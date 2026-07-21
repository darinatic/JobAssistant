"""FastAPI app — stateless resume-tailoring + job-search API.

No login, no database: the client uploads its CV once (PDF → markdown, returned)
and passes that markdown back on each call. Every endpoint is a pure function of
its request body. See CLAUDE.md for the architecture.
"""

import logging
import time
import uuid
from io import BytesIO
from typing import Literal, Optional

from fastapi import Body, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from src import search as job_search
from src import services
from src.agents.schemas import ParsedJobDescription, SkillMatch
from src.logging_setup import configure_logging
from src.matching import extract_skills, gap_analysis, lint_resume
from src.rate_limit import RateLimitMiddleware
from src.utils.config import settings

configure_logging(settings.log_level)
log = logging.getLogger("resumeagent.api")

# Optional LangSmith tracing (off by default; env-driven, PII-redacted).
from src.observability import configure_langsmith
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
    markdown: str
    chars: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, description="Natural language, e.g. '50 remote AI Engineer jobs on JobStreet this week'")
    resume_markdown: Optional[str] = Field(default=None, description="If given, jobs are ranked by CV relevance")


class SearchResponse(BaseModel):
    jobs: list[dict]
    interpreted: dict  # the filters the NL query was parsed into


class ScoreRequest(BaseModel):
    jd_text: str = Field(min_length=20)
    resume_markdown: str = Field(min_length=20)


class InsightsRequest(BaseModel):
    jobs: list[dict]
    resume_markdown: Optional[str] = None


class EnrichRequest(BaseModel):
    jobs: list[dict]  # the listing's cards; those lacking a description get backfilled
    resume_markdown: Optional[str] = None


class JobDescriptionRequest(BaseModel):
    platform: str
    external_id: str = ""
    url: str = ""
    title: str = ""
    resume_markdown: Optional[str] = None


class JobDescriptionResponse(BaseModel):
    description: str
    has_description: bool
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    relevance: int = 0
    fit: Optional[int] = None  # learned fit 0-100 when the predictor is enabled


class RedFlagsRequest(BaseModel):
    description: str = ""
    company: str = ""
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
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
    # Editorial latitude: faithful (keep all) | balanced (condense, ~1pg) | aggressive
    # (restructure + cut, hard 1pg). Honesty rules are identical at every level.
    style: Optional[Literal["faithful", "balanced", "aggressive"]] = None
    concise: bool = False  # legacy flag; concise=True maps to 'balanced' when style is unset
    include_cover_letter: bool = False  # cover letter is a separate button now
    # "Fit to page": when set, re-tailor with a hard rendered-line budget so a small
    # remainder doesn't waste an under-used trailing page. See page_budget.py.
    target_pages: Optional[int] = Field(default=None, ge=1, le=5)

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


class ExtractJdRequest(BaseModel):
    url: str = Field(min_length=4)


class ExtractJdResponse(BaseModel):
    jd_text: str


class TailorResponse(BaseModel):
    tailored_resume_markdown: Optional[str]
    cover_letter_text: Optional[str] = None
    cover_letter_word_count: Optional[int] = None
    match: MatchOut
    changes_made: list[str] = Field(default_factory=list)
    keywords_added: list[str] = Field(default_factory=list)
    status: str
    errors: list[str] = Field(default_factory=list)
    # Deterministic honesty check over (CV → tailored): each {kind, value, detail}
    # is a skill/metric/domain in the output not found in the CV. Empty = clean.
    honesty: list[dict] = Field(default_factory=list)


class ResumePdfRequest(BaseModel):
    resume_markdown: str = Field(min_length=20)
    download: bool = False


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
    """PDF resume → markdown (via MarkItDown). Returned to the client; never stored."""
    from markitdown import MarkItDown

    pdf_bytes = await file.read()
    try:
        result = MarkItDown().convert_stream(BytesIO(pdf_bytes), file_extension=".pdf")
        markdown = result.text_content
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse PDF: {e}") from e

    if len(markdown.strip()) < 100:
        raise HTTPException(status_code=422, detail="Parsed resume is too short — is this a text PDF (not a scan)?")
    return ResumeParseResponse(markdown=markdown, chars=len(markdown))


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    """Natural-language multi-platform job scrape. The query is parsed into filters
    (Haiku), then scraped live. Stateless — results are returned, not saved."""
    from src.search_nlp import parse_search_query

    q = await parse_search_query(req.query)
    jobs = await job_search.search_jobs(
        keyword=q.keyword,
        location=q.location,
        platforms=q.platforms or None,
        max_jobs=q.max_jobs,
        date_posted=q.date_posted,
        experience_levels=q.experience_levels,
        remote_options=q.remote_options,
        master_cv=req.resume_markdown,
    )
    return SearchResponse(jobs=jobs, interpreted=q.model_dump())


@app.post("/search/stream")
async def search_stream(req: SearchRequest) -> StreamingResponse:
    """Progressive search — NDJSON stream: one `interpreted` line, then a `job`
    line per result as it's scraped, then `done`. Lets the UI render incrementally."""
    import json

    from src.search_nlp import parse_search_query

    q = await parse_search_query(req.query)

    async def gen():
        yield json.dumps({"type": "interpreted", "data": q.model_dump()}) + "\n"
        async for job in job_search.search_jobs_stream(
            keyword=q.keyword, location=q.location, platforms=q.platforms or None,
            max_jobs=q.max_jobs, date_posted=q.date_posted,
            experience_levels=q.experience_levels, remote_options=q.remote_options,
            master_cv=req.resume_markdown,
        ):
            yield json.dumps({"type": "job", "data": job}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"

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
    text = await job_search.fetch_job_description(req.platform, req.external_id, req.url)
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
    # "Fit to page": budget = target_pages × the per-page safety-margin line target.
    from src.utils.page_budget import ONE_PAGE_TARGET
    target_line_budget = req.target_pages * ONE_PAGE_TARGET if req.target_pages else None
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
    gaps = gap_analysis(result.parsed_jd, req.resume_markdown, resume_md=tailored_md)
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
    )


@app.post("/cover-letter", response_model=CoverLetterResponse)
async def cover_letter(req: CoverLetterRequest) -> CoverLetterResponse:
    """Generate a cover letter for an (already tailored) resume + JD."""
    cl = await services.cover_letter_for(req.jd_text, req.resume_markdown)
    return CoverLetterResponse(cover_letter_text=cl.content, word_count=cl.word_count)


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
        resume_markdown_to_pdf_bytes, req.resume_markdown, candidate_name_from_markdown(req.resume_markdown)
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
