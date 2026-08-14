"""Push-down: what each board is sent, and what the client is told was dropped."""

import asyncio

import pytest
from pydantic import ValidationError

from src.scrapers import vocabularies as vocab
from src.scrapers.base import DiscoveredJob
from src.scrapers.filters import (
    CareersGovFilters,
    JobStreetFilters,
    McfFilters,
    filters_for,
)
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


# --- harvested vocabularies --------------------------------------------------
# Counts are NOT pinned: the MCF harvest samples a 600-job window, so its category
# coverage legitimately varies between runs (32 on 2026-08-14, 31 the next day).
# Pinning an exact count would fail every time the script is re-run.

def test_jobstreet_work_arrangement_ids_are_the_measured_ones():
    assert vocab.JOBSTREET_WORK_ARRANGEMENTS == {
        "on_site": "1", "hybrid": "2", "remote": "3",
    }


def test_jobstreet_work_type_ids_are_the_measured_ones():
    assert vocab.JOBSTREET_WORK_TYPES["full_time"] == "242"
    assert vocab.JOBSTREET_WORK_TYPES["contract_temp"] == "244"


def test_mcf_categories_use_the_names_the_api_accepts():
    # The API 400s on a numeric category id; it accepts the display name.
    assert "Information Technology" in vocab.MCF_CATEGORIES
    assert len(vocab.MCF_CATEGORIES) >= 25


def test_mcf_employment_types_are_populated():
    assert "Full Time" in vocab.MCF_EMPLOYMENT_TYPES
    assert "Permanent" in vocab.MCF_EMPLOYMENT_TYPES


def test_careersgov_vocabularies_are_populated():
    assert "Government Technology Agency" in vocab.CAREERSGOV_AGENCIES
    assert "InfoComm, Technology, New Media Communications" in vocab.CAREERSGOV_DEPARTMENTS
    assert len(vocab.CAREERSGOV_AGENCIES) >= 80


def test_careersgov_experience_bands_are_the_five_the_board_uses():
    assert set(vocab.CAREERSGOV_EXPERIENCE_BANDS) == {
        "0 - 1 year", "1 - 3 years", "4 - 6 years", "7 - 9 years", "> 10 years",
    }


def test_agency_aliases_resolve_short_names():
    assert vocab.CAREERSGOV_AGENCY_ALIASES["govtech"] == "Government Technology Agency"


# --- per-adapter native filter models ---------------------------------------

def test_mcf_filters_accept_measured_values():
    f = McfFilters(
        categories=["Information Technology"], employment_types=["Full Time"],
    )
    assert f.categories == ["Information Technology"]


def test_unknown_vocabulary_value_passes_through_rather_than_raising():
    """A board can add a category tomorrow; rejecting it would be worse than allowing it."""
    f = McfFilters(categories=["Quantum Basket Weaving"])
    assert f.categories == ["Quantum Basket Weaving"]


def test_careersgov_agency_alias_resolves_to_the_legal_name():
    f = CareersGovFilters(agencies=["govtech"])
    assert f.agencies == ["Government Technology Agency"]


def test_careersgov_closing_within_days_is_bounded():
    with pytest.raises(ValidationError):
        CareersGovFilters(closing_within_days=0)


def test_jobstreet_rejects_an_invalid_work_arrangement():
    """Board-assigned ids are validated strictly: an id we never measured means
    nothing to JobStreet, so passing it through would silently do nothing."""
    with pytest.raises(ValidationError):
        JobStreetFilters(work_arrangements=["teleport"])


def test_jobstreet_accepts_the_measured_arrangements():
    assert JobStreetFilters(work_arrangements=["remote", "hybrid"]).work_arrangements == [
        "remote", "hybrid",
    ]


def test_filters_for_returns_none_when_a_board_has_no_extras_requested():
    assert filters_for("linkedin", {}) is None


def test_filters_for_builds_the_right_model():
    f = filters_for("careersgov", {"agencies": ["htx"]})
    assert isinstance(f, CareersGovFilters)
    assert f.agencies == ["Home Team Science and Technology Agency"]


def test_filters_for_rejects_unknown_platform():
    with pytest.raises(ValueError):
        filters_for("indeed", {"agencies": ["htx"]})


def test_every_board_descriptor_carries_its_filter_model():
    from src.scrapers import ALL_CAPABILITIES
    assert all(c.filters_model is not None for c in ALL_CAPABILITIES.values())
