"""Deterministic eval graders — no LLM."""

from evals.graders import grade, summarize

_CV = "# Jane\n## Skills\nPython, PyTorch, RAG\n## Experience\n### ML Engineer\n- Built RAG chatbot, 92% accuracy"
_JD = "AI Engineer with Python, PyTorch, RAG and Kubernetes."


def test_clean_tailor_scores_well():
    tailored = "# Jane\n## Skills\nPython, PyTorch, RAG\n## Experience\n### ML Engineer\n- Built a RAG chatbot at 92% accuracy"
    g = grade(_CV, _JD, tailored)
    assert g["ok"] and g["fabrications"] == 0 and g["structure_ok"]
    assert g["keyword_coverage"] == 1.0          # Python/PyTorch/RAG all supportable + present


def test_added_skill_is_not_a_fabrication():
    tailored = _CV.replace("Python, PyTorch, RAG", "Python, PyTorch, RAG, Kubernetes")
    assert grade(_CV, _JD, tailored)["fabrications"] == 0   # adding a skill is OK


def test_invented_entry_is_flagged():
    tailored = _CV + "\n### ML Lead, GhostCorp (2019)\n- Ran a team"   # not in the CV
    assert grade(_CV, _JD, tailored)["fabrications"] >= 1


def test_forbidden_domain_trap_caught():
    tailored = _CV + "\n- Built HIPAA-compliant clinical models"
    g = grade(_CV, _JD, tailored, forbidden=("hipaa", "clinical"))
    assert "hipaa" in g["forbidden_hits"] and "clinical" in g["forbidden_hits"]


def test_empty_output_is_not_ok():
    assert grade(_CV, _JD, "")["ok"] is False


def test_summary_counts_clean_cases():
    rows = [
        {"ok": True, "fabrications": 0, "forbidden_hits": [], "keyword_coverage": 1.0, "fits_one_page": True, "structure_ok": True},
        {"ok": True, "fabrications": 2, "forbidden_hits": ["hipaa"], "keyword_coverage": 0.5, "fits_one_page": False, "structure_ok": True},
    ]
    s = summarize(rows)
    assert s["honesty_clean"] == 1 and s["honesty_clean_pct"] == 50
    assert s["total_fabrications"] == 2 and s["one_page_pct"] == 50


# --- section mirroring -------------------------------------------------------
# The grader that would have caught the v1-v3 invented-summary bug. Every other
# grader passes on that output: nothing is fabricated, coverage is fine, it fits.

_CV_NO_SUMMARY = """# Priya Raman
priya@example.com

## Skills
Python, RAG

## Experience
### ML Engineer, Vector Foundry (2022-2025)
- Built a RAG assistant with LangChain
"""


def test_invented_summary_is_flagged():
    from evals.graders import grade

    tailored = """# Priya Raman
priya@example.com

## Summary
Results-driven ML engineer with a proven track record.

## Skills
Python, RAG

## Experience
### ML Engineer, Vector Foundry (2022-2025)
- Built a RAG assistant with LangChain
"""
    row = grade(_CV_NO_SUMMARY, "Python and RAG required", tailored)
    assert row["invented_sections"] == ["summary"]
    # The point: every other signal looks clean, which is why this went unnoticed.
    assert row["fabrications"] == 0
    assert not row["forbidden_hits"]


def test_mirroring_the_cv_passes():
    from evals.graders import grade

    tailored = """# Priya Raman
priya@example.com

## Skills
Python, RAG, LangChain

## Experience
### ML Engineer, Vector Foundry (2022-2025)
- Built a RAG assistant with LangChain
"""
    assert grade(_CV_NO_SUMMARY, "Python and RAG required", tailored)["invented_sections"] == []


def test_dropping_a_section_is_allowed():
    from evals.graders import grade

    # The aggressive style cuts to fit; removing a section is never a violation.
    tailored = """# Priya Raman
priya@example.com

## Skills
Python, RAG
"""
    assert grade(_CV_NO_SUMMARY, "Python required", tailored)["invented_sections"] == []


def test_section_comparison_ignores_case_and_trailing_colon():
    from evals.graders import grade

    tailored = "# Priya Raman\n\n## SKILLS:\nPython, RAG\n"
    assert grade(_CV_NO_SUMMARY, "Python required", tailored)["invented_sections"] == []


def test_summarize_reports_section_mirroring():
    from evals.graders import summarize

    rows = [
        {"ok": True, "fabrications": 0, "forbidden_hits": [], "invented_sections": [],
         "keyword_coverage": 1.0, "fits_one_page": True, "structure_ok": True},
        {"ok": True, "fabrications": 0, "forbidden_hits": [], "invented_sections": ["summary"],
         "keyword_coverage": 1.0, "fits_one_page": True, "structure_ok": True},
    ]
    s = summarize(rows)
    assert s["total_invented_sections"] == 1
    assert s["section_mirror_pct"] == 50
    # Deliberately separate from honesty_clean so the v3/v4 baselines stay comparable.
    assert s["honesty_clean"] == 2
