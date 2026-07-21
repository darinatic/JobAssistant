"""Deterministic honesty linter — catches fabrication without an LLM."""

from src.matching import lint_resume

_CV = """# Jane Tan
## Summary
ML engineer building RAG systems.
## Skills
Python, PyTorch, Docker, FastAPI, AWS
## Experience
### ML Engineer, Acme (2023-2025)
- Built a RAG chatbot with LangChain handling 10k queries/day
- Fine-tuned BERT for classification, 92% accuracy
### Education
BSc Computer Science, NUS (2023)
"""


def test_faithful_tailor_has_no_findings():
    # Reorders + rephrases, spells out an acronym, keeps the same facts.
    tailored = """# Jane Tan
## Summary
Machine Learning (ML) engineer specializing in Retrieval-Augmented Generation (RAG).
## Skills
Python, PyTorch, FastAPI, Docker, AWS
## Experience
### ML Engineer, Acme (2023-2025)
- Fine-tuned BERT achieving 92% accuracy on classification
- Built a RAG chatbot on LangChain serving 10,000 queries/day
"""
    report = lint_resume(_CV, tailored)
    assert report.ok, report.as_dicts()


def test_added_skills_are_NOT_flagged():
    # Weaving JD skills into the Skills section is the tailor's job (ATS value).
    tailored = _CV.replace("Python, PyTorch, Docker, FastAPI, AWS",
                           "Python, PyTorch, Docker, FastAPI, AWS, Kubernetes, Terraform, MLflow")
    assert lint_resume(_CV, tailored).ok


def test_flags_invented_entry():
    # A fabricated job/project the CV never mentions.
    tailored = _CV + "\n### Senior AI Engineer, MediCorp Health (2019-2021)\n- Led clinical ML"
    entries = {f.value for f in lint_resume(_CV, tailored).of("entry")}
    assert any("MediCorp" in e for e in entries)


def test_real_entry_rephrased_is_not_flagged():
    # Same job, retitled — the company 'Acme' still anchors it, so no false positive.
    tailored = _CV.replace("### ML Engineer, Acme (2023-2025)",
                           "### Senior Machine Learning Engineer, Acme (2023-2025)")
    assert not lint_resume(_CV, tailored).of("entry")


def test_flags_fabricated_metric():
    tailored = _CV.replace("92% accuracy", "99.9% accuracy and reduced latency by 40%")
    report = lint_resume(_CV, tailored)
    metrics = {f.value for f in report.of("metric")}
    assert "99.9%" in metrics and "40%" in metrics


def test_flags_invented_domain():
    tailored = _CV.replace("RAG systems.", "RAG systems for healthcare and fintech clients, HIPAA-compliant.")
    report = lint_resume(_CV, tailored)
    domains = {f.value for f in report.of("domain")}
    assert "healthcare" in domains and "fintech" in domains and "hipaa" in domains


def test_metric_reformatting_is_not_flagged():
    # 10k -> 10,000 and 92% -> 92 % must normalize equal (no false positive).
    tailored = _CV.replace("10k queries", "10,000 queries").replace("92% accuracy", "92 % accuracy")
    assert lint_resume(_CV, tailored).ok
