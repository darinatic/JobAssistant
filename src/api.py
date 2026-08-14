"""FastAPI app — stateless resume-tailoring + job-search API.

No login, no database: the client uploads its CV once (PDF → markdown, returned)
and passes that markdown back on each call. Every endpoint is a pure function of
its request body. See CLAUDE.md for the architecture.
"""

import logging
import time
import uuid
from io import BytesIO
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from src import search as job_search
from src import services
from src.agents.resume_structurer import ResumeDocModel, ResumeStructurerAgent
from src.agents.schemas import ParsedJobDescription, SkillMatch
from src.guardrails import GuardrailReport
from src.logging_setup import configure_logging
from src.matching import extract_skills, gap_analysis, lint_resume
from src.rate_limit import RateLimitMiddleware
from src.search_nlp import SearchFilters
from src.utils.config import settings

configure_logging(settings.log_level)
log = logging.getLogger("resumeagent.api")

# Optional LangSmith tracing (off by default; env-driven, PII-redacted).
from src.observability import configure_langsmith  # noqa: E402  (after configure_logging by design)

configure_langsmith()

app = FastAPI(
    title="ResumeAgent API",
    version="0.3.0",
    description="Stateless resume-tailoring + job-search API.",
)


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:8]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("[%s] %s %s -> 500 (unhandled)", req_id, request.method, request.url.path)
            return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": req_id})
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = req_id
        if request.method != "OPTIONS" or response.status_code >= 400:
            level = logging.WARNING if response.status_code >= 400 else logging.INFO
            log.log(level, "[%s] %s %s -> %d in %.1fms",
                    req_id, request.method, request.url.path, response.status_code, duration_ms)
        return response


app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    per_min=settings.rate_limit_per_min,
    per_day=settings.rate_limit_per_day,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Schemas
# =============================================================================
class HealthResponse(BaseModel):
    status: str


class ResumeParseResponse(BaseModel):
    doc: ResumeDocModel
    chars: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, description="Natural language, e.g. '50 remote AI Engineer jobs on JobStreet this week'")
    resume_markdown: str | None = Field(default=None, description="If given, jobs are ranked by CV relevance")
    filters: SearchFilters | None = Field(default=None, description="Explicit UI dropdown filters; when present the LLM parse is skipped")
    strong_fits_only: bool = Field(default=False, description="Predictor path only: gate to good-fit jobs instead of returning all ranked by fit")


class SearchResponse(BaseModel):
    jobs: list[dict]
    interpreted: dict  # the filters the NL query was parsed into
    filter_report: dict[str, dict] = Field(
        default_factory=dict,
        description="Per-platform: which requested filters were applied, and which were dropped with why",
    )


class ScoreRequest(BaseModel):
    jd_text: str = Field(min_length=20)
    resume_markdown: str = Field(min_length=20)


class InsightsRequest(BaseModel):
    jobs: list[dict]
    resume_markdown: str | None = None


class EnrichRequest(BaseModel):
    jobs: list[dict]  # the listing's cards; those lacking a description get backfilled
    resume_markdown: str | None = None


class JobDescriptionRequest(BaseModel):
    platform: str
    external_id: str = ""
    url: str = ""
    title: str = ""
    resume_markdown: str | None = None


class JobDescriptionResponse(BaseModel):
    description: str
    has_description: bool
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    relevance: int = 0
    fit: int | None = None  # learned fit 0-100 when the predictor is enabled
    # Salary/seniority read off the detail page (LinkedIn) — present when disclosed.
    salary_min: int | None = None
    salary_max: int | None = None
    salary_period: str | None = None
    salary_raw: str | None = None
    experience_raw: str | None = None
    experience_level: str | None = None


class RedFlagsRequest(BaseModel):
    description: str = ""
    company: str = ""
    salary_min: int | None = None
    salary_max: int | None = None
    url: str = ""
    posted_date: str = ""


class RedFlagsResponse(BaseModel):
    flags: list = Field(default_factory=list)


