"""Re-measure the page estimator against real renders of the current templates.

Two constants need calibrating whenever the LaTeX preambles change:

* ``_CHARS_PER_LINE`` — how many visible characters fit on one rendered line
  (a function of text width and font size, both of which the preamble sets).
* ``PAGE_LINE_CAPACITY`` / ``ONE_PAGE_TARGET`` — where page 2 begins, in the
  estimator's own units.

Both are measured per template by rendering through the live LaTeX pipeline and
reading the resulting PDF with pypdf. Run after any preamble edit and copy the
printed values into ``src/utils/page_budget.py``.

    .venv/Scripts/python.exe -m scripts.calibrate_page_budget
"""

from __future__ import annotations

import io

import pypdf

from src.utils.latex_renderer import markdown_to_latex, render_latex_pdf_sync
from src.utils.page_budget import TEMPLATES, estimate_rendered_lines

# Every probe must start with a real header block. `markdown_to_latex` treats the
# lines after `# Name` as the centered contact line until a blank line or a `##`,
# so a probe body pasted straight after the name gets swallowed into the header
# (and then silently overflows the page instead of paginating).
_PREFIX = "# Jane Candidate\njane@example.com | github.com/jane\n\n"
_H_NAME = 2.5  # header block cost in estimator units; appears exactly once

_HEADER = _PREFIX + "## Experience\n### ML Engineer, Acme Corp | 2023 - Present\n"
_BULLET = (
    "- Built and shipped a production RAG pipeline handling fifty thousand daily "
    "user queries reliably\n"
)
# Short enough to be one rendered line in every template, so "bullets per page"
# reads directly as the estimator's one-page capacity.
_SHORT_BULLET = "- Shipped a production RAG pipeline\n"

# Realistic prose for the wrap probe. Character width is proportional, so a
# synthetic filler like "wwww" measures the widest glyph rather than the average
# and badly under-counts. This is ordinary resume phrasing.
_PROSE = (
    "Designed and deployed a multi agent evaluation pipeline that scored "
    "conversation quality against defined criteria, reducing manual review effort "
    "by seventy percent across the team and improving release confidence. "
)


def _prose(n: int) -> str:
    """Exactly `n` visible characters of realistic prose."""
    reps = -(-n // len(_PROSE))
    return (_PROSE * reps)[:n]


def _render(md: str, template: str) -> bytes:
    return render_latex_pdf_sync(markdown_to_latex(md, template=template), job_name="cal")


def _pages(md: str, template: str) -> int:
    return len(pypdf.PdfReader(io.BytesIO(_render(md, template))).pages)


def _rendered_line_count(md: str, template: str) -> int:
    """How many distinct baselines the rendered text occupies (page 1)."""
    page = pypdf.PdfReader(io.BytesIO(_render(md, template))).pages[0]
    baselines: set[float] = set()

    def visit(text, cm, tm, font_dict, font_size):  # noqa: ANN001
        if text.strip():
            baselines.add(round(tm[5], 1))

    page.extract_text(visitor_text=visit)
    return len(baselines)


def calibrate_chars_per_line(template: str) -> int:
    """Longest single bullet that still renders on ONE line.

    Binary-searches the bullet length: the estimator's ``_CHARS_PER_LINE`` should
    sit at that boundary so a bullet is counted as wrapping exactly when it does.
    """
    header_lines = _rendered_line_count("# X\n\n## S\n", template)

    def wraps(n: int) -> bool:
        md = "# X\n\n## S\n- " + _prose(n) + "\n"
        return _rendered_line_count(md, template) > header_lines + 1

    lo, hi = 40, 220
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if wraps(mid):
            hi = mid - 1
        else:
            lo = mid
    return lo


def _max_on_one_page(unit: str, template: str, *, lo: int = 2, hi: int = 200) -> int:
    """How many of `unit` fit on a single page. Binary search on real renders."""

    def fits(n: int) -> bool:
        return _pages(_PREFIX + unit * n, template) == 1

    while lo < hi:
        mid = (lo + hi + 1) // 2
        if fits(mid):
            lo = mid
        else:
            hi = mid - 1
    return lo


def calibrate_heights(template: str) -> dict[str, float]:
    """Per-element line heights, derived from page capacity in each element.

    A bullet is the unit (height 1.0). If a page holds B bullets but only S
    section headings, a section heading is B/S bullets tall. This measures the
    element's true vertical cost — text line plus the spacing around it — instead
    of guessing at it.
    """
    per_bullet = _max_on_one_page(_SHORT_BULLET, template)
    per_section = _max_on_one_page("## Section Heading\n", template)
    per_role = _max_on_one_page("### Role, Company | 2023 - Present\n", template)
    # All three share the same fixed header prefix, so it cancels in the ratios.
    return {
        "bullets_per_page": float(per_bullet),
        # Capacity counts the header block too, since the estimator does.
        "capacity": round(_H_NAME + per_bullet, 1),
        "h_section": round(per_bullet / per_section, 2),
        "h_role": round(per_bullet / per_role, 2),
    }


def _realistic_doc(sections: int, roles_per_section: int, bullets_per_role: int) -> str:
    """A resume-shaped document: multiple sections, roles, and wrapping bullets.

    Uniform-short-bullet calibration is optimistic on real resumes, which mix long
    wrapping bullets with many headings. The capacity boundary has to be validated
    against this shape or the one-page badge lies at the margin.
    """
    out = [_PREFIX.rstrip("\n"), ""]
    for s in range(sections):
        out.append(f"## Section {s + 1}")
        out.append("")
        for r in range(roles_per_section):
            out.append(f"### Role {r + 1}, Company {r + 1} | 2023 - Present")
            out.append("")
            for b in range(bullets_per_role):
                out.append("- " + _prose(90 + (b * 37) % 110))
            out.append("")
    return "\n".join(out) + "\n"


def validate_capacity(template: str) -> None:
    """Print (estimated_lines, actual_pages) over resume-shaped documents.

    The capacity constant must sit below every estimate that actually spills, and
    above every estimate that fits — print both edges so it can be set honestly.
    """
    shapes = [
        (s, r, b)
        for s in (3, 5, 7)
        for r in (1, 2, 3)
        for b in (2, 3)
    ]
    fits: list[float] = []
    spills: list[float] = []
    for shape in shapes:
        md = _realistic_doc(*shape)
        est = estimate_rendered_lines(md, template=template)
        if est > 130:  # far past the boundary; no information, skip the render
            continue
        pages = _pages(md, template)
        (fits if pages == 1 else spills).append(est)
    if fits:
        print(f"  realistic 1-page max    : {max(fits):.1f}")
    if spills:
        print(f"  realistic 2-page min    : {min(spills):.1f}")
    if fits and spills:
        print(f"  -> safe capacity        : {min(spills) - 0.5:.1f}")


def main() -> None:
    for template in TEMPLATES:
        print(f"\n=== {template} ===")
        print(f"  chars per rendered line : {calibrate_chars_per_line(template)}")
        h = calibrate_heights(template)
        print(f"  short bullets per page  : {h['bullets_per_page']:.0f}")
        print(f"  section heading height  : {h['h_section']}")
        print(f"  role heading height     : {h['h_role']}")
        print(f"  -> uniform capacity     : {h['capacity']:.1f}")
        validate_capacity(template)


if __name__ == "__main__":
    main()
