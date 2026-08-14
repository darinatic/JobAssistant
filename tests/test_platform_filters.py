"""Push-down: what each board is sent, and what the client is told was dropped."""

import asyncio

import pytest

from src.scrapers.base import DiscoveredJob
from src.search import build_filter_report


def test_filter_report_covers_every_selected_platform():
    report = build_filter_report(
        ["mycareersfuture", "linkedin"],
        {"experience_levels": ["entry_level"], "min_salary": 5000},
    )
    assert set(report) == {"mycareersfuture", "linkedin"}


def test_filter_report_names_applied_and_dropped_filters():
    report = build_filter_report(["linkedin"], {"min_salary": 5000, "date_posted": "past_week"})
    assert report["linkedin"]["applied"] == ["date_posted"]
    assert "min_salary" in report["linkedin"]["dropped"]


def test_filter_report_lists_local_filters_as_applied_too():
    """A locally-applied filter IS applied — the user should not see it as lost."""
    report = build_filter_report(["careersgov"], {"experience_levels": ["entry_level"]})
    assert report["careersgov"]["applied"] == ["experience_levels"]
    assert report["careersgov"]["dropped"] == {}


def test_filter_report_is_empty_when_nothing_was_requested():
    report = build_filter_report(["jobstreet"], {"date_posted": "any", "min_salary": None})
    assert report["jobstreet"] == {"applied": [], "dropped": {}}


# --- fail-open: a scrapeable platform with no capability descriptor ----------
# Regression: partition_filters() raising inside _scrape's per-platform task killed
# it before it could queue its done-sentinel, so the consumer waited forever. Any
# exception between building the scraper and the search loop deadlocked the search.

@pytest.mark.asyncio
async def test_scrape_terminates_for_a_platform_with_no_descriptor(monkeypatch):
    from src import search as job_search

    class _Fake:
        PLATFORM = "fake"

        async def search(self, params):
            for i in range(2):
                yield DiscoveredJob(
                    platform="fake", external_id=str(i), url="u",
                    title="Engineer", company="C", location="Singapore",
                )

    monkeypatch.setattr(job_search, "build_scraper", lambda p: _Fake())
    monkeypatch.setattr(job_search, "DEFAULT_PLATFORMS", ["fake"])

    jobs = await asyncio.wait_for(
        job_search.search_jobs(keyword="AI", max_jobs=5, date_posted="past_week"), timeout=10,
    )
    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_scrape_fails_open_and_forwards_every_filter_to_an_undescribed_board(monkeypatch):
    """Without a descriptor we cannot know what the board drops, so send it all —
    the pre-capability behaviour — rather than silently filtering nothing."""
    from src import search as job_search

    seen: list = []

    class _Fake:
        PLATFORM = "fake"

        async def search(self, params):
            seen.append(params)
            return
            yield  # pragma: no cover  (makes this an async generator)

    monkeypatch.setattr(job_search, "build_scraper", lambda p: _Fake())
    monkeypatch.setattr(job_search, "DEFAULT_PLATFORMS", ["fake"])

    await asyncio.wait_for(
        job_search.search_jobs(
            keyword="AI", max_jobs=5, date_posted="past_week",
            experience_levels=["entry_level"], remote_options=["remote"], min_salary=5000,
        ),
        timeout=10,
    )
    assert seen and seen[0].date_posted == "past_week"
    assert seen[0].experience_levels == ["entry_level"]
    assert seen[0].remote_options == ["remote"]
    assert seen[0].min_salary == 5000