class MatchOut(BaseModel):
    overall_score: int
    recommendation: str
    matched_required: list[str]
    missing_required: list[str]
    matched_preferred: list[str]
    missing_preferred: list[str]
    transferable_skills: list[str]
    reasoning: str
    surfaceable_skills: list[str] = Field(default_factory=list)
    genuine_gaps: list[str] = Field(default_factory=list)
    # Clean gazetteer keyword coverage (the same source the job cards use) — the JD's
    # concrete skills split by whether the CV has them. Meaningful + CV-aware.
    keyword_have: list[str] = Field(default_factory=list)
    keyword_missing: list[str] = Field(default_factory=list)


class TailorRequest(BaseModel):
    jd_text: str = Field(min_length=20)
    resume_markdown: str = Field(min_length=20)
    # Editorial latitude: faithful (keep all, reorder/rephrase) | aggressive
    # (restructure + cut, hard 1pg). Honesty rules are identical at both levels.
    style: Literal["faithful", "aggressive"] | None = None
    concise: bool = False  # legacy flag; concise=True maps to 'aggressive' when style is unset
    include_cover_letter: bool = False  # cover letter is a separate button now
    # "Fit to page": when set, re-tailor with a hard rendered-line budget so a small
    # remainder doesn't waste an under-used trailing page. See page_budget.py.
    target_pages: int | None = Field(default=None, ge=1, le=5)
    # Which LaTeX template the result will be rendered with. Templates differ in
    # density, so the line budget behind `target_pages` is per-template.
    template: Literal["standard", "compact"] = "standard"

    @property
    def effective_style(self) -> str:
        from src.agents.resume_tailor import normalize_style
        return normalize_style(self.style, concise=self.concise)


class CoverLetterRequest(BaseModel):
    jd_text: str = Field(min_length=20)
    resume_markdown: str = Field(min_length=20)


class CoverLetterResponse(BaseModel):
    cover_letter_text: str
    word_count: int
    # PII-guardrail report for the cover-letter LLM call (what was redacted before send).
    guardrails: GuardrailReport | None = None


class ExtractJdRequest(BaseModel):
    url: str = Field(min_length=4)


class ExtractJdResponse(BaseModel):
    jd_text: str


class TailorResponse(BaseModel):
    tailored_resume_markdown: str | None
    cover_letter_text: str | None = None
    cover_letter_word_count: int | None = None
    match: MatchOut
    changes_made: list[str] = Field(default_factory=list)
    keywords_added: list[str] = Field(default_factory=list)
    status: str
    errors: list[str] = Field(default_factory=list)
    # Deterministic honesty check over (CV → tailored): each {kind, value, detail}
    # is a skill/metric/domain in the output not found in the CV. Empty = clean.
    honesty: list[dict] = Field(default_factory=list)
    # PII-guardrail report: what was stripped from the CV before it reached the model,
    # and whether every identifier round-tripped. None when redaction was unavailable.
    guardrails: GuardrailReport | None = None


class ResumePdfRequest(BaseModel):
    resume_markdown: str = Field(min_length=20)
    download: bool = False
    template: Literal["standard", "compact"] = "standard"


class CoverLetterPdfRequest(BaseModel):
    cover_letter_text: str = Field(min_length=20)
    download: bool = False


# =============================================================================
# Helpers
# =============================================================================
def _keyword_coverage(jd_text: str, cv_markdown: str) -> tuple[list[str], list[str]]:
    """Clean gazetteer keyword split — the JD's concrete skills the CV has vs lacks."""
    jd = extract_skills(jd_text)
    cv = extract_skills(cv_markdown)
    return sorted(jd & cv), sorted(jd - cv)


def _match_out(match: SkillMatch, *, surfaceable=None, genuine=None,
               keyword_have=None, keyword_missing=None) -> MatchOut:
    return MatchOut(
        overall_score=match.overall_score,
        recommendation=match.recommendation.value,
        matched_required=match.matched_required,
        missing_required=match.missing_required,
        matched_preferred=match.matched_preferred,
        missing_preferred=match.missing_preferred,
        transferable_skills=match.transferable_skills,
        reasoning=match.reasoning,
        surfaceable_skills=surfaceable or [],
        genuine_gaps=genuine or [],
        keyword_have=keyword_have or [],
        keyword_missing=keyword_missing or [],
    )


