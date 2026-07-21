"""Pure service functions: parse JD → local match → tailor → cover letter.

Stateless — nothing here touches a database or an auth session. The FastAPI
layer passes the candidate's CV in per request.
"""

from dataclasses import dataclass
from typing import Optional

from src.agents import (
    CoverLetterAgent,
    JDParserAgent,
    ResumeTailorAgent,
)
from src.agents.schemas import (
    CoverLetter,
    ParsedJobDescription,
    SkillMatch,
    TailoredResume,
)
from src.graph import process_job
from src.graph.state import ApplicationState
from src.matching import match_local
from src.utils.config import settings


@dataclass
class TailoringResult:
    parsed_jd: ParsedJobDescription
    skill_match: SkillMatch
    tailored_resume: Optional[TailoredResume]
    cover_letter: Optional[CoverLetter]
    tailored_resume_path: Optional[str]
    status: str
    errors: list[str]

    @classmethod
    def from_state(cls, state: ApplicationState) -> "TailoringResult":
        return cls(
            parsed_jd=state.parsed_jd,
            skill_match=state.skill_match,
            tailored_resume=state.tailored_resume,
            cover_letter=state.cover_letter,
            tailored_resume_path=state.tailored_resume_path,
            status=state.status.value,
            errors=list(state.errors),
        )


_jd_parser: Optional[JDParserAgent] = None
_resume_tailor: Optional[ResumeTailorAgent] = None
_cover_letter_agent: Optional[CoverLetterAgent] = None


def _get_jd_parser() -> JDParserAgent:
    global _jd_parser
    if _jd_parser is None:
        _jd_parser = JDParserAgent()
    return _jd_parser


def _get_resume_tailor() -> ResumeTailorAgent:
    global _resume_tailor
    if _resume_tailor is None:
        _resume_tailor = ResumeTailorAgent()
    return _resume_tailor


def _get_cover_letter_agent() -> CoverLetterAgent:
    global _cover_letter_agent
    if _cover_letter_agent is None:
        _cover_letter_agent = CoverLetterAgent()
    return _cover_letter_agent


async def parse_jd(
    jd_text: str,
    source_url: Optional[str] = None,
    platform: Optional[str] = None,
) -> ParsedJobDescription:
    return await _get_jd_parser().parse(jd_text, source_url=source_url, platform=platform)


async def score_jd(
    parsed_jd: ParsedJobDescription,
    master_cv: Optional[str] = None,
) -> SkillMatch:
    """Deterministic local skills match — no LLM call (see `src/matching`)."""
    cv = master_cv if master_cv is not None else settings.get_master_cv()
    return match_local(parsed_jd, cv)


async def tailor_resume(
    parsed_jd: ParsedJobDescription,
    skill_match: SkillMatch,
    master_cv: Optional[str] = None,
) -> TailoredResume:
    return await _get_resume_tailor().tailor(parsed_jd, skill_match, master_cv=master_cv)


async def generate_cover_letter(
    parsed_jd: ParsedJobDescription,
    skill_match: SkillMatch,
    tailored_resume: TailoredResume,
) -> CoverLetter:
    return await _get_cover_letter_agent().generate(
        parsed_jd=parsed_jd,
        skill_match=skill_match,
        tailored_resume=tailored_resume,
    )


async def run_full_tailoring(
    jd_text: str,
    job_url: Optional[str] = None,
    platform: Optional[str] = None,
    master_cv: Optional[str] = None,
    style: str = "faithful",
    include_resume: bool = True,
    include_cover_letter: bool = True,
    target_line_budget: Optional[float] = None,
) -> TailoringResult:
    """Full pipeline: parse → match → tailor → cover letter.

    The two ``include_*`` flags route the LangGraph conditional edges: setting
    one to False skips the corresponding Sonnet node entirely. ``target_line_budget``
    (optional) drives a "fit to page" re-tailor with an explicit rendered-line budget.
    """
    state = await process_job(
        jd_text=jd_text, job_url=job_url, platform=platform, master_cv=master_cv,
        style=style, include_resume=include_resume, include_cover_letter=include_cover_letter,
        target_line_budget=target_line_budget,
    )
    return TailoringResult.from_state(state)


async def cover_letter_for(
    jd_text: str,
    resume_markdown: str,
    master_cv: Optional[str] = None,
) -> CoverLetter:
    """Standalone cover letter for an (already tailored) resume — parse the JD,
    match against the resume, then generate. Used by the separate CL button."""
    parsed = await parse_jd(jd_text)
    match = await score_jd(parsed, master_cv=master_cv or resume_markdown)
    tailored = TailoredResume(markdown_content=resume_markdown, changes_made=[], keywords_added=[])
    return await generate_cover_letter(parsed, match, tailored)


