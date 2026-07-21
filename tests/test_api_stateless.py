"""Endpoint tests for the stateless API (no auth, no DB)."""

import json
from unittest.mock import AsyncMock, patch

from src.agents.schemas import (
    CoverLetter,
    ExperienceLevel,
    MatchRecommendation,
    ParsedJobDescription,
    SkillMatch,
    TailoredResume,
)
from src.services import TailoringResult

_CV = "# Jane\n\n## Skills\nPython, PyTorch, RAG, FastAPI\n\n## Experience\nBuilt RAG systems."
_JD = "We need an AI Engineer skilled in Python, PyTorch, RAG and Kubernetes. " * 3


def _parsed() -> ParsedJobDescription:
    return ParsedJobDescription(
        company="Acme", title="AI Engineer", location="Singapore",
        experience_required="1-2y", experience_level=ExperienceLevel.JUNIOR,
        required_skills=["Python", "PyTorch", "RAG", "Kubernetes"],
        preferred_skills=["FastAPI"],
    )


def _match() -> SkillMatch:
    return SkillMatch(
        overall_score=80, matched_required=["Python", "PyTorch", "RAG"],
        missing_required=["Kubernetes"], matched_preferred=["FastAPI"], missing_preferred=[],
        transferable_skills=[], recommendation=MatchRecommendation.APPLY, reasoning="ok",
    )


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_score(client):
    with patch("src.api.services.parse_jd", new=AsyncMock(return_value=_parsed())), \
         patch("src.api.services.score_jd", new=AsyncMock(return_value=_match())):
        r = client.post("/score", json={"jd_text": _JD, "resume_markdown": _CV})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overall_score"] == 80
    assert body["recommendation"] == "apply"
    # gap_analysis runs for real: Kubernetes is a genuine gap (not in the CV).
    assert "Kubernetes" in body["genuine_gaps"]


def test_search(client):
    from src.search_nlp import SearchQuery
    jobs = [{"platform": "mycareersfuture", "title": "ML Engineer", "company": "X", "relevance": 90}]
    with patch("src.search_nlp.parse_search_query",
               new=AsyncMock(return_value=SearchQuery(keyword="AI Engineer", max_jobs=50, platforms=["jobstreet"]))), \
         patch("src.api.job_search.search_jobs", new=AsyncMock(return_value=jobs)):
        r = client.post("/search", json={"query": "50 AI Engineer jobs on jobstreet", "resume_markdown": _CV})
    assert r.status_code == 200, r.text
    assert r.json()["jobs"][0]["company"] == "X"
    assert r.json()["interpreted"]["max_jobs"] == 50
    assert r.json()["interpreted"]["platforms"] == ["jobstreet"]


def test_search_stream(client):
    from src.search_nlp import SearchQuery

    async def fake_stream(**kw):
        yield {"platform": "mycareersfuture", "title": "ML Engineer", "company": "X", "external_id": "1"}
        yield {"platform": "linkedin", "title": "AI Engineer", "company": "Y", "external_id": "2"}

    with patch("src.search_nlp.parse_search_query", new=AsyncMock(return_value=SearchQuery(keyword="AI"))), \
         patch("src.api.job_search.search_jobs_stream", new=fake_stream):
        r = client.post("/search/stream", json={"query": "AI jobs"})
    assert r.status_code == 200, r.text
    lines = [json.loads(x) for x in r.text.strip().split("\n")]
    assert lines[0]["type"] == "interpreted"
    assert lines[1]["type"] == "job" and lines[1]["data"]["company"] == "X"
    assert lines[-1]["type"] == "done"


def test_tailor(client):
    result = TailoringResult(
        parsed_jd=_parsed(), skill_match=_match(),
        tailored_resume=TailoredResume(markdown_content="# Tailored", changes_made=["x"], keywords_added=["RAG"]),
        cover_letter=CoverLetter(content="Dear team", word_count=2, personalization_points=[]),
        tailored_resume_path=None, status="pending_review", errors=[],
    )
    with patch("src.api.services.run_full_tailoring", new=AsyncMock(return_value=result)):
        r = client.post("/tailor", json={"jd_text": _JD, "resume_markdown": _CV})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tailored_resume_markdown"] == "# Tailored"
    assert body["cover_letter_text"] == "Dear team"
    assert body["match"]["overall_score"] == 80


