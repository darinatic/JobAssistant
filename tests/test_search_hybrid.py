from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api import app
from src.search_nlp import SearchFilters, SearchQuery, build_query


@pytest.fixture
def client():
    return TestClient(app)


def test_build_query_uses_filter_keyword_and_fields():
    f = SearchFilters(keyword="AI Engineer", date_posted="past_week",
                      platforms=["linkedin"], experience_levels=["entry_level"], max_jobs=50)
    q = build_query(f, fallback_query="ignored because keyword is set")
    assert isinstance(q, SearchQuery)
    assert q.keyword == "AI Engineer"
    assert q.date_posted == "past_week"
    assert q.platforms == ["linkedin"]
    assert q.experience_levels == ["entry_level"]
    assert q.max_jobs == 50


def test_build_query_falls_back_to_query_when_no_keyword():
    q = build_query(SearchFilters(), fallback_query="Data Scientist")
    assert q.keyword == "Data Scientist"


def test_search_with_filters_skips_llm_parse(client):
    parse = AsyncMock()  # must NOT be called when filters are supplied
    search = AsyncMock(return_value=[])
    with patch("src.search_nlp.parse_search_query", parse), \
         patch("src.api.job_search.search_jobs", search):
        r = client.post("/search", json={
            "query": "AI Engineer",
            "filters": {"keyword": "AI Engineer", "date_posted": "past_week", "platforms": ["mycareersfuture"]},
        })
    assert r.status_code == 200, r.text
    parse.assert_not_called()
    assert search.call_args.kwargs["date_posted"] == "past_week"
    assert search.call_args.kwargs["platforms"] == ["mycareersfuture"]
    assert r.json()["interpreted"]["date_posted"] == "past_week"


def test_search_without_filters_parses_nl(client):
    parse = AsyncMock(return_value=SearchQuery(keyword="AI Engineer", date_posted="past_month"))
    search = AsyncMock(return_value=[])
    with patch("src.search_nlp.parse_search_query", parse), \
         patch("src.api.job_search.search_jobs", search):
        r = client.post("/search", json={"query": "AI Engineer jobs this month"})
    assert r.status_code == 200, r.text
    parse.assert_awaited_once()
    assert r.json()["interpreted"]["date_posted"] == "past_month"
