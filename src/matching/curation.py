"""Gazetteer curation: turn the growth queue into reviewed gazetteer entries.

The matcher's precision is the product's whole argument for being deterministic, so
the gazetteer is **never** written automatically — a human approves every entry (see
``scripts/curate_gazetteer.py``, which proposes verdicts and applies only what you
accept). This module holds the parts worth testing: the deterministic reject rules
and the source-editing primitives.

Nothing here runs in a request. It is imported by the curation script only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- deterministic pre-filter -----------------------------------------------
# Phrases that are never technical skills. Catching these before the LLM keeps the
# review list short and stops soft skills leaking into a taxonomy whose value is
# precision. Matched as whole words against the lowercased candidate.
_SOFT_SKILL_WORDS = frozenset({
    "collaboration", "collaborative", "communication", "teamwork", "team",
    "initiative", "curiosity", "curious", "passion", "passionate", "ownership",
    "adaptability", "adaptable", "flexibility", "mindset", "attitude", "fluency",
    "motivated", "driven", "proactive", "detail", "organised", "organized",
    "interpersonal", "leadership", "mentoring", "stakeholder", "empathy",
    "problem", "solving", "thinking", "willingness", "eagerness",
})

# Phrases describing a workplace or a market segment rather than a capability.
_CONTEXT_PATTERNS = (
    re.compile(r"\benvironments?\b"),
    re.compile(r"\bculture\b"),
    re.compile(r"\bfast[- ]paced\b"),
    re.compile(r"\bstartup\b"),
    re.compile(r"\benterprise\b.*\bplatforms?\b"),
    re.compile(r"\bcross[- ]functional\b"),
)

VERDICTS = ("alias", "canonical", "reject")

# Ordinary English words that are also product names. A single-token canonical from
# this set matches innocent prose — "moved the cursor", "a hive of activity" — and a
# false skill match is the one failure this taxonomy exists to prevent. Such entries
# belong in the matcher's `_NO_BARE` set with disambiguated aliases instead.
_AMBIGUOUS_WORDS = frozenset({
    "cursor", "hive", "go", "r", "c", "rust", "swift", "dash", "spark", "storm",
    "pandas", "beam", "arrow", "flink", "impala", "oracle", "cloud", "lens",
    "sage", "atlas", "chef", "puppet", "ray", "bolt", "click", "shell", "pipeline",
})


def needs_disambiguation(canonical: str) -> str | None:
    """Warn when a proposed canonical's bare form would match ordinary prose.

    Returns a human-readable warning, or ``None`` when the name is safe. Advisory:
    the reviewer decides whether to add it to ``_NO_BARE`` with explicit aliases.
    """
    name = canonical.strip()
    if " " in name or not name:
        return None  # multi-word names are specific enough to match safely
    if name.lower() in _AMBIGUOUS_WORDS:
        return (
            f"{name!r} is also an ordinary word — add it to gazetteer._NO_BARE and "
            "give it disambiguated aliases, or its bare form will match prose"
        )
    return None


@dataclass(frozen=True)
class Proposal:
    """One reviewed candidate. ``verdict`` is one of :data:`VERDICTS`."""

    candidate: str
    verdict: str
    canonical: str | None = None  # target canonical when verdict == 'alias'
    reason: str = ""
    occurrences: int = 1

    @property
    def accepted(self) -> bool:
        return self.verdict in ("alias", "canonical")


def auto_reject(candidate: str) -> str | None:
    """Reason this candidate is obviously not a technical skill, else ``None``.

    Deliberately conservative: it only fires on soft skills and workplace-context
    phrases. Anything ambiguous is left for the LLM proposal and the human.
    """
    low = candidate.lower().strip()
    if not low:
        return "empty"
    words = set(re.findall(r"[a-z]+", low))
    hit = words & _SOFT_SKILL_WORDS
    if hit:
        return f"soft skill ({sorted(hit)[0]})"
    for pattern in _CONTEXT_PATTERNS:
        if pattern.search(low):
            return "describes a workplace or market, not a capability"
    return None


# --- source editing ----------------------------------------------------------
# The SKILLS dict is hand-maintained and section-commented, so entries are edited
# in place with targeted line edits rather than regenerated from a parsed literal
# (which would discard the comments that make it readable).

_DICT_END = re.compile(r"^\}\s*$", re.MULTILINE)


def _canonical_line(source: str, canonical: str) -> re.Match | None:
    return re.search(
        rf'^(?P<indent>\s*)"{re.escape(canonical)}":\s*\[(?P<aliases>.*?)\],\s*$',
        source,
        re.MULTILINE,
    )


def has_canonical(source: str, canonical: str) -> bool:
    return _canonical_line(source, canonical) is not None


def add_alias(source: str, canonical: str, alias: str) -> str:
    """Append ``alias`` to an existing canonical's alias list.

    Aliases are stored lowercased (the matcher lowercases before comparing).
    Raises ``KeyError`` if the canonical is absent, and is a no-op when the alias
    is already present.
    """
    match = _canonical_line(source, canonical)
    if match is None:
        raise KeyError(f"canonical not found in gazetteer: {canonical!r}")

    alias_l = alias.lower().strip()
    existing = [a.strip().strip('"') for a in match.group("aliases").split(",") if a.strip()]
    if alias_l in existing or alias_l == canonical.lower():
        return source

    joined = ", ".join(f'"{a}"' for a in [*existing, alias_l])
    replacement = f'{match.group("indent")}"{canonical}": [{joined}],'
    return source[: match.start()] + replacement + source[match.end():]


def add_canonical(source: str, canonical: str, aliases: list[str], *, section: str) -> str:
    """Append a new canonical (with aliases) under a trailing ``# --- section ---``.

    New entries land in their own section so a reviewer can see at a glance what
    curation added versus what was hand-seeded.
    """
    if has_canonical(source, canonical):
        return source

    header = f"    # --- {section} ---"
    alias_l = [a.lower().strip() for a in aliases if a.strip() and a.lower() != canonical.lower()]
    joined = ", ".join(f'"{a}"' for a in dict.fromkeys(alias_l))
    entry = f'    "{canonical}": [{joined}],'

    end = _DICT_END.search(source)
    if end is None:
        raise ValueError("could not locate the end of the SKILLS dict")

    insert_at = end.start()
    block = entry + "\n"
    if header not in source:
        block = header + "\n" + block
    return source[:insert_at] + block + source[insert_at:]
