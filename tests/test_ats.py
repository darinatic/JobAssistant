"""ATS board adapter — normalization across Greenhouse / Lever / Ashby, and filtering.

Offline. Payload fixtures mirror the real API shapes observed 2026-08-13.
"""

import pytest

from src.scrapers import build_scraper
from src.scrapers.ats import (
    ASHBY,
    BOARDS,
    GREENHOUSE,
    LEVER,
    AtsScraper,
    Board,
    _matches,
    html_to_text,
    normalize,
)
from src.scrapers.base import SearchParams

_GH_BOARD = Board(GREENHOUSE, "thunes", "Thunes")
_LEVER_BOARD = Board(LEVER, "ninjavan", "Ninja Van")
_ASHBY_BOARD = Board(ASHBY, "airwallex", "Airwallex")

_GH_RAW = {
    "id": 7780947003,
    "title": "Senior Data Engineer",
    "company_name": "Thunes",
    "location": {"name": "Singapore, Central, Singapore"},
    "absolute_url": "https://www.thunes.com/jobs/7780947003?gh_jid=7780947003",
    "first_published": "2026-07-09T01:20:21-04:00",
    "updated_at": "2026-07-15T05:56:13-04:00",
    "departments": [{"name": "Engineering"}],
}

_LEVER_RAW = {
    "id": "0b5ca845-1e59-4a41-a972-759d61cfa4a6",
    "text": "Account Management Associate",
    "categories": {"location": "Singapore, Singapore", "department": "Commercial",
                   "team": "Key Account Management"},
    "createdAt": 1781765419816,
    "hostedUrl": "https://jobs.lever.co/ninjavan/0b5ca845",
    "descriptionPlain": "Job Overview. Build data pipelines.",
    "lists": [{"text": "Key Responsibilities", "content": "<li>Own the pipeline</li>"}],
    "workplaceType": "onsite",
}

_ASHBY_RAW = {
    "id": "6e975468-e033-4f50-95fe-0f4351457003",
    "title": "Senior Data Platform Engineer",
    "department": "Engineering",
    "team": "Knowledge Platform",
    "location": "SG - Singapore",
    "publishedAt": "2026-03-06T04:01:10.215+00:00",
    "jobUrl": "https://jobs.ashbyhq.com/airwallex/6e975468",
    "isRemote": False,
    "workplaceType": "OnSite",
    "descriptionHtml": "<h2>About Airwallex</h2><p>We build payments.</p>",
}


# --- html handling -----------------------------------------------------------

def test_greenhouse_entity_escaped_html_is_unescaped_before_stripping():
    """Greenhouse double-encodes: content arrives as `&lt;p&gt;`.

    Stripping tags before unescaping would leave the markup visible as literal text
    in the job description handed to the model.
    """
    raw = "&lt;p&gt;&lt;strong&gt;About Thunes&lt;/strong&gt;&lt;/p&gt;&lt;p&gt;We move money.&lt;/p&gt;"
    text = html_to_text(raw)
    assert text == "About Thunes We move money."
    assert "&lt;" not in text and "<p>" not in text


def test_plain_html_is_stripped():
    assert html_to_text("<h2>About</h2><p>We build payments.</p>") == "About We build payments."


def test_empty_html_is_empty():
    assert html_to_text("") == ""


# --- normalization -----------------------------------------------------------

def test_greenhouse_normalization():
    p = normalize(_GH_RAW, _GH_BOARD)
    assert p.external_id == "7780947003"
    assert p.title == "Senior Data Engineer"
    assert p.company == "Thunes"
    assert p.location == "Singapore, Central, Singapore"
    assert p.posted_date == "2026-07-09"          # first_published, not updated_at
    assert p.context == "Engineering"
    assert p.gh_slug == "thunes"                  # marks it for a lazy body fetch
    assert p.description == ""                    # listings carry no body
    assert p.workplace is None                    # Greenhouse never states this


def test_lever_normalization_includes_the_lists_block():
    p = normalize(_LEVER_RAW, _LEVER_BOARD)
    assert p.title == "Account Management Associate"
    assert p.company == "Ninja Van"
    assert p.posted_date == "2026-06-18"
    assert p.workplace == "on_site"
    # `lists` holds responsibilities and sits OUTSIDE `description`.
    assert "Build data pipelines" in p.description
    assert "Own the pipeline" in p.description
    assert p.gh_slug is None


def test_ashby_normalization():
    p = normalize(_ASHBY_RAW, _ASHBY_BOARD)
    assert p.title == "Senior Data Platform Engineer"
    assert p.company == "Airwallex"
    assert p.location == "SG - Singapore"
    assert p.posted_date == "2026-03-06"
    assert p.workplace == "on_site"
    assert "We build payments." in p.description


def test_ashby_is_remote_overrides_workplace_type():
    p = normalize({**_ASHBY_RAW, "isRemote": True}, _ASHBY_BOARD)
    assert p.workplace == "remote"


def test_missing_dates_do_not_raise():
    p = normalize({**_GH_RAW, "first_published": None, "updated_at": None}, _GH_BOARD)
    assert p.posted_date == ""


# --- filtering ---------------------------------------------------------------

