"""Pure service functions: parse JD → local match → tailor → cover letter.

Stateless — nothing here touches a database or an auth session. The FastAPI
layer passes the candidate's CV in per request.
"""

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

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
from src.guardrails import GuardrailReport, anonymize, restore, summary_report
from src.guardrails.output import StreamingRestorer, restore_and_verify
from src.matching import match_local
from src.utils.config import settings


@dataclass
class TailoringResult:
    parsed_jd: ParsedJobDescription
    skill_match: SkillMatch
    tailored_resume: TailoredResume | None
    cover_letter: CoverLetter | None
    tailored_resume_path: str | None
    status: str
    errors: list[str]
    guardrail_report: GuardrailReport | None = None

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
            guardrail_report=state.guardrail_report,
        )


_jd_parser: JDParserAgent | None = None
_resume_tailor: ResumeTailorAgent | None = None
_cover_letter_agent: CoverLetterAgent | None = None


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
    source_url: str | None = None,
    platform: str | None = None,
) -> ParsedJobDescription:
    return await _get_jd_parser().parse(jd_text, source_url=source_url, platform=platform)


async def score_jd(
    parsed_jd: ParsedJobDescription,
    master_cv: str | None = None,
) -> SkillMatch:
    """Deterministic local skills match — no LLM call (see `src/matching`)."""
    cv = master_cv if master_cv is not None else settings.get_master_cv()
    return match_local(parsed_jd, cv)


async def tailor_resume(
    parsed_jd: ParsedJobDescription,
    skill_match: SkillMatch,
    master_cv: str | None = None,
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
    job_url: str | None = None,
    platform: str | None = None,
    master_cv: str | None = None,
    style: str = "faithful",
    include_resume: bool = True,
    include_cover_letter: bool = True,
    target_line_budget: float | None = None,
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


_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\n|\n```\s*$")


def _clean_streamed_resume(text: str) -> str:
    """Trim what a non-schema'd model sometimes wraps around the markdown.

    The streaming path has no schema to enforce shape, so rule #9 asks for bare
    markdown — but a stray code fence or a leading blank line is cheap to forgive
    here rather than re-prompt. Anything before the first ``# `` heading is dropped,
    which also removes a "Here is the tailored resume:" preamble.
    """
    text = _FENCE_RE.sub("", text.strip())
    idx = text.find("# ")
    if idx > 0 and not text[:idx].strip().startswith("#"):
        text = text[idx:]
    return text.strip()


async def stream_tailoring(
    jd_text: str,
    *,
    master_cv: str,
    style: str = "faithful",
    target_line_budget: float | None = None,
) -> AsyncIterator[dict]:
    """Tailor with the resume streamed back as it is written.

    Yields dicts: ``{"type": "match", ...}`` once the deterministic match is known
    (so the UI can paint the skill rail before any text arrives), then
    ``{"type": "delta", "text": ...}`` per chunk, then a final ``{"type": "done"}``
    carrying the authoritative resume plus the guardrail report.

    Deliberately not routed through the LangGraph workflow: the graph's value is
    orchestrating parse → match → tailor → cover-letter as discrete completed steps,
    which is the opposite of streaming one of them. The cover letter is a separate
    endpoint anyway. Parse and match are reused verbatim from this module.

    **The deltas are for display only.** The ``done`` payload is the source of truth:
    it is the fully accumulated text put through ``restore_and_verify``, which runs
    the identifier round-trip check and the contact-header safety net.
    """
    parsed = await parse_jd(jd_text)
    match = await score_jd(parsed, master_cv=master_cv)
    yield {"type": "match", "data": match.model_dump(), "parsed_jd": parsed.model_dump()}

    # PII guardrail: the model sees an anonymized CV. Identifiers are restored per
    # chunk so the user never sees a <NAME_0> token in their own resume.
    redaction = anonymize(master_cv)
    restorer = StreamingRestorer(redaction)
    raw: list[str] = []

    async for chunk in _get_resume_tailor().stream_tailor(
        parsed, match, master_cv=redaction.text, style=style,
        target_line_budget=target_line_budget,
    ):
        raw.append(chunk)
        visible = restorer.push(chunk)
        if visible:
            yield {"type": "delta", "text": visible}
    tail = restorer.flush()
    if tail:
        yield {"type": "delta", "text": tail}

    restored, report = restore_and_verify(
        _clean_streamed_resume("".join(raw)), redaction, original_cv=master_cv
    )
    yield {
        "type": "done",
        "tailored_resume_markdown": restored,
        "guardrails": report.model_dump(),
    }


async def cover_letter_for(
    jd_text: str,
    resume_markdown: str,
    master_cv: str | None = None,
) -> tuple[CoverLetter, GuardrailReport]:
    """Standalone cover letter for an (already tailored) resume — parse the JD,
    match against the resume, then generate. Used by the separate CL button.
    Returns the letter plus the PII-guardrail report for that call."""
    parsed = await parse_jd(jd_text)
    # Match on the REAL resume (deterministic, local — no LLM, no third party).
    match = await score_jd(parsed, master_cv=master_cv or resume_markdown)
    # PII guardrail: the cover-letter LLM call sees an anonymized resume; restore
    # the identifiers (e.g. the signed name) locally. Fails open.
    redaction = anonymize(resume_markdown)
    tailored = TailoredResume(markdown_content=redaction.text, changes_made=[], keywords_added=[])
    cover = await generate_cover_letter(parsed, match, tailored)
    restored = cover.model_copy(update={"content": restore(cover.content, redaction)})
    return restored, summary_report(redaction)