def test_cover_letter_endpoint(client):
    cl = CoverLetter(content="Dear Hiring Manager, ...", word_count=120, personalization_points=[])
    with patch("src.api.services.cover_letter_for", new=AsyncMock(return_value=cl)):
        r = client.post("/cover-letter", json={"jd_text": _JD, "resume_markdown": _CV})
    assert r.status_code == 200, r.text
    assert r.json()["cover_letter_text"].startswith("Dear")
    assert r.json()["word_count"] == 120


def test_extract_jd_endpoint(client):
    with patch("src.jd_extract.extract_jd_from_url", new=AsyncMock(return_value="A real job description " * 5)):
        r = client.post("/extract-jd", json={"url": "example.com/job/1"})
    assert r.status_code == 200, r.text
    assert "job description" in r.json()["jd_text"]


def _tailor_result():
    return TailoringResult(
        parsed_jd=_parsed(), skill_match=_match(),
        tailored_resume=TailoredResume(markdown_content="# Tailored", changes_made=[], keywords_added=[]),
        cover_letter=None, tailored_resume_path=None, status="pending_review", errors=[],
    )


def test_tailor_style_passes_through(client):
    mock = AsyncMock(return_value=_tailor_result())
    with patch("src.api.services.run_full_tailoring", new=mock):
        r = client.post("/tailor", json={"jd_text": _JD, "resume_markdown": _CV, "style": "aggressive"})
    assert r.status_code == 200, r.text
    assert mock.call_args.kwargs["style"] == "aggressive"


def test_tailor_legacy_concise_maps_to_balanced(client):
    mock = AsyncMock(return_value=_tailor_result())
    with patch("src.api.services.run_full_tailoring", new=mock):
        r = client.post("/tailor", json={"jd_text": _JD, "resume_markdown": _CV, "concise": True})
    assert r.status_code == 200, r.text
    assert mock.call_args.kwargs["style"] == "balanced"


def test_tailor_target_pages_sets_line_budget(client):
    # target_pages=2 -> budget = 2 * ONE_PAGE_TARGET (52) = 104 lines.
    mock = AsyncMock(return_value=_tailor_result())
    with patch("src.api.services.run_full_tailoring", new=mock):
        r = client.post("/tailor", json={"jd_text": _JD, "resume_markdown": _CV, "target_pages": 2})
    assert r.status_code == 200, r.text
    assert mock.call_args.kwargs["target_line_budget"] == 104.0


def test_tailor_without_target_pages_has_no_budget(client):
    mock = AsyncMock(return_value=_tailor_result())
    with patch("src.api.services.run_full_tailoring", new=mock):
        r = client.post("/tailor", json={"jd_text": _JD, "resume_markdown": _CV})
    assert r.status_code == 200, r.text
    assert mock.call_args.kwargs["target_line_budget"] is None


def test_resume_pdf(client):
    with patch("src.utils.latex_renderer.resume_markdown_to_pdf_bytes",
               new=AsyncMock(return_value=b"%PDF-1.4 fake")):
        r = client.post("/tailored/resume.pdf", json={"resume_markdown": _CV})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == b"%PDF-1.4 fake"


def test_red_flags_endpoint_shape(client):
    r = client.post("/job/red-flags", json={
        "description": "Pay a registration fee of $50. Contact us on WhatsApp.",
        "company": "X"})
    assert r.status_code == 200
    codes = {f["code"] for f in r.json()["flags"]}
    assert "upfront_payment" in codes and "messaging_only" in codes


def test_red_flags_endpoint_clean(client):
    r = client.post("/job/red-flags", json={
        "description": ("Senior ML Engineer building RAG pipelines with PyTorch. "
                        "5+ years experience required. Apply on our careers site."),
        "company": "Acme", "salary_min": 6000, "salary_max": 9000,
        "posted_date": "2026-07-10"})
    assert r.status_code == 200
    # deterministic clean posting -> no high/warn flags
    assert all(f["severity"] == "info" for f in r.json()["flags"])
