"""Pydantic schemas for agent inputs and outputs.

Field descriptions are intentionally verbose: they're consumed by Claude's
structured-output mode as part of the tool schema.
"""

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Claude's structured output occasionally leaks the closing tag of a field (and the
# tool-call wrapper) INTO the field value, e.g. work_arrangement="unspecified</work_
# arrangement>\n</invoke>". That breaks enum validation and can silently pollute string
# fields. Strip from the first stray closing tag onward.
_TAG_LEAK = re.compile(r"</[A-Za-z_][\w-]*>[\s\S]*$")


def _strip_tag_leak(s: str) -> str:
    return _TAG_LEAK.sub("", s).strip()


class ExperienceLevel(str, Enum):
    ENTRY = "entry"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"


class WorkArrangement(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    FLEXIBLE = "flexible"
    UNSPECIFIED = "unspecified"


class RedFlag(BaseModel):
    flag: str = Field(description="Brief description of the red flag")
    severity: str = Field(description="low, medium, or high")
    reason: str = Field(description="Why this might be a concern for the candidate")


class ParsedJobDescription(BaseModel):
    company: str = Field(description="Company name")
    title: str = Field(description="Job title")
    location: str = Field(description="Job location (city/country)")
    work_arrangement: WorkArrangement = Field(
        default=WorkArrangement.UNSPECIFIED,
        description="Remote, hybrid, onsite, or flexible",
    )

    required_skills: list[str] = Field(
        default_factory=list,
        description="Skills explicitly marked as required or must-have",
    )
    preferred_skills: list[str] = Field(
        default_factory=list,
        description="Skills marked as nice-to-have or preferred",
    )
    experience_required: str = Field(
        description="Experience requirement as stated (e.g., '2-4 years')"
    )
    experience_level: ExperienceLevel = Field(description="Classified experience level")
    education_required: Optional[str] = Field(
        default=None,
        description="Education requirements if specified",
    )

    responsibilities: list[str] = Field(
        default_factory=list,
        description="Key job responsibilities and duties",
    )
    tech_stack: list[str] = Field(
        default_factory=list,
        description="Specific technologies, frameworks, and tools mentioned",
    )

    salary_range: Optional[str] = Field(default=None, description="Salary range if disclosed")
    benefits: list[str] = Field(
        default_factory=list,
        description="Benefits mentioned (equity, health, etc.)",
    )

    red_flags: list[RedFlag] = Field(
        default_factory=list,
        description="Potential concerns for the candidate",
    )
    keywords_for_resume: list[str] = Field(
        default_factory=list,
        description="Key terms to incorporate into tailored resume",
    )

    source_url: Optional[str] = Field(default=None, description="URL where the job was found")
    platform: Optional[str] = Field(
        default=None,
        description="Platform (LinkedIn, Jobstreet, MyCareersFuture, direct)",
    )

    # Strip structured-output tag leakage from the enum fields (a leaked '</...>'
    # made the value 'unspecified</work_arrangement>...' and failed enum validation,
    # crashing the whole tailor pipeline for that JD).
    @field_validator("work_arrangement", "experience_level", mode="before")
    @classmethod
    def _clean_enum(cls, v):
        return _strip_tag_leak(v).lower() if isinstance(v, str) else v

    # Same leakage can silently pollute freeform string fields — clean them too.
    @field_validator(
        "company", "title", "location", "experience_required",
        "education_required", "salary_range", mode="before",
    )
    @classmethod
    def _clean_str(cls, v):
        return _strip_tag_leak(v) if isinstance(v, str) else v

    # Claude's structured output occasionally emits the string "null" (or a bare
    # string) for a list field; coerce those to a valid list so the whole parse
    # doesn't blow up on one malformed field.
    @field_validator(
        "required_skills", "preferred_skills", "responsibilities",
        "tech_stack", "benefits", "keywords_for_resume", mode="before",
    )
    @classmethod
    def _coerce_str_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [] if v.strip().lower() in ("null", "none", "") else [v]
        return v

    @field_validator("red_flags", mode="before")
    @classmethod
    def _coerce_obj_list(cls, v):
        if v is None or (isinstance(v, str) and v.strip().lower() in ("null", "none", "")):
            return []
        return v


class MatchRecommendation(str, Enum):
    APPLY = "apply"
    STRETCH = "stretch"
    SKIP = "skip"


class SkillMatch(BaseModel):
    overall_score: int = Field(ge=0, le=100, description="Overall match score from 0-100")
    matched_required: list[str] = Field(
        default_factory=list,
        description="Required skills the candidate has",
    )
    matched_preferred: list[str] = Field(
        default_factory=list,
        description="Preferred skills the candidate has",
    )
    missing_required: list[str] = Field(
        default_factory=list,
        description="Required skills the candidate lacks",
    )
    missing_preferred: list[str] = Field(
        default_factory=list,
        description="Preferred skills the candidate lacks",
    )
    transferable_skills: list[str] = Field(
        default_factory=list,
        description="Candidate skills that could transfer to requirements",
    )
    recommendation: MatchRecommendation = Field(
        description="Whether to apply, stretch-apply, or skip",
    )
    reasoning: str = Field(description="Brief explanation of the match assessment")


class TailoredResume(BaseModel):
    markdown_content: str = Field(description="The tailored resume in markdown format")
    changes_made: list[str] = Field(
        default_factory=list,
        description="Summary of changes made to the original resume",
    )
    keywords_added: list[str] = Field(
        default_factory=list,
        description="Keywords incorporated from the JD",
    )
    sections_reordered: bool = Field(
        default=False,
        description="Whether sections or bullets were reordered",
    )


class CoverLetter(BaseModel):
    content: str = Field(description="The cover letter text")
    word_count: int = Field(description="Word count of the cover letter")
    personalization_points: list[str] = Field(
        default_factory=list,
        description="Specific personalizations made for this company/role",
    )


