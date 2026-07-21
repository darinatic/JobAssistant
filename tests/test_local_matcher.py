"""Unit tests for the local (gazetteer-based) matching engine.

Pure, deterministic, no LLM — these run everywhere and fast.
"""

from src.agents.schemas import ExperienceLevel, MatchRecommendation, ParsedJobDescription
from src.matching.gazetteer import canonicalize, extract_skills
from src.matching.local_matcher import gap_analysis, match_local


def _jd(required=None, preferred=None, tech_stack=None) -> ParsedJobDescription:
    return ParsedJobDescription(
        company="TestCo",
        title="AI Engineer",
        location="Singapore",
        experience_required="1-2 years",
        experience_level=ExperienceLevel.JUNIOR,
        required_skills=required or [],
        preferred_skills=preferred or [],
        tech_stack=tech_stack or [],
    )


# --- gazetteer --------------------------------------------------------------
def test_extract_basic_and_aliases():
    skills = extract_skills("Experience with PyTorch, building RAG systems and LLMs.")
    assert {"PyTorch", "RAG", "LLM"} <= skills


def test_alias_maps_to_canonical():
    assert extract_skills("we run everything on k8s") == {"Kubernetes"}
    assert extract_skills("torch and tensor flow") == {"PyTorch", "TensorFlow"}
    assert extract_skills("retrieval-augmented generation pipeline") == {"RAG"}


def test_word_boundary_no_false_substring():
    # "java" must NOT fire inside "javascript".
    skills = extract_skills("Strong JavaScript developer")
    assert "JavaScript" in skills
    assert "Java" not in skills


def test_symbol_tokens_match():
    skills = extract_skills("Proficient in C++, C# and Node.js")
    assert {"C++", "C#", "Node.js"} <= skills


def test_ambiguous_short_skills_not_overmatched():
    # bare "go"/"r" in prose must not be mistaken for the Go language / R.
    assert "Go" not in extract_skills("please go to the next round")
    assert "Go" in extract_skills("backend services in Golang")


def test_canonicalize():
    assert canonicalize("k8s") == "Kubernetes"
    assert canonicalize("Python programming") == "Python"
    assert canonicalize("some unlisted skill xyz") is None


# --- scorer -----------------------------------------------------------------
def test_match_local_scores_and_buckets():
    jd = _jd(
        required=["Python", "PyTorch", "RAG", "Kubernetes"],
        preferred=["AWS", "FastAPI"],
    )
    cv = "Built RAG systems in Python with PyTorch. Deployed on AWS with FastAPI."
    m = match_local(jd, cv)

    assert set(m.matched_required) == {"Python", "PyTorch", "RAG"}
    assert m.missing_required == ["Kubernetes"]
    assert set(m.matched_preferred) == {"AWS", "FastAPI"}
    # 3/4 required (0.75) + 2/2 preferred (1.0) + baseline: 60*.75 + 25 + 15 = 85
    assert m.overall_score == 85
    assert m.recommendation == MatchRecommendation.APPLY


def test_match_local_weak_match_skips():
    jd = _jd(required=["Rust", "Scala", "Hadoop", "Kafka"])
    m = match_local(jd, "Python and PyTorch only.")
    assert m.matched_required == []
    assert m.overall_score == 15  # baseline only
    assert m.recommendation == MatchRecommendation.SKIP


def test_match_local_fallback_for_unlisted_skill():
    # "GraphQL" is in the gazetteer; an out-of-gazetteer term still matches via substring.
    jd = _jd(required=["Kubernetes administration"])
    m = match_local(jd, "Handled Kubernetes administration for the cluster.")
    assert m.matched_required == ["Kubernetes administration"]


# --- gap analysis (the tailoring honesty split) -----------------------------
def test_gap_analysis_surfaceable_vs_genuine():
    jd = _jd(required=["Python", "Docker", "Terraform"])
    master = "Python engineer who has used Docker in production."
    # The tailored resume dropped Docker; Terraform was never in the master CV.
    resume = "Python engineer focused on ML."

    gaps = gap_analysis(jd, master, resume_md=resume)
    assert "Docker" in gaps.surfaceable_skills      # has it, not on resume → weave in
    assert "Terraform" in gaps.genuine_gaps         # never had it → learning path
    assert "Python" not in gaps.surfaceable_skills  # already on resume
    assert "Python" not in gaps.genuine_gaps


def test_gap_analysis_defaults_to_master_no_surfaceable():
    jd = _jd(required=["Python", "Rust"])
    gaps = gap_analysis(jd, "Python developer.")
    assert gaps.surfaceable_skills == []       # resume == master → nothing hidden
    assert gaps.genuine_gaps == ["Rust"]
