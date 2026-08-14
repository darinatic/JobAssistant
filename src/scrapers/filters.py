"""Native-only filter dimensions, one model per board.

These carry what a board can do that the shared SearchParams cannot express.
Vocabulary values are validated LENIENTLY against the snapshots in
vocabularies.py: an unrecognised value is logged and passed through, because a
board adding a new agency must not break the search. Values with a fixed,
board-assigned id (JobStreet work types) are validated strictly — an id we did
not measure is meaningless to the board.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field, field_validator

from src.scrapers import vocabularies as vocab
from src.scrapers.vocabularies import CAREERSGOV_AGENCY_ALIASES

log = logging.getLogger(__name__)


def _warn_unknown(values: list[str], known: tuple[str, ...], field: str) -> list[str]:
    for v in values:
        if v not in known:
            log.info(
                "Unrecognised %s value %r — passing through (vocabulary may be stale)", field, v
            )
    return values


class McfFilters(BaseModel):
    categories: list[str] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    schemes: list[str] = Field(default_factory=list)

    @field_validator("categories")
    @classmethod
    def _check_categories(cls, v: list[str]) -> list[str]:
        return _warn_unknown(v, vocab.MCF_CATEGORIES, "MCF category")

    @field_validator("employment_types")
    @classmethod
    def _check_employment(cls, v: list[str]) -> list[str]:
        return _warn_unknown(v, vocab.MCF_EMPLOYMENT_TYPES, "MCF employment type")


class JobStreetFilters(BaseModel):
    work_types: list[str] = Field(default_factory=list)
    work_arrangements: list[str] = Field(default_factory=list)
    salary_type: str = "monthly"
    salary_max: int | None = None

    @field_validator("work_types")
    @classmethod
    def _check_work_types(cls, v: list[str]) -> list[str]:
        unknown = [x for x in v if x not in vocab.JOBSTREET_WORK_TYPES]
        if unknown:
            raise ValueError(f"Unknown JobStreet work type(s): {unknown}")
        return v

    @field_validator("work_arrangements")
    @classmethod
    def _check_arrangements(cls, v: list[str]) -> list[str]:
        unknown = [x for x in v if x not in vocab.JOBSTREET_WORK_ARRANGEMENTS]
        if unknown:
            raise ValueError(f"Unknown JobStreet work arrangement(s): {unknown}")
        return v

    @field_validator("salary_type")
    @classmethod
    def _check_salary_type(cls, v: str) -> str:
        if v not in vocab.JOBSTREET_SALARY_TYPES:
            raise ValueError(f"Unknown JobStreet salary type: {v}")
        return v


class CareersGovFilters(BaseModel):
    agencies: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    closing_within_days: int | None = Field(default=None, ge=1, le=365)

    @field_validator("agencies")
    @classmethod
    def _resolve_agencies(cls, v: list[str]) -> list[str]:
        """Expand the acronyms candidates actually type. The board lists only full
        legal names, so 'govtech' would otherwise match nothing at all."""
        out = [CAREERSGOV_AGENCY_ALIASES.get(a.strip().lower(), a) for a in v]
        return _warn_unknown(out, vocab.CAREERSGOV_AGENCIES, "Careers@Gov agency")

    @field_validator("departments")
    @classmethod
    def _check_departments(cls, v: list[str]) -> list[str]:
        return _warn_unknown(v, vocab.CAREERSGOV_DEPARTMENTS, "Careers@Gov department")


class LinkedInFilters(BaseModel):
    easy_apply: bool = False
    company_id: str | None = None


_MODELS: dict[str, type[BaseModel]] = {
    "mycareersfuture": McfFilters,
    "jobstreet": JobStreetFilters,
    "careersgov": CareersGovFilters,
    "linkedin": LinkedInFilters,
}


def filters_for(platform: str, raw: dict | None) -> BaseModel | None:
    """Validate a board's native filter payload. None when nothing was requested."""
    key = platform.lower().replace(" ", "").replace("-", "")
    model = _MODELS.get(key)
    if model is None:
        raise ValueError(f"Unknown platform: {platform}")
    if not raw:
        return None
    return model(**raw)
