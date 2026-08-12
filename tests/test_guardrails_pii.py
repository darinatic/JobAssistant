"""Tests for the PII guardrail layer (src/guardrails).

Offline — no Anthropic/LLM call. The "model" is simulated by echoing / rewriting the
anonymized text, since redaction correctness is independent of the actual tailoring.
Detection is deterministic (regex + the H1 name) — no external deps.
"""

from src.guardrails import anonymize, pii, restore, restore_and_verify, summary_report

CV = """# Jason Bobo Kyaw
jason.bk@example.com | +65 9123 4567 | linkedin.com/in/jasonbk | Singapore

## Summary
Jason Bobo Kyaw is an AI engineer focused on LLM systems and RAG pipelines.

## Skills
Python, PyTorch, Kubernetes, AWS, LangGraph

## Experience
### ML Engineer, Acme | 2023 - Present
- Built a RAG chatbot serving 10,000 users.
"""


def test_direct_identifiers_are_stripped_from_what_the_model_sees():
    red = anonymize(CV)
    assert red.available
    # The real identifiers must NOT appear in the anonymized text.
    assert "jason.bk@example.com" not in red.text
    assert "+65 9123 4567" not in red.text
    assert "Jason Bobo Kyaw" not in red.text
    # Placeholder tokens are present instead.
    assert "<EMAIL_0>" in red.text
    assert "<PHONE_0>" in red.text


def test_substance_is_not_redacted():
    """Skills / tech terms / company names the tailor needs must survive verbatim —
    deterministic detection only touches the H1 name + header identifiers, so nothing
    in the body is at risk."""
    red = anonymize(CV)
    for term in ("Python", "PyTorch", "Kubernetes", "RAG", "LLM", "AI engineer", "Acme"):
        assert term in red.text, f"{term!r} should not be redacted"


def test_round_trip_identity_echo():
    """Model echoes the anonymized text verbatim → restore yields the originals back."""
    red = anonymize(CV)
    restored = restore(red.text, red)
    assert "Jason Bobo Kyaw" in restored
    assert "jason.bk@example.com" in restored
    assert "+65 9123 4567" in restored
    assert "<PERSON_0>" not in restored and "<EMAIL_ADDRESS_0>" not in restored


def test_round_trip_survives_rewrite_and_reorder():
    """Positions change and prose is rewritten, but tokens survive → identifiers restore."""
    red = anonymize(CV)
    rewritten = "REORDERED HEADER\n" + red.text.replace(
        "AI engineer focused on LLM systems and RAG pipelines",
        "Machine Learning (ML) engineer specializing in RAG and LLM systems",
    )
    restored, report = restore_and_verify(rewritten, red, original_cv=CV)
    assert "Jason Bobo Kyaw" in restored
    assert "jason.bk@example.com" in restored
    assert report.all_restored
    assert not report.header_forced
    assert report.available


def test_duplicate_name_restores_all_occurrences():
    """The name appears in the header AND the summary — both must round-trip."""
    red = anonymize(CV)
    restored = restore(red.text, red)
    assert restored.count("Jason Bobo Kyaw") >= 2


def test_header_safety_net_when_model_drops_a_token():
    """If the model fails to echo the name/email tokens, the header is force-restored
    from the original CV so the final resume still carries the real details."""
    red = anonymize(CV)
    # Simulate the model dropping the header tokens entirely (none echoed), while
    # still returning a resume with sections.
    dropped = (
        "# Candidate\ncontact withheld\n\n"
        "## Summary\nExperienced engineer.\n\n## Skills\nPython, PyTorch\n"
    )
    restored, report = restore_and_verify(dropped, red, original_cv=CV)
    assert report.header_forced
    assert not report.all_restored
    assert "Jason Bobo Kyaw" in restored
    assert "jason.bk@example.com" in restored


def test_report_counts_reflect_redaction():
    red = anonymize(CV)
    _, report = restore_and_verify(red.text, red, original_cv=CV)
    assert report.redaction.total >= 3  # at least name + email + phone
    assert report.redaction.counts.get("EMAIL", 0) == 1


