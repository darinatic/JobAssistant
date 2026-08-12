"""Deterministic page estimator for the ATS LaTeX resume templates.

Each template renders at a fixed density, so page count is a deterministic function
of the markdown. That lets us (a) tell the tailor a concrete line budget, and (b)
show the user a page estimate — without paying a Tectonic render on every tailor.

Density differs per template, so every constant here is **per template**. They are
measured, not guessed: ``scripts/calibrate_page_budget.py`` renders through the live
LaTeX pipeline and reads the PDFs back with pypdf. Element heights come from page
capacity in each element (a page holds B bullets but only S section headings, so a
section heading is B/S bullets tall), which captures the vertical spacing around an
element rather than just its text line. Re-run that script after any preamble edit
and copy the numbers back here.

The frontend mirrors these constants in ``frontend/src/lib/page-fit.ts`` to render the
live page badge — keep the two in sync.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

DEFAULT_TEMPLATE = "standard"


@dataclass(frozen=True)
class TemplateBudget:
    """Calibrated density constants for one LaTeX template."""

    chars_per_line: int
    """Visible characters that fit on one rendered line (text width / font size)."""

    capacity: float
    """One-page ceiling in estimator units. Above this, content spills to page 2."""

    target: float
    """Budget handed to the tailor. Below `capacity`, leaving a safety margin."""

    h_name: float
    """Height of the `# Name` header line."""

    h_section: float
    """Height of a `## Section` heading, including its rule and spacing."""

    h_role: float
    """Height of a `### Role` subheading."""


# Calibrated 2026-08-12 against the retuned 10pt preambles (see the module docstring).
# Section/role heights fell sharply from the old template's 2.0/1.3 because the
# retune cut \titlespacing and \parskip around headings.
#
# On `capacity`: this is a linear model of a nonlinear process (pagination), so the
# boundary is a band, not a point. Measured over resume-shaped documents, `standard`
# fit one page up to 58.7 and spilled from 62.1; `compact` fit to 62.2 and spilled
# from 68.6. Capacity is set at the CONSERVATIVE edge of each band on purpose:
# over-reporting pages just makes the user trim a little more, while under-reporting
# promises "fits one page" and then hands back a two-page PDF.
TEMPLATES: dict[str, TemplateBudget] = {
    "standard": TemplateBudget(
        chars_per_line=119, capacity=60.0, target=57.0,
        h_name=2.5, h_section=1.2, h_role=1.11,
    ),
    "compact": TemplateBudget(
        chars_per_line=124, capacity=64.0, target=61.0,
        h_name=2.5, h_section=1.14, h_role=1.08,
    ),
}


def budget_for(template: str | None = None) -> TemplateBudget:
    """Density constants for `template`, falling back to the standard template."""
    return TEMPLATES.get(template or DEFAULT_TEMPLATE, TEMPLATES[DEFAULT_TEMPLATE])


# Back-compat module-level aliases for the default template. Prefer `budget_for`.
PAGE_LINE_CAPACITY = TEMPLATES[DEFAULT_TEMPLATE].capacity
ONE_PAGE_TARGET = TEMPLATES[DEFAULT_TEMPLATE].target

# A trailing page holding at most this many rendered lines is "under-used" — a
# small remainder spilling past a full page. Below the threshold we recommend
# trimming up to the nearest full page; above it the last page carries real
# content and is left alone (the user can still compress via the aggressive style).
_TRAILING_TRIM_MAX_LINES = 15.0

_BULLET_RE = re.compile(r"^\s*[-*]\s+")
_MD_INLINE_RE = re.compile(r"\*\*|\*|`|_")


def _visible_len(line: str) -> int:
    text = _BULLET_RE.sub("", line)
    text = _MD_INLINE_RE.sub("", text)
    return len(text.strip())


def estimate_rendered_lines(markdown: str, *, template: str | None = None) -> float:
    """Estimate how many lines this markdown occupies in the rendered PDF."""
    b = budget_for(template)
    total = 0.0
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            total += b.h_name
        elif line.startswith("## "):
            total += b.h_section
        elif line.startswith("### "):
            total += b.h_role
        else:
            total += max(1, math.ceil(_visible_len(line) / b.chars_per_line))
    return total


def page_fit(markdown: str, *, template: str | None = None) -> dict:
    """Page-fit summary for a resume markdown. ``fits`` is the one-page verdict;
    ``overflow_lines`` is roughly how many lines to cut when it doesn't."""
    b = budget_for(template)
    lines = estimate_rendered_lines(markdown, template=template)
    est_pages = max(1, math.ceil(lines / b.capacity))
    return {
        "estimated_lines": round(lines, 1),
        "capacity": b.capacity,
        "estimated_pages": est_pages,
        "fits_one_page": lines <= b.capacity,
        "overflow_lines": max(0, math.ceil(lines - b.target)),
    }


def page_fit_target(markdown: str, *, template: str | None = None) -> dict:
    """Recommend trimming a small remainder off an under-used trailing page.

    Generalizes the one-page notion to any page count: if the content spills a
    little past a full page (the last page holds only a few lines), suggest
    trimming down to the nearest full page so the final page isn't wasted. When
    the last page carries real content, recommend nothing.

    Returns ``target_line_budget`` (the line budget to hand the tailor) and
    ``trim_lines`` (roughly how many lines to cut), or a no-op when the layout
    is already well-utilized.
    """
    b = budget_for(template)
    lines = estimate_rendered_lines(markdown, template=template)
    current_pages = max(1, math.ceil(lines / b.capacity))
    # Rendered lines sitting on the last (current) page.
    remainder = lines - (current_pages - 1) * b.capacity
    under_used = current_pages >= 2 and remainder <= _TRAILING_TRIM_MAX_LINES

    if under_used:
        target_pages = current_pages - 1
        target_line_budget = target_pages * b.target
        trim_lines = max(0, math.ceil(lines - target_line_budget))
    else:
        target_pages = current_pages
        target_line_budget = None
        trim_lines = 0

    return {
        "estimated_lines": round(lines, 1),
        "estimated_pages": current_pages,
        "under_used_trailing_page": under_used,
        "target_pages": target_pages,
        "target_line_budget": target_line_budget,
        "trim_lines": trim_lines,
    }
