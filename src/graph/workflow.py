"""LangGraph workflow: parse JD → match → tailor → cover letter → review."""

from datetime import datetime
from typing import Literal

from langgraph.graph import StateGraph, END

from src.agents import (
    CoverLetterAgent,
    JDParserAgent,
    ResumeTailorAgent,
)
from src.graph.state import ApplicationState, WorkflowStatus
from src.matching import match_local
from src.utils.config import settings


jd_parser = JDParserAgent()
resume_tailor = ResumeTailorAgent()
cover_letter_agent = CoverLetterAgent()


async def parse_jd_node(state: ApplicationState) -> ApplicationState:
    state.status = WorkflowStatus.PARSING
    state.updated_at = datetime.now().isoformat()

    try:
        state.parsed_jd = await jd_parser.parse(
            jd_text=state.job_description_text,
            source_url=state.job_url,
            platform=state.platform,
        )
    except Exception as e:
        state.errors.append(f"JD parsing failed: {e}")
        state.status = WorkflowStatus.FAILED

    return state


async def match_skills_node(state: ApplicationState) -> ApplicationState:
    state.status = WorkflowStatus.MATCHING
    state.updated_at = datetime.now().isoformat()

    if state.parsed_jd is None:
        state.errors.append("Cannot match skills: JD not parsed")
        state.status = WorkflowStatus.FAILED
        return state

    try:
        # Deterministic local match (no LLM). Uses the request's CV when threaded
        # (stateless app), else the local master_cv.md file.
        cv = state.master_cv if state.master_cv is not None else settings.get_master_cv()
        state.skill_match = match_local(state.parsed_jd, cv)
    except Exception as e:
        state.errors.append(f"Skills matching failed: {e}")
        state.status = WorkflowStatus.FAILED

    return state


async def tailor_resume_node(state: ApplicationState) -> ApplicationState:
    state.status = WorkflowStatus.TAILORING
    state.updated_at = datetime.now().isoformat()

    if state.parsed_jd is None or state.skill_match is None:
        state.errors.append("Cannot tailor resume: missing JD or match data")
        state.status = WorkflowStatus.FAILED
        return state

    try:
        tailored = await resume_tailor.tailor(
            state.parsed_jd, state.skill_match, master_cv=state.master_cv, style=state.style,
            target_line_budget=state.target_line_budget,
        )
        state.tailored_resume = tailored
        filepath = await resume_tailor.save_tailored_resume(tailored, state.parsed_jd)
        state.tailored_resume_path = str(filepath)
    except Exception as e:
        state.errors.append(f"Resume tailoring failed: {e}")
        state.status = WorkflowStatus.FAILED

    return state


async def generate_cover_letter_node(state: ApplicationState) -> ApplicationState:
    state.status = WorkflowStatus.GENERATING_COVER_LETTER
    state.updated_at = datetime.now().isoformat()

    if not settings.generate_cover_letters:
        return state

    if state.parsed_jd is None or state.skill_match is None or state.tailored_resume is None:
        state.errors.append("Cannot generate cover letter: missing required data")
        return state

    try:
        state.cover_letter = await cover_letter_agent.generate(
            parsed_jd=state.parsed_jd,
            skill_match=state.skill_match,
            tailored_resume=state.tailored_resume,
        )
    except Exception as e:
        # Non-fatal — proceed without cover letter.
        state.errors.append(f"Cover letter generation failed: {e}")

    return state


async def prepare_review_node(state: ApplicationState) -> ApplicationState:
    state.status = WorkflowStatus.PENDING_REVIEW
    state.updated_at = datetime.now().isoformat()
    return state


def should_continue_after_parsing(
    state: ApplicationState,
) -> Literal["match_skills", "end"]:
    if state.status == WorkflowStatus.FAILED or state.parsed_jd is None:
        return "end"
    return "match_skills"