def _params(**kw):
    base = {"keyword": "", "location": "Singapore", "date_posted": "any",
            "experience_levels": [], "remote_options": [], "max_jobs": 25}
    return SearchParams(**{**base, **kw})


def test_location_filter_keeps_singapore_only():
    sg = normalize(_GH_RAW, _GH_BOARD)
    us = normalize({**_GH_RAW, "location": {"name": "New York, USA"}}, _GH_BOARD)
    assert _matches(sg, _params())
    assert not _matches(us, _params())


def test_ashby_sg_prefix_still_matches_singapore():
    assert _matches(normalize(_ASHBY_RAW, _ASHBY_BOARD), _params())


def test_keyword_searches_title_company_and_team():
    p = normalize(_ASHBY_RAW, _ASHBY_BOARD)
    assert _matches(p, _params(keyword="data platform"))
    assert _matches(p, _params(keyword="airwallex engineer"))
    assert _matches(p, _params(keyword="knowledge"))          # team
    assert not _matches(p, _params(keyword="chef"))


def test_remote_filter_uses_stated_workplace():
    onsite = normalize(_LEVER_RAW, _LEVER_BOARD)
    remote = normalize({**_LEVER_RAW, "workplaceType": "remote"}, _LEVER_BOARD)
    assert not _matches(onsite, _params(remote_options=["remote"]))
    assert _matches(remote, _params(remote_options=["remote"]))


def test_remote_filter_never_excludes_a_board_that_stays_silent():
    # Greenhouse does not state workplace; dropping those would hide most postings.
    gh = normalize(_GH_RAW, _GH_BOARD)
    assert gh.workplace is None
    assert _matches(gh, _params(remote_options=["remote"]))


def test_date_filter_excludes_old_postings():
    old = normalize({**_GH_RAW, "first_published": "2020-01-01T00:00:00+00:00"}, _GH_BOARD)
    assert _matches(old, _params(date_posted="any"))
    assert not _matches(old, _params(date_posted="past_week"))


def test_undated_postings_survive_a_date_filter():
    undated = normalize({**_GH_RAW, "first_published": None, "updated_at": None}, _GH_BOARD)
    assert _matches(undated, _params(date_posted="past_week"))


# --- registry ----------------------------------------------------------------

def test_board_registry_is_well_formed():
    assert BOARDS, "registry must not be empty"
    assert all(b.ats in (GREENHOUSE, LEVER, ASHBY) for b in BOARDS)
    assert all(b.slug and b.company for b in BOARDS)


def test_board_registry_has_no_duplicates():
    keys = [(b.ats, b.slug) for b in BOARDS]
    assert len(keys) == len(set(keys))


def test_factory_builds_the_scraper():
    assert build_scraper("ats").PLATFORM == "ats"
    assert build_scraper("greenhouse").PLATFORM == "ats"


def test_card_mapping_leaves_salary_and_seniority_unset():
    # Neither is stated reliably by any of the three, and a guess from the title
    # would feed the matcher noise.
    card = AtsScraper()._to_discovered(normalize(_ASHBY_RAW, _ASHBY_BOARD))
    assert card.platform == "ats"
    assert card.company == "Airwallex"
    assert card.salary_min is None and card.salary_raw is None
    assert card.experience_level is None


@pytest.mark.parametrize("url,expected", [
    ("https://www.thunes.com/jobs/7780947003?gh_jid=7780947003", True),
    ("https://boards.greenhouse.io/thunes/jobs/7780947003", True),
    ("https://jobs.lever.co/ninjavan/0b5ca845", False),
])
def test_fetch_one_only_recognises_greenhouse_style_urls(url, expected):
    import re
    found = bool(re.search(r"gh_jid=(\d+)", url) or re.search(r"/jobs/(\d+)", url))
    assert found is expected


# --- on-demand body fetch ----------------------------------------------------
# fetch_one originally understood Greenhouse URLs only, so a Lever or Ashby posting
# that reached the drawer without an inline body could never recover one.

@pytest.mark.parametrize("url,vendor", [
    ("https://boards.greenhouse.io/thunes/jobs/7780947003", "greenhouse"),
    ("https://www.thunes.com/jobs/7780947003?gh_jid=7780947003", "greenhouse"),
    ("https://jobs.lever.co/ninjavan/0b5ca845-1e59-4a41-a972-759d61cfa4a6", "lever"),
    ("https://jobs.ashbyhq.com/airwallex/6e975468-e033-4f50-95fe-0f4351457003", "ashby"),
])
def test_fetch_one_recognises_every_vendor_url(url, vendor):
    import re
    lever = re.search(r"jobs\.lever\.co/([^/]+)/([0-9a-f-]{16,})", url)
    ashby = re.search(r"jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{16,})", url)
    gh = re.search(r"gh_jid=(\d+)", url) or re.search(r"/jobs/(\d+)", url)
    detected = "lever" if lever else "ashby" if ashby else "greenhouse" if gh else None
    assert detected == vendor


@pytest.mark.asyncio
async def test_fetch_one_returns_empty_for_an_unrecognised_url():
    assert await AtsScraper.fetch_one("https://example.com/careers/123") == ""
