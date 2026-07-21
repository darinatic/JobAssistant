"""Scraper filter construction (no network)."""

from src.scrapers.base import SearchParams
from src.scrapers.jobstreet import JobStreetScraper
from src.scrapers.mycareersfuture import MyCareersFutureScraper


def test_jobstreet_url_daterange():
    s = JobStreetScraper()
    week = s._build_search_url(SearchParams(keyword="AI Engineer", date_posted="past_week"), 1)
    assert "daterange=7" in week
    day = s._build_search_url(SearchParams(keyword="AI Engineer", date_posted="past_24_hours"), 1)
    assert "daterange=1" in day
    any_ = s._build_search_url(SearchParams(keyword="AI Engineer", date_posted="any"), 1)
    assert "daterange" not in any_


def test_jobstreet_url_slug():
    url = JobStreetScraper()._build_search_url(SearchParams(keyword="Machine Learning Engineer"), 2)
    assert "machine-learning-engineer-jobs" in url and "page=2" in url


def test_mcf_posting_date_parse():
    assert MyCareersFutureScraper._posting_date({"metadata": {"newPostingDate": "2026-07-03"}}).isoformat() == "2026-07-03"
    assert MyCareersFutureScraper._posting_date({"metadata": {}}) is None
    assert MyCareersFutureScraper._posting_date({"metadata": {"newPostingDate": "garbage"}}) is None
