"""Unit tests for the local (gazetteer-based) matching engine.

Pure, deterministic, no LLM — these run everywhere and fast.
"""

from src.agents.schemas import ExperienceLevel, MatchRecommendation, ParsedJobDescription
from src.matching.gazetteer import canonicalize, extract_skills
from src.matching.local_matcher import gap_analysis, match_local, reconcile_jd_skills


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
    # Flat pool: 5 of 6 skills matched (Python, PyTorch, RAG, AWS, FastAPI; Kubernetes not) → 83.
    assert m.overall_score == 83
    assert m.recommendation == MatchRecommendation.APPLY


def test_match_local_weak_match_skips():
    jd = _jd(required=["Rust", "Scala", "Hadoop", "Kafka"])
    m = match_local(jd, "Python and PyTorch only.")
    assert m.matched_required == []
    assert m.overall_score == 0  # no overlap → 0, same basis as search relevance
    assert m.recommendation == MatchRecommendation.SKIP


def test_match_local_fallback_for_unlisted_skill():
    # "GraphQL" is in the gazetteer; an out-of-gazetteer term still matches via substring.
    jd = _jd(required=["Kubernetes administration"])
    m = match_local(jd, "Handled Kubernetes administration for the cluster.")
    assert m.matched_required == ["Kubernetes administration"]


# --- gap analysis (the tailoring honesty split) -----------------------------
def test_gap_analysis_partitions_jd_skills_by_cv_presence():
    jd = _jd(required=["Python", "Docker", "Terraform"])
    master = "Python engineer who has used Docker in production."

    gaps = gap_analysis(jd, master)
    # Every JD skill the CV backs is surfaceable (honest to feature), regardless
    # of whether a tailored draft already lists it.
    assert "Python" in gaps.surfaceable_skills
    assert "Docker" in gaps.surfaceable_skills
    assert "Terraform" in gaps.genuine_gaps          # never in the CV → learning path
    assert "Terraform" not in gaps.surfaceable_skills


def test_gap_analysis_all_backed_skills_surface():
    jd = _jd(required=["Python", "Rust"])
    gaps = gap_analysis(jd, "Python developer.")
    assert gaps.surfaceable_skills == ["Python"]     # in the CV → honest to feature
    assert gaps.genuine_gaps == ["Rust"]             # not in the CV → gap


# --- reconcile: gazetteer is the single source of JD skills (search ↔ tailor) ---
def test_reconcile_aligns_tailor_skills_with_search():
    """After reconcile, the tailor's JD skills equal what search's gazetteer would
    extract from the same text — so the two stages can't disagree on the count."""
    jd_text = (
        "We need Python, PyTorch and RAG. Bonus: Kubernetes. Strong stakeholder "
        "collaboration and a drive for innovation."
    )
    jd = _jd(
        required=["Python", "Stakeholder collaboration", "Innovation driving"],
        preferred=["Machine Learning"],
        tech_stack=["PyTorch"],
    )
    candidates = reconcile_jd_skills(jd, jd_text)

    assert jd.required_skills == sorted(extract_skills(f"{jd.title}\n{jd_text}"))
    assert {"Python", "PyTorch", "RAG", "Kubernetes"} <= set(jd.required_skills)
    assert "Stakeholder collaboration" not in jd.required_skills  # soft-skill noise dropped
    assert jd.preferred_skills == [] and jd.tech_stack == [] and jd.keywords_for_resume == []
    # the dropped soft-skill phrases come back as growth candidates for curation
    assert "Stakeholder collaboration" in candidates and "Innovation driving" in candidates


def test_reconcile_returns_unknown_haiku_skills_as_growth_candidates():
    jd = _jd(required=["Python", "Stakeholder collaboration"], tech_stack=["Widget wrangling"])
    candidates = reconcile_jd_skills(jd, "A Python role.")
    assert "Python" not in candidates  # known to the gazetteer
    assert set(candidates) == {"Stakeholder collaboration", "Widget wrangling"}
