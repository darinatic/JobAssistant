"""Deterministic one-page estimator for the ATS LaTeX resume template.

The template renders at a fixed density, so page count is a deterministic function
of the markdown. Empirical calibration (rendering resumes of growing length through
the real template and counting PDF pages with pypdf) put the one-page ceiling at
~46 rendered lines; it spilled to a 2nd page at ~48. Each element maps to an
estimated line height below, and long bullets wrap by character width.

This lets us (a) tell the tailor a concrete budget, and (b) show the user a page
estimate — without paying a Tectonic render on every tailor.
"""

from __future__ import annotations

import math
import re

# ~95 visible chars fit on one line at Latin Modern 11pt in this template's text
# width (an ~88-char bullet rendered to exactly one line in calibration).
_CHARS_PER_LINE = 95

# Estimated rendered line-height per markdown element (calibrated to the template).
_H_NAME = 2.5      # '# Name' — large heading + the contact line's own cost is separate
_H_SECTION = 2.0   # '## Section' — heading + the \section vertical spacing
_H_ROLE = 1.3      # '### Role/Project' — subheading, tighter

# One-page capacity in this estimator's units. Calibrated by rendering + counting
# pages: the last one-page resume scored 54.1 and the first two-page one scored 55.1,
# so 55 is the boundary. Target 52 leaves a safety margin for font/label variance.
PAGE_LINE_CAPACITY = 55.0
ONE_PAGE_TARGET = 52.0

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


def estimate_rendered_lines(markdown: str) -> float:
    """Estimate how many lines this markdown occupies in the rendered PDF."""
    total = 0.0
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            total += _H_NAME
        elif line.startswith("## "):
            total += _H_SECTION
        elif line.startswith("### "):
            total += _H_ROLE
        else:
            total += max(1, math.ceil(_visible_len(line) / _CHARS_PER_LINE))
    return total


def page_fit(markdown: str) -> dict:
    """Page-fit summary for a resume markdown. ``fits`` is the one-page verdict;
    ``overflow_lines`` is roughly how many lines to cut when it doesn't."""
    lines = estimate_rendered_lines(markdown)
    est_pages = max(1, math.ceil(lines / PAGE_LINE_CAPACITY))
    return {
        "estimated_lines": round(lines, 1),
        "capacity": PAGE_LINE_CAPACITY,
        "estimated_pages": est_pages,
        "fits_one_page": lines <= PAGE_LINE_CAPACITY,
        "overflow_lines": max(0, math.ceil(lines - ONE_PAGE_TARGET)),
    }


def page_fit_target(markdown: str) -> dict:
    """Recommend trimming a small remainder off an under-used trailing page.

    Generalizes the one-page notion to any page count: if the content spills a
    little past a full page (the last page holds only a few lines), suggest
    trimming down to the nearest full page so the final page isn't wasted. When
    the last page carries real content, recommend nothing.

    Returns ``target_line_budget`` (the line budget to hand the tailor) and
    ``trim_lines`` (roughly how many lines to cut), or a no-op when the layout
    is already well-utilized.
    """
    lines = estimate_rendered_lines(markdown)
    current_pages = max(1, math.ceil(lines / PAGE_LINE_CAPACITY))
    # Rendered lines sitting on the last (current) page.
    remainder = lines - (current_pages - 1) * PAGE_LINE_CAPACITY
    under_used = current_pages >= 2 and remainder <= _TRAILING_TRIM_MAX_LINES

    if under_used:
        target_pages = current_pages - 1
        target_line_budget = target_pages * ONE_PAGE_TARGET
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