async def _render_pdf_or_503(fn, *args) -> bytes:
    """Map a missing Tectonic toolchain to a clear 503, a compile failure to 500."""
    from src.utils.latex_renderer import LatexCompileError, LatexUnavailable
    try:
        return await fn(*args)
    except LatexUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except LatexCompileError as e:
        log.error("LaTeX compile failed: %s", e)
        raise HTTPException(status_code=500, detail="PDF rendering failed") from e


# =============================================================================
# Endpoints
# =============================================================================
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/resume/parse", response_model=ResumeParseResponse)
async def resume_parse(file: UploadFile = File(...)) -> ResumeParseResponse:
    """PDF/DOCX resume → structured section model (MarkItDown text → one Haiku
    structuring pass). A scanned PDF (no extractable text) falls back to Claude's
    vision to OCR + structure it. Returned to the client; never stored."""
    from markitdown import MarkItDown

    raw = await file.read()
    is_docx = (file.filename or "").lower().endswith(".docx")
    ext = ".docx" if is_docx else ".pdf"
    try:
        result = MarkItDown().convert_stream(BytesIO(raw), file_extension=ext)
        text = result.text_content
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse resume: {e}") from e

    agent = ResumeStructurerAgent()
    if len(text.strip()) < 100:
        if is_docx:
            # A DOCX is always text-based; too little text means an empty/broken file.
            raise HTTPException(status_code=422, detail="This DOCX has almost no text — is it the right file?")
        doc = await agent.structure_from_file(raw, "application/pdf")  # OCR the scan
    else:
        doc = await agent.structure(text)
    return ResumeParseResponse(doc=doc, chars=len(text))


@app.get("/search/capabilities")
async def search_capabilities() -> dict:
    """What each board can actually filter, plus the vocabularies for its native filters.

    Published so the UI can grey out a filter the selected boards cannot honour
    (instead of accepting the click and dropping it), and so an agent calling this
    service can discover valid values rather than guessing at them.
    """
    from src.scrapers import vocabularies as vocab
    from src.scrapers.capabilities import ALL_CAPABILITIES

    boards = {
        name: {
            "common": {k: str(v) for k, v in caps.common.items()},
            "notes": caps.notes,
            "native_filters": (
                caps.filters_model.model_json_schema() if caps.filters_model else None
            ),
        }
        for name, caps in ALL_CAPABILITIES.items()
    }
    return {
        "boards": boards,
        "vocabularies": {
            "mcf_categories": list(vocab.MCF_CATEGORIES),
            "mcf_employment_types": list(vocab.MCF_EMPLOYMENT_TYPES),
            "jobstreet_work_types": sorted(vocab.JOBSTREET_WORK_TYPES),
            "jobstreet_work_arrangements": sorted(vocab.JOBSTREET_WORK_ARRANGEMENTS),
            "careersgov_agencies": list(vocab.CAREERSGOV_AGENCIES),
            "careersgov_departments": list(vocab.CAREERSGOV_DEPARTMENTS),
            "careersgov_employment_types": list(vocab.CAREERSGOV_EMPLOYMENT_TYPES),
        },
    }


def _filter_report_for(q) -> dict[str, dict]:
    """Which of this query's filters each targeted board honoured, and which it dropped."""
    return job_search.build_filter_report(
        q.platforms or job_search.DEFAULT_PLATFORMS,
        {
            "date_posted": q.date_posted,
            "experience_levels": q.experience_levels,
            "remote_options": q.remote_options,
            "min_salary": q.min_salary,
        },
    )


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    """Natural-language multi-platform job scrape. The query is parsed into filters
    (Haiku), then scraped live. Stateless — results are returned, not saved."""
    from src.search_nlp import build_query, parse_search_query

    q = build_query(req.filters, req.query) if req.filters is not None else await parse_search_query(req.query)
    jobs = await job_search.search_jobs(
        keyword=q.keyword,
        location=q.location,
        platforms=q.platforms or None,
        max_jobs=q.max_jobs,
        date_posted=q.date_posted,
        experience_levels=q.experience_levels,
        remote_options=q.remote_options,
        min_salary=q.min_salary,
        platform_filters=q.platform_filters,
        master_cv=req.resume_markdown,
    )
    return SearchResponse(
        jobs=jobs, interpreted=q.model_dump(), filter_report=_filter_report_for(q),
    )