def should_continue_after_matching(
    state: ApplicationState,
) -> Literal["tailor_resume", "generate_cover_letter", "end"]:
    if state.status == WorkflowStatus.FAILED or state.skill_match is None:
        return "end"
    # A user who asked to tailor gets a tailored resume regardless of score —
    # no auto-skip on low matches (the score is advisory, shown alongside).
    if not state.include_resume:
        if state.include_cover_letter and state.skill_match.overall_score >= 60:
            return "generate_cover_letter"
        return "end"
    return "tailor_resume"


def should_generate_cover_letter(
    state: ApplicationState,
) -> Literal["generate_cover_letter", "prepare_review", "end"]:
    if state.status == WorkflowStatus.FAILED or state.tailored_resume is None:
        return "end"
    if state.should_generate_cover_letter:
        return "generate_cover_letter"
    return "prepare_review"


def after_cover_letter(state: ApplicationState) -> Literal["prepare_review", "end"]:
    if state.status == WorkflowStatus.FAILED:
        return "end"
    return "prepare_review"


def build_tailoring_workflow() -> StateGraph:
    workflow = StateGraph(ApplicationState)

    workflow.add_node("parse_jd", parse_jd_node)
    workflow.add_node("match_skills", match_skills_node)
    workflow.add_node("tailor_resume", tailor_resume_node)
    workflow.add_node("generate_cover_letter", generate_cover_letter_node)
    workflow.add_node("prepare_review", prepare_review_node)

    workflow.set_entry_point("parse_jd")

    workflow.add_conditional_edges(
        "parse_jd",
        should_continue_after_parsing,
        {"match_skills": "match_skills", "end": END},
    )
    workflow.add_conditional_edges(
        "match_skills",
        should_continue_after_matching,
        {
            "tailor_resume": "tailor_resume",
            "generate_cover_letter": "generate_cover_letter",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "tailor_resume",
        should_generate_cover_letter,
        {"generate_cover_letter": "generate_cover_letter", "prepare_review": "prepare_review", "end": END},
    )
    workflow.add_conditional_edges(
        "generate_cover_letter",
        after_cover_letter,
        {"prepare_review": "prepare_review", "end": END},
    )

    workflow.add_edge("prepare_review", END)

    return workflow


def create_tailoring_app():
    return build_tailoring_workflow().compile()


async def process_job(
    jd_text: str,
    job_url: str | None = None,
    platform: str | None = None,
    master_cv: str | None = None,
    style: str = "faithful",
    include_resume: bool = True,
    include_cover_letter: bool = True,
    target_line_budget: float | None = None,
) -> ApplicationState:
    app = create_tailoring_app()

    initial_state = ApplicationState(
        job_description_text=jd_text,
        job_url=job_url,
        platform=platform,
        master_cv=master_cv,
        style=style,
        target_line_budget=target_line_budget,
        include_resume=include_resume,
        include_cover_letter=include_cover_letter,
        created_at=datetime.now().isoformat(),
    )

    result = await app.ainvoke(initial_state)

    # LangGraph can return a dict rather than the dataclass instance.
    if isinstance(result, dict):
        return ApplicationState(
            job_description_text=result.get("job_description_text", jd_text),
            job_url=result.get("job_url", job_url),
            platform=result.get("platform", platform),
            master_cv=result.get("master_cv", master_cv),
            style=result.get("style", style),
            target_line_budget=result.get("target_line_budget", target_line_budget),
            status=result.get("status", WorkflowStatus.PENDING),
            parsed_jd=result.get("parsed_jd"),
            skill_match=result.get("skill_match"),
            tailored_resume=result.get("tailored_resume"),
            cover_letter=result.get("cover_letter"),
            company_context=result.get("company_context"),
            tailored_resume_path=result.get("tailored_resume_path"),
            cover_letter_path=result.get("cover_letter_path"),
            errors=result.get("errors", []),
            created_at=result.get("created_at"),
            updated_at=result.get("updated_at"),
            include_resume=result.get("include_resume", include_resume),
            include_cover_letter=result.get("include_cover_letter", include_cover_letter),
        )

    return result


def process_job_sync(
    jd_text: str,
    job_url: str | None = None,
    platform: str | None = None,
) -> ApplicationState:
    import asyncio
    return asyncio.run(process_job(jd_text, job_url, platform))
