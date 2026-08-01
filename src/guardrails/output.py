"""Output guard: restore redacted identifiers and verify the round-trip.

After the tailor returns anonymized markdown, we restore the real identifiers and
check that every one round-tripped. The tailor never legitimately changes the
name/contact block (it copies it), so if any identifier failed to round-trip we
force-restore the header from the original CV — guaranteeing the final resume
carries the user's correct details even if the model mangled a placeholder token.

The honesty linter (``lint_resume``) is re-exported here as the formal output
honesty guard; it runs unchanged on the restored (real) text vs. the real CV.
"""

from __future__ import annotations

import re

from src.guardrails.pii import Redaction, _header_block, restore
from src.guardrails.schemas import GuardrailReport, RedactionSummary
from src.matching.honesty import lint_resume  # noqa: F401 — re-exported as the output honesty guard

# Matches our placeholder tokens, e.g. <NAME_0>, <EMAIL_12>.
_PLACEHOLDER_RE = re.compile(r"<[A-Z][A-Z_]*_\d+>")


def _replace_header(markdown: str, new_header: str) -> str | None:
    """Swap ``markdown``'s header block for ``new_header``. Returns None (no-op) when
    the output has no ``## `` section — we won't risk clobbering the whole document."""
    lines = markdown.splitlines()
    idx = next((i for i, line in enumerate(lines) if line.startswith("## ")), None)
    if idx is None:
        return None
    return "\n".join([new_header, ""] + lines[idx:])


def summary_report(redaction: Redaction) -> GuardrailReport:
    """A redaction-summary-only report (no resume header to force-restore), for the
    cover-letter path where the output is free prose rather than a structured resume."""
    if not redaction.available:
        return GuardrailReport(available=False)
    return GuardrailReport(
        redaction=RedactionSummary(counts=redaction.counts, total=sum(redaction.counts.values())),
        available=True,
    )


def restore_and_verify(
    tailored_md: str, redaction: Redaction, original_cv: str
) -> tuple[str, GuardrailReport]:
    """Restore identifiers in ``tailored_md`` and return (restored_md, report)."""
    if not redaction.available:
        return tailored_md, GuardrailReport(available=False)

    summary = RedactionSummary(counts=redaction.counts, total=sum(redaction.counts.values()))
    reverse = {ph: orig for by_type in redaction.entity_mapping.values() for orig, ph in by_type.items()}
    expected = set(reverse)
    missing = {ph for ph in expected if ph not in tailored_md}  # model dropped/altered these

    restored = restore(tailored_md, redaction)
    residual = set(_PLACEHOLDER_RE.findall(restored))  # orphan tokens the model may have invented

    leaks: list[str] = []
    header_forced = False
    if missing or residual:
        forced = _replace_header(restored, _header_block(original_cv))
        if forced is not None:
            restored = forced
            header_forced = True
        for ph in sorted(missing, key=len, reverse=True):
            leaks.append(f"identifier not echoed by the model: {reverse[ph]!r}")
        for token in sorted(residual):
            leaks.append(f"residual placeholder in output: {token}")

    return restored, GuardrailReport(
        redaction=summary,
        all_restored=not missing and not residual,
        header_forced=header_forced,
        leaks=leaks,
        available=True,
    )
