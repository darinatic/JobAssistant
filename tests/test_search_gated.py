import asyncio
from unittest.mock import patch

import src.search as search


def _card(pid, title="AI Engineer", platform="mycareersfuture", desc="Python PyTorch RAG"):
    return {"platform": platform, "external_id": pid, "url": f"u/{pid}",
            "title": title, "company": "X", "location": "SG",
            "description": desc, "posted_date": ""}


async def _fake_scrape(*a, **k):
    # 6 MCF cards with inline descriptions (no pool fetch needed).
    for i in range(6):
        yield _card(str(i), desc=f"role {i} Python PyTorch")


def _collect(gen):
    async def run():
        return [x async for x in gen]
    return asyncio.run(run())


def test_gate_passes_only_above_threshold(monkeypatch):
    monkeypatch.setattr(search, "_scrape", _fake_scrape)
    monkeypatch.setattr(search.settings, "match_gate_threshold", 50)
    monkeypatch.setattr(search.settings, "gate_scrape_cap_mult", 3)

    def fake_score(emb, jd):
        return 0.8 if ("role 0" in jd or "role 2" in jd or "role 4" in jd) else 0.2

    with patch("src.match_predictor.is_enabled", return_value=True), \
         patch("src.match_predictor.embed_resume", return_value="CVEMB"), \
         patch("src.match_predictor.score", side_effect=fake_score):
        items = _collect(search.search_jobs_gated_stream(
            keyword="AI", max_jobs=2, master_cv="my cv"))
    jobs = [i["data"] for i in items if i["type"] == "job"]
    assert len(jobs) == 2                      # stops at N=2 passes
    assert all(j["fit"] >= 50 for j in jobs)
    assert all(not j.get("below_threshold") for j in jobs)


def test_floor_when_too_few_pass(monkeypatch):
    monkeypatch.setattr(search, "_scrape", _fake_scrape)
    monkeypatch.setattr(search.settings, "match_gate_threshold", 90)  # nothing passes
    monkeypatch.setattr(search.settings, "gate_scrape_cap_mult", 3)

    def fake_score(emb, jd):
        return 0.30

    with patch("src.match_predictor.is_enabled", return_value=True), \
         patch("src.match_predictor.embed_resume", return_value="CVEMB"), \
         patch("src.match_predictor.score", side_effect=fake_score):
        items = _collect(search.search_jobs_gated_stream(
            keyword="AI", max_jobs=3, master_cv="my cv"))
    jobs = [i["data"] for i in items if i["type"] == "job"]
    assert len(jobs) == 3                       # floor shows best-K
    assert all(j.get("below_threshold") for j in jobs)


def test_emits_progress(monkeypatch):
    monkeypatch.setattr(search, "_scrape", _fake_scrape)
    monkeypatch.setattr(search.settings, "match_gate_threshold", 50)

    with patch("src.match_predictor.is_enabled", return_value=True), \
         patch("src.match_predictor.embed_resume", return_value="CVEMB"), \
         patch("src.match_predictor.score", return_value=0.8):
        items = _collect(search.search_jobs_gated_stream(
            keyword="AI", max_jobs=2, master_cv="cv"))
    assert any(i["type"] == "progress" for i in items)
