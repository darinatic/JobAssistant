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

from dataclasses import dataclass, field
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