@app.post("/search/stream")
async def search_stream(req: SearchRequest) -> StreamingResponse:
    """Progressive search — NDJSON stream: one `interpreted` line, then a `job`
    line per result as it's scraped, then `done`. Lets the UI render incrementally."""
    import json

    from src.search_nlp import build_query, parse_search_query

    q = build_query(req.filters, req.query) if req.filters is not None else await parse_search_query(req.query)

    from src import match_predictor

    async def gen():
        yield json.dumps({"type": "interpreted", "data": q.model_dump()}) + "\n"
        # Emitted before any job so the client can warn about a dropped filter
        # immediately, rather than after a full scrape that looks like "no matches".
        yield json.dumps({"type": "filter_report", "data": _filter_report_for(q)}) + "\n"
        floor = False
        if match_predictor.is_enabled() and req.resume_markdown:
            # Predictor on: score every job and surface only good-fit ones.
            async for msg in job_search.search_jobs_gated_stream(
                keyword=q.keyword, location=q.location, platforms=q.platforms or None,
                max_jobs=q.max_jobs, date_posted=q.date_posted,
                experience_levels=q.experience_levels, remote_options=q.remote_options,
                min_salary=q.min_salary, platform_filters=q.platform_filters,
                master_cv=req.resume_markdown, gate=req.strong_fits_only,
            ):
                if msg.get("type") == "job" and msg["data"].get("below_threshold"):
                    floor = True
                yield json.dumps(msg) + "\n"
        else:
            # Predictor off: the original lazy pipeline (cards first, enrich later).
            async for job in job_search.search_jobs_stream(
                keyword=q.keyword, location=q.location, platforms=q.platforms or None,
                max_jobs=q.max_jobs, date_posted=q.date_posted,
                experience_levels=q.experience_levels, remote_options=q.remote_options,
                min_salary=q.min_salary, platform_filters=q.platform_filters,
                master_cv=req.resume_markdown,
            ):
                yield json.dumps({"type": "job", "data": job}) + "\n"
        yield json.dumps({"type": "done", "floor": floor}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/jobs/enrich/stream")
async def enrich_stream(req: EnrichRequest) -> StreamingResponse:
    """Backfill descriptions for cards that lack them, streaming NDJSON skill updates.

    Called after `/search/stream` so the listing paints fast, then fills in every
    job's keywords progressively. One `update` line per job, then `done`.
    """
    import json

    async def gen():
        async for upd in job_search.enrich_descriptions_stream(req.jobs, req.resume_markdown):
            yield json.dumps({"type": "update", "data": upd}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/job/description", response_model=JobDescriptionResponse)
async def job_description(req: JobDescriptionRequest) -> JobDescriptionResponse:
    """On-demand fetch of a single job's full description (used when a job is opened).

    Search returns LinkedIn/JobStreet cards without descriptions to stay fast; the
    drawer calls this to fill one in, then (with a CV) re-derives the skill overlap.
    """
    detail = await job_search.fetch_job_detail(req.platform, req.external_id, req.url)
    text = detail.description
    have: list[str] = []
    missing: list[str] = []
    relevance = 0
    fit = None
    if text and req.resume_markdown:
        cv_skills = extract_skills(req.resume_markdown)
        jd_skills = extract_skills(text)
        have = sorted(jd_skills & cv_skills)
        missing = sorted(jd_skills - cv_skills)
        relevance = round(100 * len(have) / len(jd_skills)) if jd_skills else 0
        # Learned fit (same signal the search cards rank by; None when off).
        fit = await job_search._fit_pct(req.resume_markdown, req.title, text)
    return JobDescriptionResponse(
        description=text, has_description=bool(text.strip()),
        matched_skills=have, missing_skills=missing, relevance=relevance, fit=fit,
        salary_min=detail.salary_min, salary_max=detail.salary_max,
        salary_period=detail.salary_period, salary_raw=detail.salary_raw,
        experience_raw=detail.experience_raw, experience_level=detail.experience_level,
    )


@app.post("/job/red-flags", response_model=RedFlagsResponse)
async def job_red_flags(req: RedFlagsRequest) -> RedFlagsResponse:
    """Deterministic legitimacy red-flags for a posting (advisory, never blocks)."""
    from src.intel.red_flags import scan_red_flags
    flags = scan_red_flags({
        "description": req.description, "company": req.company,
        "salary_min": req.salary_min, "salary_max": req.salary_max,
        "url": req.url, "posted_date": req.posted_date,
    })
    return RedFlagsResponse(flags=flags)


@app.post("/score", response_model=MatchOut)
async def score(req: ScoreRequest) -> MatchOut:
    """Parse a JD (Haiku) and score it against the CV with the local matcher."""
    parsed = await services.parse_jd(req.jd_text)
    match = await services.score_jd(parsed, master_cv=req.resume_markdown)
    gaps = gap_analysis(parsed, req.resume_markdown)
    have, missing = _keyword_coverage(req.jd_text, req.resume_markdown)
    return _match_out(match, surfaceable=gaps.surfaceable_skills, genuine=gaps.genuine_gaps,
                      keyword_have=have, keyword_missing=missing)


@app.post("/insights")
async def insights(req: InsightsRequest) -> dict:
    """Deterministic skill-demand aggregation over a found-jobs set (no LLM)."""
    from src.insights import aggregate_jobs

    return aggregate_jobs(req.jobs, req.resume_markdown)


@app.post("/tailor", response_model=TailorResponse)
async def tailor(req: TailorRequest) -> TailorResponse:
    """Full tailoring pipeline. Re-running with a different style re-tailors from
    the master CV (there is no feedback/refine loop — users edit the markdown or
    pick a more aggressive style)."""
    # "Fit to page": budget = target_pages × the per-page safety-margin line target
    # of the template this will actually be rendered with (densities differ).
    from src.utils.page_budget import budget_for
    page_target = budget_for(req.template).target
    target_line_budget = req.target_pages * page_target if req.target_pages else None
    result = await services.run_full_tailoring(
        req.jd_text, master_cv=req.resume_markdown,
        style=req.effective_style, include_cover_letter=req.include_cover_letter,
        target_line_budget=target_line_budget,
    )

    if result.skill_match is None:
        log.warning("Tailoring failed for JD: %s", result.errors)
        raise HTTPException(
            status_code=422,
            detail="Couldn't process this job description — try another posting or paste the JD text manually.",
        )

    tailored_md = result.tailored_resume.markdown_content if result.tailored_resume else None
    gaps = gap_analysis(result.parsed_jd, req.resume_markdown)
    have, missing = _keyword_coverage(req.jd_text, req.resume_markdown)
    # Deterministic honesty check on the output — advisory, never blocks the response.
    honesty = lint_resume(req.resume_markdown, tailored_md).as_dicts() if tailored_md else []

    return TailorResponse(
        tailored_resume_markdown=tailored_md,
        cover_letter_text=result.cover_letter.content if result.cover_letter else None,
        cover_letter_word_count=result.cover_letter.word_count if result.cover_letter else None,
        match=_match_out(result.skill_match, surfaceable=gaps.surfaceable_skills, genuine=gaps.genuine_gaps,
                         keyword_have=have, keyword_missing=missing),
        changes_made=result.tailored_resume.changes_made if result.tailored_resume else [],
        keywords_added=result.tailored_resume.keywords_added if result.tailored_resume else [],
        status=result.status,
        errors=result.errors,
        honesty=honesty,
        guardrails=result.guardrail_report,
    )


@app.post("/tailor/stream")
async def tailor_stream(req: TailorRequest) -> StreamingResponse:
    """Same pipeline as `/tailor`, streamed as NDJSON so the resume paints as it is
    written: a `match` line once the deterministic match is known, a `delta` line per
    chunk, then `done` with the authoritative resume + advisory panels.

    The deltas are for display only — `done` carries the verified text (identifiers
    round-tripped, contact header safety-netted), so the client should adopt that as
    its final state rather than the concatenated deltas.
    """
    import json

    from src.utils.page_budget import budget_for

    page_target = budget_for(req.template).target
    target_line_budget = req.target_pages * page_target if req.target_pages else None

    async def gen():
        tailored_md = ""
        match_out: MatchOut | None = None
        guardrails: dict | None = None
        try:
            async for msg in services.stream_tailoring(
                req.jd_text, master_cv=req.resume_markdown,
                style=req.effective_style, target_line_budget=target_line_budget,
            ):
                if msg["type"] == "match":
                    # Build the SAME enriched MatchOut the `done` event carries. A raw
                    # SkillMatch has no surfaceable_skills/genuine_gaps/keyword_* , and
                    # the client renders those immediately — emitting the bare model
                    # crashed the tailor stage on `undefined.length`. One shape, both
                    # events. Reuses the stream's own parse/match, so no extra LLM call;
                    # the gap split and keyword coverage are deterministic (~1ms).
                    parsed = ParsedJobDescription.model_validate(msg["parsed_jd"])
                    skill_match = SkillMatch.model_validate(msg["data"])
                    gaps = gap_analysis(parsed, req.resume_markdown)
                    have, missing = _keyword_coverage(req.jd_text, req.resume_markdown)
                    match_out = _match_out(
                        skill_match, surfaceable=gaps.surfaceable_skills,
                        genuine=gaps.genuine_gaps, keyword_have=have, keyword_missing=missing,
                    )
                    yield json.dumps({"type": "match", "data": match_out.model_dump()}) + "\n"
                    continue
                if msg["type"] == "done":
                    tailored_md = msg["tailored_resume_markdown"]
                    guardrails = msg["guardrails"]
                    continue  # re-emitted below with the honesty lint
                yield json.dumps(msg) + "\n"
        except Exception as e:  # noqa: BLE001 — a stream can't raise an HTTP status midway
            log.warning("Streaming tailor failed: %s", e)
            yield json.dumps({"type": "error", "detail": str(e)}) + "\n"
            return

        if match_out is None:
            yield json.dumps({"type": "error", "detail": "Couldn't process this job description."}) + "\n"
            return

        # The honesty lint can only run once the draft is complete.
        honesty = lint_resume(req.resume_markdown, tailored_md).as_dicts() if tailored_md else []
        yield json.dumps({
            "type": "done",
            "tailored_resume_markdown": tailored_md,
            "match": match_out.model_dump(),
            "honesty": honesty,
            "guardrails": guardrails,
        }) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/cover-letter", response_model=CoverLetterResponse)
async def cover_letter(req: CoverLetterRequest) -> CoverLetterResponse:
    """Generate a cover letter for an (already tailored) resume + JD."""
    cl, guardrails = await services.cover_letter_for(req.jd_text, req.resume_markdown)
    return CoverLetterResponse(
        cover_letter_text=cl.content, word_count=cl.word_count, guardrails=guardrails
    )


@app.post("/extract-jd", response_model=ExtractJdResponse)
async def extract_jd(req: ExtractJdRequest) -> ExtractJdResponse:
    """Scrape a job description from a URL (best-effort)."""
    from src.jd_extract import extract_jd_from_url

    try:
        return ExtractJdResponse(jd_text=await extract_jd_from_url(req.url))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.post("/tailored/resume.pdf")
async def resume_pdf(req: ResumePdfRequest) -> Response:
    from src.utils.latex_renderer import resume_markdown_to_pdf_bytes
    from src.utils.pdf_converter import candidate_name_from_markdown

    pdf_bytes = await _render_pdf_or_503(
        resume_markdown_to_pdf_bytes, req.resume_markdown,
        candidate_name_from_markdown(req.resume_markdown), req.template,
    )
    disposition = "attachment" if req.download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="resume.pdf"'},
    )


@app.post("/tailored/cover-letter.pdf")
async def cover_letter_pdf(req: CoverLetterPdfRequest) -> Response:
    from src.utils.latex_renderer import cover_letter_to_pdf_bytes

    pdf_bytes = await _render_pdf_or_503(cover_letter_to_pdf_bytes, req.cover_letter_text)
    disposition = "attachment" if req.download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="cover-letter.pdf"'},
    )


# =============================================================================
# Static SPA — serve the built frontend from the same origin (production single
# image). Registered LAST so it never shadows an API route. No-op in dev, where
# the frontend runs under Vite and this dist/ folder doesn't exist.
# =============================================================================
from pathlib import Path as _Path  # noqa: E402

from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_DIST = _Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")  # SPA fallback
