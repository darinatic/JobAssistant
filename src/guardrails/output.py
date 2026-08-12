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


class StreamingRestorer:
    """Restore identifiers incrementally as tailored markdown streams in.

    Streaming the model's raw output would show the user ``<NAME_0>`` in their own
    resume, so tokens have to be swapped back before each chunk is released. The
    catch is that a token can straddle a chunk boundary (``"...<NAM"`` + ``"E_0>..."``),
    and a naive per-chunk ``restore`` would emit the two halves untouched.

    So the tail is held back whenever it contains an unterminated ``<``: that is the
    only way a placeholder can be half-arrived. The hold is capped at
    ``_MAX_HOLD`` characters, because ordinary prose can contain a ``<`` that never
    closes and the stream must not stall waiting for a ``>`` that never comes.

    This is a *display* guard. The authoritative resume is still the fully
    accumulated text put through :func:`restore_and_verify` at the end of the
    stream, which is what runs the round-trip check and the header safety net.
    """

    # Longest real token is like "<PHONE_10>"; 32 gives ample headroom.
    _MAX_HOLD = 32

    def __init__(self, redaction: Redaction) -> None:
        self._redaction = redaction
        self._buf = ""

    def push(self, chunk: str) -> str:
        """Feed a raw chunk, get back the safe-to-display restored text."""
        self._buf += chunk
        cut = len(self._buf)
        start = self._buf.rfind("<")
        if start != -1 and ">" not in self._buf[start:] and len(self._buf) - start <= self._MAX_HOLD:
            cut = start  # a placeholder may be mid-arrival — hold from the '<'
        out, self._buf = self._buf[:cut], self._buf[cut:]
        return restore(out, self._redaction)

    def flush(self) -> str:
        """Release whatever is still held (end of stream)."""
        out, self._buf = self._buf, ""
        return restore(out, self._redaction)


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

    # The contact header is COPIED, never authored — the tailor has no legitimate
    # reason to rewrite a name, email, phone or profile link. Rebuilding it from the
    # CV unconditionally also closes a failure mode nothing else catches: the tailor
    # prompt asks for links shaped like "linkedin.com/in/x", so the model sometimes
    # wraps an opaque <URL_0> placeholder in that prefix, and restoring then yields
    # "linkedin.com/in/linkedin.com/in/user". The token round-trips, so the check
    # below still passes while the user's actual URL is broken in the PDF.
    rebuilt = _replace_header(restored, _header_block(original_cv))
    if rebuilt is not None:
        restored = rebuilt

    if missing or residual:
        # `header_forced` stays reserved for "we had to intervene because an
        # identifier did not round-trip", which is what the UI surfaces.
        header_forced = rebuilt is not None
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
