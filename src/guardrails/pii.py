"""Reversible PII redaction for text sent to the LLM (data minimization).

The candidate's CV is sent to Anthropic (a third party) to tailor it. Before it
leaves, we strip the direct identifiers — name, email, phone, profile URLs — and
replace each with a unique placeholder token (``<NAME_0>``, ``<EMAIL_0>``, ...). The
model tailors an anonymized copy; we restore the real identifiers locally from the
mapping. See ``output.restore_and_verify`` for the restore + verification.

Detection is **deterministic, dependency-free, ~1ms** — no NER model, no extra LLM
call — matching the rest of the app (honesty linter, red flags, gazetteer). It is
**header-anchored**: in a resume the direct identifiers live in the contact header
(the block before the first ``## `` section), and the app's markdown format puts the
name on the ``# `` H1 line. So:

- **Name** = the first ``# `` H1 (fallback: a short first content line). Redacted
  everywhere it appears (word-boundary), so a repeat in the summary is caught too.
- **Email** = regex, document-wide (near-zero false positives).
- **Phone / URL** = regex, **header-only** — this is where they live, and scoping
  there avoids eating body numbers ("10,000 users", "2023") or reference links.

Skills / companies / metrics in the body are never touched (we only redact the H1
name and header identifiers), so the tailor keeps all the substance it needs — no
NER false positives, no gazetteer allowlist required. Everything fails OPEN: any
error yields an unredacted ``Redaction`` with ``available=False`` so tailoring
proceeds on the real CV rather than breaking.
"""

from __future__ import annotations

import logging
import re

from src.utils.config import settings

log = logging.getLogger(__name__)

_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:[\w-]+\.)+"
    r"(?:com|org|net|io|dev|co|me|ai|xyz|tech|gov|edu)"
    r"(?:/[\w\-./%?=&#]*)?",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{5,}\d")


class Redaction:
    """Result of anonymizing a piece of text.

    ``entity_mapping`` is a nested ``{entity_type: {original: placeholder}}`` dict;
    ``restore`` inverts it. ``available=False`` means redaction was skipped or failed
    (fail-open) and ``text`` is the original, unredacted input.
    """

    def __init__(
        self,
        text: str,
        entity_mapping: dict[str, dict[str, str]] | None = None,
        counts: dict[str, int] | None = None,
        available: bool = True,
    ) -> None:
        self.text = text
        self.entity_mapping = entity_mapping or {}
        self.counts = counts or {}
        self.available = available


def _header_block(markdown: str) -> str:
    """The contact header — every line up to the first ``## `` section heading."""
    lines: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            break
        lines.append(line)
    return "\n".join(lines).rstrip()


def _digit_count(s: str) -> int:
    return sum(c.isdigit() for c in s)


def _extract_name(text: str) -> str | None:
    """The candidate's name — the first ``# `` H1, else a short first content line."""
    m = _H1_RE.search(text)
    if m:
        return m.group(1).strip()
    for line in text.splitlines():
        s = line.strip().lstrip("#").strip()
        if not s:
            continue
        # A plausible name line: a few words, no email/digits (else it's a contact line).
        if "@" in s or any(c.isdigit() for c in s):
            return None
        return s if 1 <= len(s.split()) <= 5 else None
    return None


def _detect(text: str) -> list[tuple[str, str]]:
    """Find (entity_type, value) pairs to redact — deterministic, header-anchored."""
    values: list[tuple[str, str]] = []

    name = _extract_name(text)
    if name:
        values.append(("NAME", name))

    emails = set(_EMAIL_RE.findall(text))
    values += [("EMAIL", e) for e in emails]

    # Phone + URL only exist in the contact header; scope there for precision. Mask
    # emails (and then URLs) out first so their characters aren't re-detected.
    header = _header_block(text)
    for e in emails:
        header = header.replace(e, " ")
    urls = {m.group(0) for m in _URL_RE.finditer(header)}
    values += [("URL", u) for u in urls]

    for u in urls:
        header = header.replace(u, " ")
    phones = {p.strip() for p in _PHONE_RE.findall(header) if _digit_count(p) >= 7}
    values += [("PHONE", p) for p in phones]

    return values


def _register(mapping: dict[str, dict[str, str]], etype: str, value: str) -> str:
    bucket = mapping.setdefault(etype, {})
    if value in bucket:
        return bucket[value]
    token = f"<{etype}_{len(bucket)}>"
    bucket[value] = token
    return token


def anonymize(text: str) -> Redaction:
    """Strip direct identifiers from ``text``, returning the anonymized text plus the
    reversible mapping. Fails open: on any error returns the original text with
    ``available=False``."""
    if not settings.pii_redaction_enabled or not text.strip():
        return Redaction(text=text, available=False)

    try:
        mapping: dict[str, dict[str, str]] = {}
        redacted = text
        # Longest value first so a shorter value (e.g. a first name) can't clobber a
        # longer one it is a substring of.
        for etype, value in sorted(_detect(text), key=lambda v: len(v[1]), reverse=True):
            if not value:
                continue
            # Names use word boundaries (avoid "Sam" matching inside "Samsung"); the
            # long distinctive identifiers (email/phone/url) are safe as literals.
            if etype == "NAME":
                pattern = re.compile(rf"\b{re.escape(value)}\b")
                if not pattern.search(redacted):
                    continue
                token = _register(mapping, etype, value)
                redacted = pattern.sub(token, redacted)
            else:
                if value not in redacted:
                    continue
                token = _register(mapping, etype, value)
                redacted = redacted.replace(value, token)
        counts = {etype: len(m) for etype, m in mapping.items() if m}
        return Redaction(text=redacted, entity_mapping=mapping, counts=counts)
    except Exception:  # noqa: BLE001 — fail open, never break tailoring
        log.warning("PII redaction unavailable; tailoring on the real CV", exc_info=True)
        return Redaction(text=text, available=False)


def restore(text: str, redaction: Redaction) -> str:
    """Replace placeholder tokens in ``text`` with the original identifiers.

    Token replacement (the tailor rewrites/reorders the text, so any positional
    mapping would be invalid, but the ``<NAME_0>`` tokens survive verbatim at temp 0).
    Longest token first so ``<NAME_1>`` is not clipped inside ``<NAME_10>``. Tokens
    absent from ``text`` are left as-is (the output guard reports them)."""
    if not redaction.available or not redaction.entity_mapping:
        return text
    reverse = {ph: orig for by_type in redaction.entity_mapping.values() for orig, ph in by_type.items()}
    for placeholder in sorted(reverse, key=len, reverse=True):
        text = text.replace(placeholder, reverse[placeholder])
    return text
