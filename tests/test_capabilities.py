"""Capability descriptors: the declared filter surface must match reality.

The verdicts encoded here were MEASURED against the live boards on 2026-08-14 —
see docs/superpowers/specs/2026-08-14-per-board-filters-design.md. The contract
test exists because LinkedIn silently ignored f_E/f_WT for months while the UI
advertised both.
"""

import pytest

from src.scrapers import SearchParams
from src.scrapers.capabilities import (
    ALL_CAPABILITIES,
    COMMON_FILTERS,
    Support,
    capabilities_for,
)
from src.scrapers.linkedin import LinkedInGuestScraper

PLATFORMS = ["mycareersfuture", "linkedin", "jobstreet", "careersgov"]


def test_every_platform_declares_capabilities():
    assert set(ALL_CAPABILITIES) == set(PLATFORMS)


@pytest.mark.parametrize("platform", PLATFORMS)
def test_every_common_filter_has_a_verdict(platform):
    caps = capabilities_for(platform)
    assert set(caps.common) == set(COMMON_FILTERS)
    assert all(isinstance(v, Support) for v in caps.common.values())


@pytest.mark.parametrize("platform", PLATFORMS)
def test_unsupported_filters_carry_a_reason(platform):
    """An unsupported filter must explain itself — the UI shows this on hover."""
    caps = capabilities_for(platform)
    for key, support in caps.common.items():
        if support is Support.UNSUPPORTED:
            assert caps.notes.get(key), f"{platform}.{key} is unsupported with no note"


def test_measured_verdicts():
    """Locks in the 2026-08-14 probe results. Changing one means re-probing first."""
    mcf = capabilities_for("mycareersfuture").common
    assert mcf["experience_levels"] is Support.NATIVE       # positionLevels
    assert mcf["min_salary"] is Support.NATIVE              # salary=
    assert mcf["date_posted"] is Support.LOCAL              # no date param
    assert mcf["remote_options"] is Support.UNSUPPORTED     # flexibleWorkArrangements 400s

    li = capabilities_for("linkedin").common
    assert li["date_posted"] is Support.NATIVE              # f_TPR
    assert li["experience_levels"] is Support.UNSUPPORTED   # f_E measured ignored
    assert li["remote_options"] is Support.UNSUPPORTED      # f_WT measured ignored
    assert li["min_salary"] is Support.UNSUPPORTED          # f_SB2 measured ignored

    js = capabilities_for("jobstreet").common
    assert js["date_posted"] is Support.NATIVE              # daterange
    assert js["remote_options"] is Support.NATIVE           # workarrangement 1/2/3
    assert js["min_salary"] is Support.NATIVE               # salarytype+salaryrange
    assert js["experience_levels"] is Support.UNSUPPORTED

    cg = capabilities_for("careersgov").common
    assert cg["experience_levels"] is Support.LOCAL         # whole catalogue in memory
    assert cg["date_posted"] is Support.LOCAL
    assert cg["min_salary"] is Support.UNSUPPORTED          # board publishes no salary


def test_unknown_platform_raises():
    with pytest.raises(ValueError):
        capabilities_for("indeed")


# --- the contract: what we DECLARE is what we SEND -------------------------

def test_linkedin_query_omits_filters_it_cannot_honour():
    """Regression: f_E and f_WT were sent for months and silently ignored."""
    params = SearchParams(
        keyword="data engineer",
        experience_levels=["entry_level", "mid_senior"],
        remote_options=["remote", "hybrid"],
        date_posted="past_week",
    )
    q = LinkedInGuestScraper()._build_query(params)
    assert "f_E" not in q, "LinkedIn ignores f_E — declared UNSUPPORTED, must not be sent"
    assert "f_WT" not in q, "LinkedIn ignores f_WT — declared UNSUPPORTED, must not be sent"


def test_linkedin_still_sends_the_date_filter_it_does_honour():
    params = SearchParams(keyword="data engineer", date_posted="past_week")
    q = LinkedInGuestScraper()._build_query(params)
    assert q["f_TPR"] == "r604800"
