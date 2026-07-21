"""Concurrent multi-platform scrape + on-demand description fetch (no network)."""

import asyncio

import pytest

from src import search as job_search
from src.scrapers.base import DiscoveredJob


class _FakeScraper:
    """Yields n jobs, optionally after a per-job delay; records the params it saw."""

    seen_flags: dict[str, bool] = {}

    def __init__(self, platform: str, n: int = 2, delay: float = 0.0):
        self.PLATFORM = platform
        self._n = n
        self._delay = delay

    async def search(self, params):
        _FakeScraper.seen_flags[self.PLATFORM] = params.fetch_descriptions
        for i in range(min(self._n, params.max_jobs)):  # real scrapers honor max_jobs
            if self._delay:
                await asyncio.sleep(self._delay)
            yield DiscoveredJob(
                platform=self.PLATFORM, external_id=f"{self.PLATFORM}-{i}",
                url=f"http://x/{self.PLATFORM}/{i}", title="AI Engineer",
                company="Acme", location="Central", description="Python and PyTorch",
            )


def _patch(monkeypatch, mapping):
    monkeypatch.setattr(job_search, "build_scraper", lambda p: mapping[p])
    monkeypatch.setattr(job_search, "DEFAULT_PLATFORMS", list(mapping.keys()))


def test_platform_budgets_weight_favors_high_volume_boards():
    # Small total so caps don't bind: JobStreet/LinkedIn outweigh MCF.
    b = job_search._platform_budgets(["mycareersfuture", "linkedin", "jobstreet"], 10)
    assert b["jobstreet"] > b["mycareersfuture"]
    assert b["linkedin"] > b["mycareersfuture"]
    assert all(n >= 1 for n in b.values())


def test_platform_budgets_respect_reliability_caps():
    b = job_search._platform_budgets(["mycareersfuture", "linkedin", "jobstreet"], 1000)
    assert b["linkedin"] == job_search._CAPS["linkedin"]
    assert b["jobstreet"] == job_search._CAPS["jobstreet"]
    assert b["mycareersfuture"] == job_search._CAPS["mycareersfuture"]


@pytest.mark.asyncio
async def test_weighted_budget_no_starvation(monkeypatch):
    # Every platform floods; weighted budgets must let each contribute its share
    # (no first-arrived race) and the total equals the sum of budgets.
    mapping = {p: _FakeScraper(p, n=500) for p in ["mycareersfuture", "linkedin", "jobstreet"]}
    _patch(monkeypatch, mapping)
    budgets = job_search._platform_budgets(list(mapping.keys()), 60)
    jobs = await job_search.search_jobs(keyword="AI", max_jobs=60)
    from collections import Counter
    by = Counter(j["platform"] for j in jobs)
    assert len(jobs) == sum(budgets.values())
    for p, n in budgets.items():
        assert by[p] == n  # each platform contributes exactly its budget, none starved


@pytest.mark.asyncio
async def test_scrape_runs_platforms_concurrently(monkeypatch):
    # "slow" is listed first but sleeps before its first yield; if the scrape were
    # sequential, its jobs would arrive first. Concurrency lets "fast" win.
    _patch(monkeypatch, {"slow": _FakeScraper("slow", delay=0.2), "fast": _FakeScraper("fast", delay=0.0)})
    seen = [j async for j in job_search.search_jobs_stream(keyword="AI", max_jobs=10)]
    platforms = [j["platform"] for j in seen]
    assert set(platforms) == {"slow", "fast"}
    assert platforms[0] == "fast"  # fast platform not blocked behind slow one


class _FitFake:
    """Yields jobs whose description encodes the fit score the mocked model returns."""
    def __init__(self, platform: str, scores: list[float]):
        self.PLATFORM = platform
        self._scores = scores

    async def search(self, params):
        for i, s in enumerate(self._scores):
            yield DiscoveredJob(
                platform=self.PLATFORM, external_id=f"{self.PLATFORM}-{i}", url="u",
                title="AI Engineer", company="C", location="SG", description=f"role score={s}",
            )


@pytest.mark.asyncio
async def test_search_adds_fit_and_ranks_by_it(monkeypatch):
    import re
    import src.match_predictor as mp
    monkeypatch.setattr(mp, "is_enabled", lambda: True)
    monkeypatch.setattr(mp, "predict_fit", lambda cv, text: float(re.search(r"score=([\d.]+)", text).group(1)))

    monkeypatch.setattr(job_search, "build_scraper", lambda p: _FitFake("x", [0.2, 0.9, 0.5]))
    monkeypatch.setattr(job_search, "DEFAULT_PLATFORMS", ["x"])
    jobs = await job_search.search_jobs(keyword="AI", max_jobs=10, master_cv="Python dev")

    assert [j["fit"] for j in jobs] == [90, 50, 20]        # sorted by learned fit, desc


