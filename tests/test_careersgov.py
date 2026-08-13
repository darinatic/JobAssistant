"""Careers@Gov adapter — RSC catalogue extraction, filtering, and body parsing.

Offline: catalogue parsing runs against a hand-built flight payload, and description
parsing against a captured detail page (tests/fixtures/careersgov_detail.html).
"""

import json
from pathlib import Path

import pytest

from src.scrapers import build_scraper
from src.scrapers.careersgov import (
    CareersGovScraper,
    _matches_experience,
    _matches_keyword,
    _posted_date,
    extract_jobs,
    parse_description,
)
from src.scrapers.parsing import lowest_careersgov_band, normalize_experience

_FIXTURE = Path(__file__).parent / "fixtures" / "careersgov_detail.html"


def _flight(*objs: dict) -> str:
    """Build a page whose RSC payload embeds `objs`, the way Next.js streams it."""
    # The site emits COMPACT json (no spaces after ':' / ','), which the extractor's
    # object-start pattern relies on — encode the fixture the same way.
    inner = ("some prefix "
             + ",".join(json.dumps(o, separators=(",", ":")) for o in objs)
             + " some suffix")
    return f"<script>self.__next_f.push([1,{json.dumps(inner)}])</script>"


_JOB = {
    "id": "17659145/005056a3-53e2-1fd1-a4a1-646d77f0f402",
    "name": "Senior Data Engineer (Platforms)",
    "agency": "Government Technology Agency",
    "department": "InfoComm, Technology, New Media Communications",
    "employmentType": "Permanent",
    "jobSource": "hrp",
    "closeAt": "Closing in 6 day(s)",
    "experienceLevels": ["1 - 3 years", "4 - 6 years"],
    "activityTimestamp": 1784332800000,
    "closingTimestamp": 1787011200000,
    "isAvailable": True,
}


# --- catalogue extraction ----------------------------------------------------

def test_extracts_jobs_from_the_rsc_payload():
    jobs = extract_jobs(_flight(_JOB))
    assert len(jobs) == 1
    assert jobs[0]["name"] == "Senior Data Engineer (Platforms)"
    assert jobs[0]["agency"] == "Government Technology Agency"


def test_non_ascii_titles_survive():
    # A blanket unicode_escape decode would corrupt these; the parser must json-decode
    # each flight literal instead.
    job = {**_JOB, "name": "Engineer – Renewable Energy (Café Systems)"}
    assert extract_jobs(_flight(job))[0]["name"] == "Engineer – Renewable Energy (Café Systems)"


def test_records_repeated_across_chunks_are_deduped():
    page = _flight(_JOB) + _flight(_JOB)
    assert len(extract_jobs(page)) == 1


def test_extraction_survives_an_unparseable_chunk():
    page = "<script>self.__next_f.push([1,\"broken\\\"])</script>" + _flight(_JOB)
    assert len(extract_jobs(page)) == 1


def test_a_page_with_no_payload_yields_nothing():
    assert extract_jobs("<html><body>nothing here</body></html>") == []


def test_extra_unknown_fields_do_not_break_decoding():
    jobs = extract_jobs(_flight({**_JOB, "somethingNew": {"nested": [1, 2]}}))
    assert jobs and jobs[0]["somethingNew"] == {"nested": [1, 2]}


# --- filtering ---------------------------------------------------------------

@pytest.mark.parametrize("keyword", ["data", "DATA ENGINEER", "govtech technology", ""])
def test_keyword_matches_across_title_agency_and_department(keyword):
    # "govtech technology" only matches if agency and department are searched too.
    assert _matches_keyword({**_JOB, "agency": "GovTech"}, keyword)


def test_keyword_requires_every_term():
    assert not _matches_keyword(_JOB, "data chef")


def test_experience_filter_matches_any_listed_band():
    assert _matches_experience(_JOB, ["associate"])
    assert _matches_experience(_JOB, ["mid_senior"])
    assert not _matches_experience(_JOB, ["director"])


def test_experience_filter_keeps_postings_that_state_nothing():
    # Excluding on a field the posting never filled in would silently drop real jobs.
    assert _matches_experience({**_JOB, "experienceLevels": []}, ["director"])


def test_undefined_sentinel_is_not_treated_as_a_level():
    job = {**_JOB, "experienceLevels": ["$undefined"]}
    assert _matches_experience(job, ["director"])  # falls through to "unstated"


def test_posted_date_from_epoch_millis():
    assert _posted_date(_JOB) == "2026-07-18"
    assert _posted_date({**_JOB, "activityTimestamp": None}) == ""


# --- experience normalization ------------------------------------------------

