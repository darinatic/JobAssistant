"""SearchQuery validators (no LLM) — normalization of parsed filters."""

from src.search_nlp import SearchQuery


def test_platform_aliases_normalized():
    q = SearchQuery(keyword="AI", platforms=["JobStreet", "mcf", "LinkedIn", "bogus"])
    assert q.platforms == ["jobstreet", "mycareersfuture", "linkedin"]


def test_max_jobs_clamped():
    assert SearchQuery(keyword="AI", max_jobs=500).max_jobs == 50
    assert SearchQuery(keyword="AI", max_jobs=100).max_jobs == 50  # capped at 50
    assert SearchQuery(keyword="AI", max_jobs=0).max_jobs == 1
    assert SearchQuery(keyword="AI", max_jobs="lots").max_jobs == 25  # type: ignore[arg-type]


def test_date_posted_normalized():
    assert SearchQuery(keyword="AI", date_posted="past week").date_posted == "past_week"
    assert SearchQuery(keyword="AI", date_posted="yesterday").date_posted == "any"


def test_enum_lists_filtered():
    q = SearchQuery(keyword="AI", experience_levels=["entry_level", "wizard"], remote_options=["remote", "moon"])
    assert q.experience_levels == ["entry_level"]
    assert q.remote_options == ["remote"]


def test_defaults():
    q = SearchQuery(keyword="AI Engineer")
    assert q.location == "Singapore" and q.date_posted == "any" and q.max_jobs == 25 and q.platforms == []