@pytest.mark.asyncio
async def test_no_fit_when_predictor_disabled(monkeypatch):
    import src.match_predictor as mp
    monkeypatch.setattr(mp, "is_enabled", lambda: False)
    monkeypatch.setattr(job_search, "build_scraper", lambda p: _FitFake("x", [0.2, 0.9]))
    monkeypatch.setattr(job_search, "DEFAULT_PLATFORMS", ["x"])
    jobs = await job_search.search_jobs(keyword="AI", max_jobs=10, master_cv="Python dev")
    assert all("fit" not in j for j in jobs)               # off by default → no-op


@pytest.mark.asyncio
async def test_global_cap_limits_total_across_platforms(monkeypatch):
    # Two platforms that can each yield 5; max_jobs=6 must cap the TOTAL at 6,
    # not return 10 (one full cap per platform — the reported bug).
    _patch(monkeypatch, {"a": _FakeScraper("a", n=5), "b": _FakeScraper("b", n=5)})
    jobs = await job_search.search_jobs(keyword="AI", max_jobs=6)
    assert len(jobs) == 6


@pytest.mark.asyncio
async def test_search_defers_descriptions_by_default(monkeypatch):
    _FakeScraper.seen_flags = {}
    _patch(monkeypatch, {"a": _FakeScraper("a"), "b": _FakeScraper("b")})
    await job_search.search_jobs(keyword="AI", max_jobs=10)
    assert _FakeScraper.seen_flags == {"a": False, "b": False}


@pytest.mark.asyncio
async def test_search_can_opt_into_eager_descriptions(monkeypatch):
    _FakeScraper.seen_flags = {}
    _patch(monkeypatch, {"a": _FakeScraper("a")})
    await job_search.search_jobs(keyword="AI", max_jobs=10, fetch_descriptions=True)
    assert _FakeScraper.seen_flags == {"a": True}


@pytest.mark.asyncio
async def test_enrich_streams_updates_and_splits_skills(monkeypatch):
    monkeypatch.setattr("src.browser.browserbase.enabled", lambda: False)  # force httpx path
    async def fake_desc(self, client, job_id):
        return "We need Python and Docker experience."
    monkeypatch.setattr("src.scrapers.linkedin.LinkedInGuestScraper._fetch_description", fake_desc)
    monkeypatch.setattr("random.uniform", lambda *a: 0)  # no polite sleep in tests

    jobs = [{"platform": "linkedin", "external_id": "1", "url": "http://x/1", "title": "AI Engineer"}]
    updates = [u async for u in job_search.enrich_descriptions_stream(jobs, master_cv="I use Python daily.")]
    assert len(updates) == 1
    u = updates[0]
    assert u["external_id"] == "1" and u["has_description"] is True
    assert "Python" in u["matched_skills"]       # in the CV
    assert "Docker" in u["missing_skills"]        # wanted, not in the CV


@pytest.mark.asyncio
async def test_enrich_routes_linkedin_through_browserbase_when_enabled(monkeypatch):
    import src.browser.browserbase as bbmod
    monkeypatch.setattr(bbmod, "enabled", lambda: True)

    async def fake_bb(items):
        for j in items:
            yield j, "We need Python and Kubernetes."
    monkeypatch.setattr(bbmod, "fetch_linkedin_descriptions", fake_bb)

    jobs = [{"platform": "linkedin", "external_id": "1", "url": "u", "title": "AI Engineer"}]
    updates = [u async for u in job_search.enrich_descriptions_stream(jobs, master_cv="Python dev")]
    assert len(updates) == 1 and updates[0]["has_description"] is True
    assert "Python" in updates[0]["matched_skills"]
    assert "Kubernetes" in updates[0]["missing_skills"]


@pytest.mark.asyncio
async def test_enrich_skips_cards_that_already_have_descriptions(monkeypatch):
    # MCF cards arrive with inline descriptions — enrichment must not refetch them.
    jobs = [{"platform": "mycareersfuture", "external_id": "m1", "url": "u", "title": "T",
             "description": "Already has Python here."}]
    updates = [u async for u in job_search.enrich_descriptions_stream(jobs, master_cv="Python")]
    assert updates == []


@pytest.mark.asyncio
async def test_fetch_job_description_dispatch(monkeypatch):
    monkeypatch.setattr("src.browser.browserbase.enabled", lambda: False)  # force guest path
    async def fake_li(external_id):
        return f"LI desc for {external_id}"
    monkeypatch.setattr("src.scrapers.linkedin.LinkedInGuestScraper.fetch_one", staticmethod(fake_li))
    assert await job_search.fetch_job_description("linkedin", "123", "http://x") == "LI desc for 123"
    # Unknown platform → empty, never raises.
    assert await job_search.fetch_job_description("nope", "", "") == ""
