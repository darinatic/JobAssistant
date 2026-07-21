"""Unit tests for the markdown → LaTeX render layer.

The escaping + markdown-mapping tests run everywhere. The end-to-end compile
test is gated on the Tectonic binary being installed (like the --run-llm-eval
gate for LLM tests) so CI without a LaTeX toolchain stays green.
"""

import pytest

from src.utils.latex_renderer import (
    LatexUnavailable,
    _tectonic_bin,
    cover_letter_to_latex,
    latex_escape,
    markdown_to_latex,
    render_latex_pdf_sync,
)


def _has_tectonic() -> bool:
    # Use the same resolver the renderer uses (PATH + config + known locations),
    # so the e2e test runs wherever Tectonic is actually reachable, not only PATH.
    try:
        return bool(_tectonic_bin())
    except LatexUnavailable:
        return False


_HAS_TECTONIC = _has_tectonic()
_SAMPLE_MD = """# Jane Candidate
jane@example.com | +65 9123 4567 | [linkedin.com/in/jane](https://linkedin.com/in/jane)

## Professional Summary
AI engineer with production LLM & RAG experience. 100% honest tailoring.

## Skills
Python, PyTorch, LangGraph, Supabase

## Work Experience

### Acme Corp — ML Engineer
**2023 - Present** | Singapore

- Built a RAG pipeline handling 50k daily queries at 90% accuracy
- Cut inference latency by 40% using *quantization* and **batching**

## Education
### National University of Singapore
B.Sc. Computer Science
"""


def test_latex_escape_specials():
    assert latex_escape("a & b") == r"a \& b"
    assert latex_escape("100%") == r"100\%"
    assert latex_escape("a_b #c $d") == r"a\_b \#c \$d"
    assert latex_escape("{x}") == r"\{x\}"


def test_markdown_to_latex_structure():
    tex = markdown_to_latex(_SAMPLE_MD)
    # Full compilable document.
    assert r"\documentclass" in tex
    assert r"\begin{document}" in tex and r"\end{document}" in tex
    # Single column ATS-safe template — no multicol/tables.
    assert "multicol" not in tex and "tabular" not in tex
    # Header centered with the name.
    assert r"\begin{center}" in tex
    assert "Jane Candidate" in tex
    # Sections became \section*.
    assert r"\section*{" in tex
    # Bullets became an itemize list.
    assert r"\begin{itemize}" in tex and r"\item" in tex
    # Inline emphasis converted.
    assert r"\textit{quantization}" in tex
    assert r"\textbf{batching}" in tex
    # Link converted to \href with the URL preserved.
    assert r"\href{https://linkedin.com/in/jane}" in tex


def test_markdown_to_latex_escapes_body_specials():
    tex = markdown_to_latex(_SAMPLE_MD)
    # The "90% accuracy" / "100% honest" percent signs must be escaped, not raw.
    assert "90\\% accuracy" in tex
    assert "100\\% honest" in tex


def test_cover_letter_paragraphs():
    tex = cover_letter_to_latex("Dear Hiring Manager,\n\nI am writing to apply.\n\nRegards,\nJane")
    assert r"\begin{document}" in tex
    # Two blank-line-separated paragraphs → separated in the body.
    assert "Dear Hiring Manager," in tex
    assert "I am writing to apply." in tex


def test_contact_line_separators_and_protocol_strip():
    md = "# Jane Doe\n+65 123 • jane@x.com • https://github.com/jane\n\n## Summary\nHi."
    tex = markdown_to_latex(md)
    assert "github.com/jane" in tex
    assert "https://" not in tex                 # protocol stripped
    assert "•" not in tex                    # raw bullet char never reaches LaTeX
    assert r"\textbullet" in tex                   # items joined by a real separator


def test_unicode_punctuation_escaped():
    out = latex_escape("a • b – c ’s")
    assert "•" not in out and "–" not in out
    assert r"\textbullet" in out


def _header(latex: str) -> str:
    """The centered header block, i.e. everything up to \\end{center}."""
    return latex.split(r"\end{center}")[0]


def test_contact_line_survives_blank_line_after_name():
    tight = "# Jane Tan\nAI Engineer · jane@x.com\n\n## Experience\n- Built RAG"
    spaced = "# Jane Tan\n\nAI Engineer · jane@x.com\n\n## Experience\n- Built RAG"
    # The blank-line (serializer) form must produce the SAME centered header
    # as the tight form — contact centered inside \begin{center}...\end{center}.
    assert _header(markdown_to_latex(spaced)) == _header(markdown_to_latex(tight))
    assert "AI Engineer" in _header(markdown_to_latex(spaced))


def test_name_without_contact_is_not_polluted_by_section():
    md = "# Jane Tan\n\n## Experience\n- Built RAG"
    out = markdown_to_latex(md)
    assert r"\section*{Experience}" in out
    assert "Experience" not in _header(out)  # section not absorbed as contact


def test_resume_uses_sans_serif_font():
    tex = markdown_to_latex(_SAMPLE_MD)
    # Modern sans-serif default, not the old Latin Modern serif.
    assert "roboto" in tex
    assert r"\usepackage{lmodern}" not in tex
    # ATS encoding preserved.
    assert r"\usepackage[T1]{fontenc}" in tex
    # Clean-extraction heading: real uppercase, not fake small-caps (which corrupt the text layer).
    assert r"\scshape" not in tex
    assert r"\MakeUppercase" in tex


def test_cover_letter_uses_sans_serif_font():
    tex = cover_letter_to_latex("Dear Hiring Manager,\n\nI am writing to apply.")
    assert "roboto" in tex
    assert r"\usepackage{lmodern}" not in tex


@pytest.mark.skipif(not _HAS_TECTONIC, reason="Tectonic not installed")
def test_end_to_end_compile_produces_pdf():
    tex = markdown_to_latex(_SAMPLE_MD)
    pdf = render_latex_pdf_sync(tex, job_name="resume")
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000
