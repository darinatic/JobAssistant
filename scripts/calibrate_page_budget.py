"""Re-measure the one-page estimator against real renders of the current font.

Renders resumes of growing length through the live LaTeX template, counts actual
PDF pages with pypdf, and prints (estimated_lines, actual_pages) so the boundary
constants in src/utils/page_budget.py can be set to where page 2 begins.
"""
import io

import pypdf

from src.utils.latex_renderer import markdown_to_latex, render_latex_pdf_sync
from src.utils.page_budget import estimate_rendered_lines

_HEADER = "# Jane Candidate\njane@example.com | github.com/jane\n\n## Experience\n### ML Engineer, Acme Corp | 2023 - Present\n"
_BULLET = "- Built and shipped a production RAG pipeline handling fifty thousand daily user queries reliably\n"


def _pages(md: str) -> int:
    pdf = render_latex_pdf_sync(markdown_to_latex(md), job_name="cal")
    return len(pypdf.PdfReader(io.BytesIO(pdf)).pages)


def main() -> None:
    for n in range(20, 60, 2):
        md = _HEADER + _BULLET * n
        est = estimate_rendered_lines(md)
        pages = _pages(md)
        print(f"bullets={n:3d}  est_lines={est:6.1f}  actual_pages={pages}")


if __name__ == "__main__":
    main()