def test_fail_open_on_internal_error(monkeypatch):
    """A detection failure must not break tailoring: return the real CV, available=False."""
    def boom(_text):
        raise RuntimeError("detection blew up")

    monkeypatch.setattr(pii, "_detect", boom)
    red = anonymize(CV)
    assert not red.available
    assert red.text == CV  # unredacted — the caller tailors on the real CV
    # restore is a no-op on an unavailable redaction.
    assert restore(red.text, red) == CV
    _, report = restore_and_verify(red.text, red, original_cv=CV)
    assert not report.available


def test_disabled_flag_skips_redaction(monkeypatch):
    monkeypatch.setattr(pii.settings, "pii_redaction_enabled", False)
    red = anonymize(CV)
    assert not red.available
    assert red.text == CV


def test_summary_report_for_cover_letter_path():
    red = anonymize(CV)
    report = summary_report(red)
    assert report.available
    assert report.redaction.total >= 3


# --- the contact header is copied, never authored ---------------------------

def _cv() -> str:
    return (
        "# Jane Tan\n\n"
        "jane.tan@example.com | +65 9123 4567 | linkedin.com/in/janetan\n\n"
        "## Skills\n\nPython, RAG\n"
    )


def test_model_wrapping_a_placeholder_in_a_url_prefix_is_repaired():
    """Regression: 'linkedin.com/in/linkedin.com/in/janetan'.

    The tailor prompt asks for links shaped 'linkedin.com/in/x', so the model
    sometimes wraps the opaque <URL_0> token in that prefix. The token round-trips
    fine, so the placeholder check passes while the user's URL is silently broken.
    """
    from src.guardrails.output import restore_and_verify
    from src.guardrails.pii import anonymize

    cv = _cv()
    rd = anonymize(cv)
    url_token = next(iter(rd.entity_mapping["URL"].values()))
    name_token = rd.entity_mapping["NAME"]["Jane Tan"]
    email_token = next(iter(rd.entity_mapping["EMAIL"].values()))
    phone_token = next(iter(rd.entity_mapping["PHONE"].values()))

    # Every token present (so nothing is "missing"), but the URL is prefix-wrapped.
    bad = (
        f"# {name_token}\n\n{email_token} | {phone_token} | linkedin.com/in/{url_token}\n\n"
        "## Skills\n\nPython, RAG\n"
    )
    out, report = restore_and_verify(bad, rd, original_cv=cv)

    assert "linkedin.com/in/linkedin.com/in/janetan" not in out
    assert "linkedin.com/in/janetan" in out
    # Tokens all round-tripped, so this is NOT reported as a forced intervention.
    assert report.all_restored is True
    assert report.header_forced is False


def test_header_is_taken_from_the_cv_even_when_the_model_reformats_it():
    from src.guardrails.output import restore_and_verify
    from src.guardrails.pii import anonymize

    cv = _cv()
    rd = anonymize(cv)
    tokens = [ph for by in rd.entity_mapping.values() for ph in by.values()]
    name = rd.entity_mapping["NAME"]["Jane Tan"]
    others = " . ".join(t for t in tokens if t != name)  # model reflows the separators
    reflowed = f"# {name}\n\n{others}\n\n## Skills\n\nPython\n"

    out, _ = restore_and_verify(reflowed, rd, original_cv=cv)
    assert "jane.tan@example.com | +65 9123 4567 | linkedin.com/in/janetan" in out


def test_body_content_is_untouched_by_the_header_rebuild():
    from src.guardrails.output import restore_and_verify
    from src.guardrails.pii import anonymize

    cv = _cv()
    rd = anonymize(cv)
    name = rd.entity_mapping["NAME"]["Jane Tan"]
    tailored = f"# {name}\n\nsomething\n\n## Skills\n\nPython, RAG, LangChain\n"
    out, _ = restore_and_verify(tailored, rd, original_cv=cv)
    assert "Python, RAG, LangChain" in out
