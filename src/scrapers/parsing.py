"""Deterministic parsing helpers shared across scrapers.

Salary strings and seniority labels come off each board in slightly different
shapes; these pure functions turn them into a common structured form. No I/O,
no board knowledge beyond the platform tag — fully unit-testable, ~microseconds.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Salary
# ---------------------------------------------------------------------------

# A currency-ish number: optional $, digits with , separators, optional decimals,
# optional k suffix. Captured group is the numeric text (without $ or k).
_NUM = r"(?:S?\$|SGD|USD)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kK])?"
_NUM_RE = re.compile(_NUM)

# Period tokens. Monthly wins if both somehow appear (SG boards quote monthly).
_MONTHLY_RE = re.compile(r"\b(?:per\s+month|/\s*mo|/mo|pcm|monthly|month)\b", re.I)
_ANNUAL_RE = re.compile(r"\b(?:per\s+(?:year|annum)|/\s*(?:yr|year)|/yr|p\.?a\.?|annual(?:ly)?|year|annum)\b", re.I)

# "up to" / "from" single-bound markers.
_UPTO_RE = re.compile(r"\b(?:up\s+to|max(?:imum)?|below)\b", re.I)
_FROM_RE = re.compile(r"\b(?:from|min(?:imum)?|starting|above)\b", re.I)

# Plausible SGD pay bounds (monthly or annual) — filter out years / counts / noise.
_MIN_PLAUSIBLE = 100
_MAX_PLAUSIBLE = 10_000_000


def _to_int(num_text: str, k: str | None) -> int | None:
    try:
        val = float(num_text.replace(",", ""))
    except ValueError:
        return None
    if k:
        val *= 1000
    val = round(val)
    if _MIN_PLAUSIBLE <= val <= _MAX_PLAUSIBLE:
        return val
    return None


def _period(text: str) -> str | None:
    if _MONTHLY_RE.search(text):
        return "monthly"
    if _ANNUAL_RE.search(text):
        return "annual"
    return None


def parse_salary(text: str | None) -> tuple[int | None, int | None, str | None]:
    """Parse a freeform salary string into ``(min, max, period)``.

    Handles ranges ("$5,000 - $7,000 per month"), single bounds ("Up to $8k/mo",
    "From $5,000 annually"), ``k`` suffixes, and LinkedIn's "SGD 11,000.00/mo"
    form. ``period`` is ``'monthly'`` / ``'annual'`` / ``None``. Returns
    ``(None, None, None)`` when nothing plausible parses (e.g. "Competitive").
    """
    if not text:
        return (None, None, None)

    nums = [_to_int(n, k) for n, k in _NUM_RE.findall(text)]
    nums = [n for n in nums if n is not None]
    if not nums:
        return (None, None, None)

    period = _period(text)

    if len(nums) == 1:
        val = nums[0]
        # A single figure with an "up to" marker is a max; "from" is a min.
        if _UPTO_RE.search(text):
            return (None, val, period)
        if _FROM_RE.search(text):
            return (val, None, period)
        # Bare single figure — treat as a min ("$5,000/mo").
        return (val, None, period)

    lo, hi = min(nums[0], nums[1]), max(nums[0], nums[1])
    return (lo, hi, period)


def monthly_value(value: int | None, period: str | None) -> int | None:
    """Normalize a salary figure to a monthly SGD value for aggregation.

    ``annual`` divides by 12; ``monthly`` and unknown (``None``) pass through
    unchanged — preserving the historical assumption that period-less figures
    (overwhelmingly MCF) are monthly.
    """
    if value is None:
        return None
    if period == "annual":
        return round(value / 12)
    return value


# ---------------------------------------------------------------------------
# Experience / seniority
# ---------------------------------------------------------------------------

# Our normalized buckets (mirror SearchParams.experience_levels / search-filters.ts):
#   entry_level | associate | mid_senior | director | executive

# MyCareersFuture positionLevels -> bucket. Reverse of _POSITION_LEVELS in
# mycareersfuture.py; kept here so the mapping lives with the other parsers.
_MCF_LEVELS = {
    "fresh/entry level": "entry_level",
    "non-executive": "entry_level",
    "junior executive": "associate",
    "senior executive": "mid_senior",
    "manager": "mid_senior",
    "professional": "mid_senior",
    "middle management": "director",
    "senior management": "director",
}

# LinkedIn "Seniority level" criterion -> bucket. Near 1:1. Internship / Not
# Applicable -> None (outside our 5-value model; never guess).
_LINKEDIN_LEVELS = {
    "entry level": "entry_level",
    "associate": "associate",
    "mid-senior level": "mid_senior",
    "director": "director",
    "executive": "executive",
}

_LEVEL_TABLES = {
    "mycareersfuture": _MCF_LEVELS,
    "linkedin": _LINKEDIN_LEVELS,
}


def normalize_experience(raw: str | None, platform: str) -> str | None:
    """Best-effort map of a board's raw seniority string to a normalized bucket.

    Returns ``None`` for unknown platforms, unmatched strings, or values outside
    our 5-value model (e.g. "Internship", "Not Applicable") — never a guess.
    """
    if not raw:
        return None
    table = _LEVEL_TABLES.get((platform or "").lower())
    if not table:
        return None
    return table.get(raw.strip().lower())
