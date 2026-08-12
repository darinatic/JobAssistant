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


def test_contact_info_is_not_flagged_as_metric():
    # A phone / email / profile URL in the header is contact info, not a fabricated
    # achievement figure — its digits must not surface as "metric" findings.
    tailored = _CV.replace(
        "# Jane Tan",
        "# Jane Tan\njane.tan@example.com | +65 9123 4567 | linkedin.com/in/janetan | github.com/janetan123",
    )
    report = lint_resume(_CV, tailored)
    assert report.of("metric") == [], report.as_dicts()


def test_real_metric_still_flagged_alongside_contact_info():
    # Stripping contact info must not blind the check to a genuine fabricated metric.
    tailored = _CV.replace("# Jane Tan", "# Jane Tan\n+65 9123 4567").replace(
        "92% accuracy", "reduced costs by 40%")
    metrics = {f.value for f in lint_resume(_CV, tailored).of("metric")}
    assert "40%" in metrics


def test_metric_reformatting_is_not_flagged():
    # 10k -> 10,000 and 92% -> 92 % must normalize equal (no false positive).
    tailored = _CV.replace("10k queries", "10,000 queries").replace("92% accuracy", "92 % accuracy")
    assert lint_resume(_CV, tailored).ok


# --- dates are not achievements ---------------------------------------------
# The markdown contract puts a role's dates at the end of its `### ` heading after
# " | " so the PDF right-aligns them. That reformats the CV's own "(2023-2025)" into
# "| 2023 - 2025", which used to read as three invented figures.

def test_date_range_reformatting_is_not_flagged():
    tailored = _CV.replace(
        "### ML Engineer, Acme (2023-2025)",
        "### ML Engineer, Acme | 2023 - 2025",
    )
    assert lint_resume(_CV, tailored).ok, lint_resume(_CV, tailored).as_dicts()


def test_hyphenated_year_range_is_not_stripped_as_a_phone_number():
    # "2023-2025" is shaped exactly like the local grouped phone "9123-4567". When
    # the phone regex ate it, the CV silently lost its years while the output kept
    # them, so every reformatted date looked fabricated.
    from src.matching.honesty import _strip_contact

    assert "2023-2025" in _strip_contact("### ML Engineer, Acme (2023-2025)")


def test_real_phone_numbers_are_still_stripped():
    from src.matching.honesty import _strip_contact

    assert "9123 4567" not in _strip_contact("Jane Tan | 9123 4567")
    assert "9123-4567" not in _strip_contact("Jane Tan | 9123-4567")
    assert "3725" not in _strip_contact("Jane Tan | +65 9450 3725")


def test_a_bare_year_is_never_treated_as_a_metric():
    from src.matching.honesty import _metrics

    assert _metrics("Graduated 2018, shipped 300 features") == {"300"}


def test_a_new_graduation_year_is_not_a_fabrication():
    # Adding an education year the CV words differently is a date edit, not an
    # invented achievement — the entry check still guards the school itself.
    tailored = _CV.replace("NUS (2023)", "NUS | 2019 - 2023")
    assert lint_resume(_CV, tailored).ok


def test_a_genuinely_invented_metric_is_still_caught():
    # The year exemption must not blunt the real check.
    tailored = _CV.replace("92% accuracy", "99.7% accuracy")
    assert not lint_resume(_CV, tailored).ok
    assert "99.7%" in {f.value for f in lint_resume(_CV, tailored).of("metric")}
