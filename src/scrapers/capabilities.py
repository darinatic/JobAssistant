"""What each board can actually filter, measured rather than assumed.

Every verdict here was probed against the live board on 2026-08-14 (method and
raw numbers: docs/superpowers/specs/2026-08-14-per-board-filters-design.md).
Two of them contradict what this codebase believed for months:

  * LinkedIn's guest endpoint IGNORES f_E and f_WT. `f_E=1` (internship only) and
    `f_E=6` (executive only) return byte-identical job sets.
  * JobStreet DOES support remote (`workarrangement` 1/2/3) and salary
    (`salarytype` x `salaryrange`), neither of which we ever sent.

`Support` describes SEARCH TIME only. A filter a board cannot push down is not
lost — it falls to the client-side refine bar over the fetched results.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from pydantic import BaseModel


class Support(StrEnum):
    NATIVE = "native"            # the board filters it server-side
    LOCAL = "local"              # the adapter filters its own payload
    UNSUPPORTED = "unsupported"  # cannot be done at search time


# The shared filter vocabulary. Keys match SearchParams field names.
COMMON_FILTERS = ("date_posted", "experience_levels", "remote_options", "min_salary")


@dataclass(frozen=True)
class BoardCapabilities:
    platform: str
    common: dict[str, Support]
    filters_model: type[BaseModel] | None = None
    notes: dict[str, str] = field(default_factory=dict)


ALL_CAPABILITIES: dict[str, BoardCapabilities] = {
    "mycareersfuture": BoardCapabilities(
        platform="mycareersfuture",
        common={
            "date_posted": Support.LOCAL,
            "experience_levels": Support.NATIVE,
            "remote_options": Support.UNSUPPORTED,
            "min_salary": Support.NATIVE,
        },
        notes={
            "date_posted": "No date parameter; results are sorted newest-first and cut locally.",
            "remote_options": "The flexibleWorkArrangements query parameter returns HTTP 400. "
                              "The field exists on each record, so remote can be narrowed "
                              "after the search.",
        },
    ),
    "linkedin": BoardCapabilities(
        platform="linkedin",
        common={
            "date_posted": Support.NATIVE,
            "experience_levels": Support.UNSUPPORTED,
            "remote_options": Support.UNSUPPORTED,
            "min_salary": Support.UNSUPPORTED,
        },
        notes={
            "experience_levels": "The guest endpoint ignores f_E (measured). Seniority is on "
                                 "the detail page only, so it can be narrowed after "
                                 "descriptions load.",
            "remote_options": "The guest endpoint ignores f_WT (measured).",
            "min_salary": "The guest endpoint ignores f_SB2 (measured), and cards carry no salary.",
        },
    ),
    "jobstreet": BoardCapabilities(
        platform="jobstreet",
        common={
            "date_posted": Support.NATIVE,
            "experience_levels": Support.UNSUPPORTED,
            "remote_options": Support.NATIVE,
            "min_salary": Support.NATIVE,
        },
        notes={
            "experience_levels": "JobStreet publishes no seniority field at all.",
        },
    ),
    "careersgov": BoardCapabilities(
        platform="careersgov",
        common={
            "date_posted": Support.LOCAL,
            "experience_levels": Support.LOCAL,
            "remote_options": Support.UNSUPPORTED,
            "min_salary": Support.UNSUPPORTED,
        },
        notes={
            "remote_options": "The board publishes no work-arrangement field.",
            "min_salary": "The board publishes no salary. salaryRange was null on all "
                          "2,171 postings.",
        },
    ),
}


def capabilities_for(platform: str) -> BoardCapabilities:
    """Descriptor for a platform name. Raises ValueError for an unknown board."""
    caps = ALL_CAPABILITIES.get(platform.lower().replace(" ", "").replace("-", ""))
    if caps is None:
        raise ValueError(f"Unknown platform: {platform}")
    return caps


# A filter set to any of these is "not requested" rather than "requested and dropped".
_UNSET: tuple[object, ...] = (None, "", "any", [], (), {})


def _is_set(value: object) -> bool:
    return value not in _UNSET


@dataclass(frozen=True)
class FilterPlan:
    """How one board handles one request's filters."""

    pushed: dict[str, object]    # sent to the board itself
    local: dict[str, object]     # the adapter applies these to its own payload
    dropped: dict[str, str]      # filter key -> why this board cannot honour it


_DEFAULT_REASON = "This board does not support that filter."


def partition_filters(platform: str, requested: dict[str, object]) -> FilterPlan:
    """Split a request's common filters into pushed / local / dropped for one board.

    Filters left at their default are not "dropped" — nothing was asked for. Only a
    genuinely requested filter that the board cannot honour lands in `dropped`, and
    it always carries a reason so the UI can say why.
    """
    caps = capabilities_for(platform)
    pushed: dict[str, object] = {}
    local: dict[str, object] = {}
    dropped: dict[str, str] = {}

    for key, value in requested.items():
        if key not in caps.common or not _is_set(value):
            continue
        support = caps.common[key]
        if support is Support.NATIVE:
            pushed[key] = value
        elif support is Support.LOCAL:
            local[key] = value
        else:
            dropped[key] = caps.notes.get(key, _DEFAULT_REASON)

    return FilterPlan(pushed=pushed, local=local, dropped=dropped)


def _attach_filter_models() -> None:
    """Bind each board's native-filter model to its descriptor.

    Late-bound and called from src/scrapers/__init__.py after every adapter is
    imported: filters.py imports vocabularies, and binding at module scope here
    would order-couple this module to it.
    """
    from src.scrapers.filters import (
        CareersGovFilters,
        JobStreetFilters,
        LinkedInFilters,
        McfFilters,
    )

    models: dict[str, type[BaseModel]] = {
        "mycareersfuture": McfFilters,
        "jobstreet": JobStreetFilters,
        "careersgov": CareersGovFilters,
        "linkedin": LinkedInFilters,
    }
    for name, model in models.items():
        ALL_CAPABILITIES[name] = replace(ALL_CAPABILITIES[name], filters_model=model)
