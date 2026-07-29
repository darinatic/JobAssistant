"""Deterministic JD preprocessing for the fit predictor's 512-token budget.

Keeps high-signal sections (responsibilities, requirements, qualifications,
skills, tech) and drops boilerplate (about-us, company blurb, benefits, perks,
EEO, how-to-apply) so the truncated model input carries the parts that predict
fit. No LLM; pure string work.
"""

from __future__ import annotations

# Boilerplate section headings to DROP (matched case-insensitively as substrings).
_DROP = (
    "about us", "about the company", "about the team", "who we are",
    "benefit", "perk", "what we offer", "why join", "equal opportunit", "eeo",
    "how to apply", "to apply", "our mission", "our story", "diversity", "company overview",
)
_HEADING_MAX_WORDS = 8


def _matches(text: str, needles: tuple[str, ...]) -> bool:
    t = text.lower()
    return any(n in t for n in needles)


def _is_heading(line: str) -> bool:
    """A short line that ends with ':' or names a known boilerplate section."""
    s = line.strip()
    if not s or len(s.split()) > _HEADING_MAX_WORDS:
        return False
    return s.rstrip().endswith(":") or _matches(s, _DROP)


def preprocess_jd(text: str, max_chars: int = 2000) -> str:
    """Return the signal-bearing part of a JD, boilerplate stripped, capped.

    Splits into sections at heading-like lines, drops sections whose heading is a
    known boilerplate one, keeps the rest. Falls back to the head of the text when
    no sections are detected. ``max_chars`` roughly bounds the model's token budget.
    """
    if not text or not text.strip():
        return ""

    sections: list[tuple[str, list[str]]] = [("", [])]  # (heading, body lines)
    for line in text.splitlines():
        if _is_heading(line):
            sections.append((line.strip(), []))
        else:
            sections[-1][1].append(line)

    kept: list[str] = []
    saw_heading = len(sections) > 1
    for heading, body in sections:
        if heading and _matches(heading, _DROP):
            continue  # drop the whole boilerplate section (heading + body)
        block = "\n".join([heading, *body] if heading else body).strip()
        if block:
            kept.append(block)

    out = "\n\n".join(kept).strip()
    if not out or not saw_heading:
        out = text.strip()  # no clear sections -> keep the head (truncated below)
    return out[:max_chars]
