"""State definitions for the LangGraph workflow."""

from dataclasses import dataclass, field
from enum import Enum
from operator import add
from typing import Annotated, Optional

from src.agents.schemas import (
    CoverLetter,
    MatchRecommendation,
    ParsedJobDescription,
    SkillMatch,
    TailoredResume,
)


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    MATCHING = "matching"
    TAILORING = "tailoring"
    GENERATING_COVER_LETTER = "generating_cover_letter"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    APPLYING = "applying"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"
    SKIPPED_BY_USER = "skipped_by_user"


@dataclass
class ApplicationState:
    job_description_text: str = ""
    job_url: Optional[str] = None
    platform: Optional[str] = None

    # The candidate's master CV (markdown). Threaded per-request in the stateless
    # app; falls back to the local master_cv.md file when omitted.
    master_cv: Optional[str] = None

    # Tailoring style: faithful (keep all, reorder/rephrase) | balanced (condense +
    # drop weak content, ~1 page) | aggressive (restructure + cut + hard 1 page).
    style: str = "faithful"

    # Optional explicit rendered-line budget for a "fit to page" re-tailor — when
    # set it overrides the style's length rule (see resume_tailor._budget_rule).
    target_line_budget: Optional[float] = None

    status: WorkflowStatus = WorkflowStatus.PENDING

    parsed_jd: Optional[ParsedJobDescription] = None
    skill_match: Optional[SkillMatch] = None
    tailored_resume: Optional[TailoredResume] = None
    cover_letter: Optional[CoverLetter] = None
    company_context: Optional[str] = None  # Phase 9.3 — web-research used for the cover letter

    tailored_resume_path: Optional[str] = None
    cover_letter_path: Optional[str] = None

    # Annotated with `add` so LangGraph merges errors from parallel nodes.
    errors: Annotated[list[str], add] = field(default_factory=list)

    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Flags the workflow's conditional edges respect: callers can opt out of
    # the resume or cover-letter step to avoid burning Sonnet calls on output
    # they're not going to use (e.g. applications that don't take a cover letter).
    include_resume: bool = True
    include_cover_letter: bool = True

    @property
    def should_apply(self) -> bool:
        if self.skill_match is None:
            return False
        return self.skill_match.recommendation != MatchRecommendation.SKIP

    @property
    def should_generate_cover_letter(self) -> bool:
        if not self.include_cover_letter:
            return False
        if self.skill_match is None:
            return False
        return self.skill_match.overall_score >= 60

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            WorkflowStatus.SUBMITTED,
            WorkflowStatus.FAILED,
            WorkflowStatus.SKIPPED,
            WorkflowStatus.SKIPPED_BY_USER,
            WorkflowStatus.REJECTED,
        }

    def to_dict(self) -> dict:
        return {
            "job_description_text": self.job_description_text[:200] + "...",
            "job_url": self.job_url,
            "platform": self.platform,
            "status": self.status.value,
            "parsed_jd": {
                "company": self.parsed_jd.company,
                "title": self.parsed_jd.title,
            } if self.parsed_jd else None,
            "skill_match": {
                "score": self.skill_match.overall_score,
                "recommendation": self.skill_match.recommendation.value,
            } if self.skill_match else None,
            "has_tailored_resume": self.tailored_resume is not None,
            "has_cover_letter": self.cover_letter is not None,
            "errors": self.errors,
        }
