"""Stateless insights aggregation."""

from unittest.mock import patch

from src.insights import aggregate_jobs

_JOBS = [
    {"title": "AI Engineer", "description": "Python, RAG, LLM, Kubernetes", "platform": "linkedin", "salary_min": 5000, "salary_max": 7000},
    {"title": "ML Engineer", "description": "Python, PyTorch, RAG, Docker", "platform": "linkedin"},
    {"title": "NLP Engineer", "description": "Python, LLM, Kubernetes, AWS", "platform": "mycareersfuture", "salary_max": 8000},
]
_CV = "Python and PyTorch engineer with RAG experience."


def test_aggregate_skill_demand_and_cv_standing():
    out = aggregate_jobs(_JOBS, _CV)
    assert out["job_count"] == 3
    by_skill = {d["skill"]: d for d in out["demanded_skills"]}
    # Python in all 3 jobs → 100%, and the CV has it.
    assert by_skill["Python"]["count"] == 3
    assert by_skill["Python"]["pct"] == 100
    assert by_skill["Python"]["candidate_has"] is True
    # Kubernetes in 2 jobs, CV lacks it → a gap.
    assert by_skill["Kubernetes"]["candidate_has"] is False
    assert "Kubernetes" in out["your_gaps"]
    assert "Python" in out["your_strengths"]
    assert out["coverage"]["avg_relevance"] > 0
    assert out["salary"]["min"] == 5000 and out["salary"]["max"] == 8000


def test_aggregate_no_cv():
    out = aggregate_jobs(_JOBS)
    assert out["coverage"] is None
    assert all(d["candidate_has"] is False for d in out["demanded_skills"])


def test_insights_endpoint(client):
    r = client.post("/insights", json={"jobs": _JOBS, "resume_markdown": _CV})
    assert r.status_code == 200, r.text
    assert r.json()["job_count"] == 3
    assert "Python" in r.json()["your_strengths"]