def test_lowest_band_wins():
    assert lowest_careersgov_band(["4 - 6 years", "1 - 3 years"]) == "1 - 3 years"
    assert lowest_careersgov_band(["> 10 years"]) == "> 10 years"
    assert lowest_careersgov_band(["$undefined"]) is None
    assert lowest_careersgov_band([]) is None


@pytest.mark.parametrize("band,bucket", [
    ("0 - 1 year", "entry_level"),
    ("1 - 3 years", "associate"),
    ("4 - 6 years", "mid_senior"),
    ("7 - 9 years", "mid_senior"),
    ("> 10 years", "director"),
])
def test_bands_map_to_our_buckets(band, bucket):
    assert normalize_experience(band, "careersgov") == bucket


# --- url + card mapping ------------------------------------------------------

def test_job_url_uses_the_sitemap_shape():
    assert CareersGovScraper.job_url(_JOB) == (
        "https://jobs.careers.gov.sg/jobs/hrp/17659145/005056a3-53e2-1fd1-a4a1-646d77f0f402"
    )


def test_job_url_honours_non_hrp_sources():
    # The catalogue also carries greenhouse- and workable-hosted postings.
    assert "/jobs/greenhouse/" in CareersGovScraper.job_url({**_JOB, "jobSource": "greenhouse"})


def test_card_mapping():
    card = CareersGovScraper()._to_discovered(_JOB, "body text")
    assert card.platform == "careersgov"
    assert card.title == "Senior Data Engineer (Platforms)"
    assert card.company == "Government Technology Agency"
    assert card.location == "Singapore"
    assert card.description == "body text"
    assert card.experience_level == "associate"     # lowest band of the two listed
    assert card.experience_raw == "1 - 3 years, 4 - 6 years"
    assert card.salary_min is None                  # the board never publishes salary


def test_undefined_fields_render_empty_not_literal():
    card = CareersGovScraper()._to_discovered({**_JOB, "agency": "$undefined"}, "")
    assert card.company == ""


def test_factory_builds_the_scraper():
    assert build_scraper("careersgov").PLATFORM == "careersgov"
    assert build_scraper("careers@gov").PLATFORM == "careersgov"


# --- description parsing -----------------------------------------------------

@pytest.mark.skipif(not _FIXTURE.exists(), reason="detail fixture not captured")
def test_description_excludes_the_government_masthead():
    """Every gov page opens with the SG masthead banner.

    Falling back to <main> would prepend ~250 chars of "Expand masthead to find out
    how to identify an official government website..." to EVERY posting, polluting
    the JD sent to the model.
    """
    body = parse_description(_FIXTURE.read_text(encoding="utf-8"))
    assert body
    assert "Expand masthead" not in body
    assert "identify an official government" not in body


@pytest.mark.skipif(not _FIXTURE.exists(), reason="detail fixture not captured")
def test_description_keeps_the_section_headings():
    body = parse_description(_FIXTURE.read_text(encoding="utf-8"))
    assert "What the role is" in body
    assert "What you will be working on" in body
    assert len(body) > 500


def test_description_of_an_empty_page_is_empty():
    assert parse_description("<html><body></body></html>") == ""


def test_description_falls_back_to_labelled_sections():
    # If <article> disappears, headed blocks are still recovered rather than the page.
    html = (
        "<html><body><main>Expand masthead to find out how to identify a website"
        "<h2>What the role is</h2><p>" + "Build data pipelines. " * 5 + "</p>"
        "</main></body></html>"
    )
    body = parse_description(html)
    assert "What the role is" in body
    assert "Expand masthead" not in body


# --- agency acronyms ---------------------------------------------------------
# The board lists full legal names only, so an unexpanded "govtech" matched nothing.

@pytest.mark.parametrize("term,agency", [
    ("govtech", "Government Technology Agency"),
    ("htx", "Home Team Science and Technology Agency (HTX)"),
    ("dsta", "Defence Science and Technology Agency"),
    ("csit", "Centre for Strategic Infocomm Technologies"),
    ("lta", "Land Transport Authority"),
])
def test_agency_acronyms_match_full_legal_names(term, agency):
    assert _matches_keyword({**_JOB, "agency": agency}, term)


def test_acronym_combines_with_a_role_term():
    job = {**_JOB, "agency": "Government Technology Agency", "name": "Data Engineer"}
    assert _matches_keyword(job, "govtech data")
    assert not _matches_keyword(job, "govtech chef")


def test_an_acronym_does_not_match_an_unrelated_agency():
    assert not _matches_keyword({**_JOB, "agency": "Land Transport Authority"}, "govtech")
