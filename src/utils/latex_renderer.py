"""Markdown → LaTeX → PDF via Tectonic.

The tailored resume is markdown (the editor + honesty linter operate on it). This
module is the *render* layer: it maps that markdown onto a deliberately ATS-safe
LaTeX template and compiles it with Tectonic.

ATS safety is the whole point of the template choices below: single column, a clean
sans-serif Roboto font with a proper T1/ToUnicode map (so PDF text extracts cleanly), plain
``\\section`` headings, no tables / multicol / floats / graphics, and links rendered as
visible text. Fancy LaTeX (multi-column, micro-typography, custom glyphs) is exactly what
silently breaks resume parsers, so it is intentionally absent.

Tectonic is a single self-contained binary (no full TeX Live). Install it and put it on
PATH; when it is missing, :class:`LatexUnavailable` is raised so the API can surface a
clear 503 instead of a 500.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


class LatexUnavailable(RuntimeError):
    """The Tectonic binary could not be found on PATH."""


class LatexCompileError(RuntimeError):
    """Tectonic ran but failed to produce a PDF."""


# --- LaTeX template ---------------------------------------------------------
# A single embedded preamble. `{body}` is filled with converted markdown.
# `article` is single-column by default; we never load multicol/minipage.
_RESUME_PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[default]{roboto}
\usepackage[a4paper,margin=0.6in]{geometry}
\usepackage[hidelinks]{hyperref}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage{parskip}

\pagestyle{empty}
\setlength{\parindent}{0pt}

% Tight, standard bullet lists — dense enough for one page, no custom glyphs.
\setlist[itemize]{leftmargin=1.25em, itemsep=1pt, topsep=2pt, parsep=0pt}

% Plain bold section headings with a full-width rule underneath. No color, no
% custom fonts — parsers read these as ordinary headings.
\titleformat{\section}{\large\bfseries}{}{0em}{\MakeUppercase}[\titlerule]
\titlespacing*{\section}{0pt}{10pt}{4pt}

\begin{document}
@@BODY@@
\end{document}
"""

_COVER_PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[default]{roboto}
\usepackage[a4paper,margin=1in]{geometry}
\usepackage{parskip}
\pagestyle{empty}
\setlength{\parindent}{0pt}
\linespread{1.08}
\begin{document}
@@BODY@@
\end{document}
"""


# --- escaping + inline formatting -------------------------------------------
_ESCAPE = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    # Common Unicode punctuation from PDF extraction / model output that the T1
    # font can't render (they silently vanish otherwise — e.g. contact separators).
    "•": r"\textbullet{}",     # •
    "·": r"\textperiodcentered{}",  # ·
    "–": "--",                 # – en dash
    "—": "---",                # — em dash
    "‘": "`", "’": "'",   # curly single quotes
    "“": "``", "”": "''", # curly double quotes
}
_ESCAPE_RE = re.compile("|".join(re.escape(k) for k in _ESCAPE))
# Contact-line separators (any run) + a leading protocol we strip for brevity.
_CONTACT_SEP_RE = re.compile(r"\s*[•·|]+\s*")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def latex_escape(text: str) -> str:
    """Escape every LaTeX special character in a plain string."""
    return _ESCAPE_RE.sub(lambda m: _ESCAPE[m.group()], text)


def _escape_url(url: str) -> str:
    # hyperref handles most of a URL verbatim; only % and # must be escaped.
    return url.replace("\\", r"\\").replace("%", r"\%").replace("#", r"\#")


def _inline(text: str) -> str:
    """Convert a markdown inline span to LaTeX: links, bold, italic, then escape.

    Links are pulled out first (their URLs contain characters the escaper would
    mangle), replaced with sentinels, and restored as ``\\href`` after the rest
    of the text is escaped.
    """
    links: list[tuple[str, str]] = []

    def _stash(m: re.Match) -> str:
        links.append((m.group(1), m.group(2)))
        return f"\x00{len(links) - 1}\x00"

    text = _LINK_RE.sub(_stash, text)
    text = latex_escape(text)
    text = _BOLD_RE.sub(lambda m: r"\textbf{" + m.group(1) + "}", text)
    text = _ITALIC_RE.sub(lambda m: r"\textit{" + m.group(1) + "}", text)

    def _restore(m: re.Match) -> str:
        label, url = links[int(m.group(1))]
        return r"\href{" + _escape_url(url) + "}{" + latex_escape(label) + "}"

    return re.sub(r"\x00(\d+)\x00", _restore, text)


def _is_rule(line: str) -> bool:
    s = line.strip()
    return len(s) >= 3 and set(s) <= {"-", "*", "_"}


def _contact_parts(lines: list[str]) -> list[str]:
    """Split header contact lines into clean items: break on •/·/| separators
    and strip protocols so links are short (and the line can wrap between items)."""
    parts: list[str] = []
    for line in lines:
        for p in _CONTACT_SEP_RE.split(line):
            p = re.sub(r"^https?://(www\.)?", "", p.strip())
            if p:
                parts.append(p)
    return parts


# --- markdown → LaTeX -------------------------------------------------------
def markdown_to_latex(md_content: str, candidate_name: str = "Resume") -> str:
    """Convert resume markdown into a full ATS-safe LaTeX document.

    Handles the constructs the tailor agent emits: an ``# Name`` header with
    contact lines beneath it, ``## Section`` headings, ``### Role`` subheadings,
    ``- `` bullet lists, and inline bold / italic / links. The header is centered;
    everything else is a single left-aligned column.
    """
    lines = md_content.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    in_list = False
    i = 0

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append(r"\end{itemize}")
            in_list = False

    # Header: the first `# ` line is the name; consecutive non-blank lines after
    # it (until a blank line or a `##`) are contact details.
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].startswith("# "):
        name = lines[i][2:].strip()
        i += 1
        # A markdown serializer inserts a blank line between the name and the
        # contact block. Skip ONE blank line, but only when a real contact line
        # (non-blank, non-heading) follows it — so "# Name" with no contact, or
        # "# Name" directly before "## Section", is unaffected.
        if (i + 1 < len(lines) and not lines[i].strip()
                and lines[i + 1].strip() and not lines[i + 1].startswith("#")):
            i += 1
        contact: list[str] = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith("#"):
            contact.append(lines[i].strip())
            i += 1
        out.append(r"\begin{center}")
        out.append(r"{\LARGE\bfseries " + _inline(name) + r"}\\[2pt]")
        parts = _contact_parts(contact)
        if parts:
            # \sloppy + spaces around the separator let the centered line wrap
            # between items instead of overflowing the margin on long URLs.
            joined = r" \textbullet{} ".join(_inline(p) for p in parts)
            out.append(r"{\small \sloppy " + joined + "}")
        out.append(r"\end{center}")
        out.append(r"\vspace{2pt}")

    for line in lines[i:]:
        stripped = line.strip()
        if not stripped:
            close_list()
            continue
        if stripped.startswith("## "):
            close_list()
            out.append(r"\section*{" + _inline(stripped[3:].strip()) + "}")
        elif stripped.startswith("### "):
            close_list()
            heading = stripped[4:].strip()
            # A trailing " | date" segment is right-aligned to the margin (standard
            # resume layout: role on the left, dates on the right). rpartition splits
            # on the LAST " | " so a company name with no pipe keeps the whole label.
            left, sep, date = heading.rpartition(" | ")
            if sep:
                out.append(r"\textbf{" + _inline(left.strip()) + r"}\hfill " + _inline(date.strip()) + r"\par")
            else:
                out.append(r"\textbf{" + _inline(heading) + r"}\par")
        elif stripped.startswith("#"):
            close_list()
            out.append(r"\textbf{" + _inline(stripped.lstrip("# ").strip()) + r"}\par")
        elif stripped[:2] in ("- ", "* ") or stripped.startswith("+ "):
            if not in_list:
                out.append(r"\begin{itemize}")
                in_list = True
            out.append(r"\item " + _inline(stripped[2:].strip()))
        elif _is_rule(stripped):
            close_list()
        else:
            close_list()
            out.append(_inline(stripped) + r"\par")

    close_list()
    return _RESUME_PREAMBLE.replace("@@BODY@@", "\n".join(out))


def cover_letter_to_latex(text: str) -> str:
    """Plain-text cover letter → LaTeX. Blank lines separate paragraphs."""
    paras = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]
    body = "\n\n".join(_inline(" ".join(p.split("\n"))) for p in paras)
    return _COVER_PREAMBLE.replace("@@BODY@@", body)


# --- compilation ------------------------------------------------------------
def _tectonic_candidates() -> list[Path]:
    """Common install locations, so the server finds Tectonic even when it isn't on
    the PATH of whatever shell launched it (a frequent cause of a spurious 503)."""
    out: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        out.append(Path(local) / "tectonic" / "tectonic.exe")
    home = Path.home()
    out += [
        home / "scoop" / "shims" / "tectonic.exe",
        home / ".cargo" / "bin" / "tectonic",
        Path("/usr/local/bin/tectonic"),
        Path("/opt/homebrew/bin/tectonic"),
        Path("/usr/bin/tectonic"),
    ]
    return out


def _tectonic_bin() -> str:
    from src.utils.config import settings

    # 1) explicit override (TECTONIC_PATH), 2) PATH, 3) known install locations.
    if settings.tectonic_path and Path(settings.tectonic_path).exists():
        return settings.tectonic_path
    binary = shutil.which("tectonic")
    if binary:
        return binary
    for cand in _tectonic_candidates():
        if cand.exists():
            return str(cand)
    raise LatexUnavailable(
        "Tectonic is not installed or not on PATH. Install it "
        "(e.g. `cargo install tectonic`, `scoop install tectonic`, or a release "
        "binary), or set TECTONIC_PATH, to render resume/cover-letter PDFs."
    )


def render_latex_pdf_sync(tex: str, *, job_name: str = "document") -> bytes:
    """Compile LaTeX source to PDF bytes. Blocking — call via ``asyncio.to_thread``."""
    binary = _tectonic_bin()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tex_path = tmp_path / f"{job_name}.tex"
        tex_path.write_text(tex, encoding="utf-8")
        proc = subprocess.run(
            [
                binary, "-X", "compile", str(tex_path),
                "--outdir", str(tmp_path),
                "--untrusted",
            ],
            capture_output=True,
            text=True,
        )
        pdf_path = tmp_path / f"{job_name}.pdf"
        if proc.returncode != 0 or not pdf_path.exists():
            tail = (proc.stderr or proc.stdout or "").strip()[-1500:]
            raise LatexCompileError(f"Tectonic failed (exit {proc.returncode}):\n{tail}")
        return pdf_path.read_bytes()


async def render_latex_pdf_bytes(tex: str, *, job_name: str = "document") -> bytes:
    import asyncio

    return await asyncio.to_thread(render_latex_pdf_sync, tex, job_name=job_name)


async def resume_markdown_to_pdf_bytes(md_content: str, candidate_name: str = "Resume") -> bytes:
    tex = markdown_to_latex(md_content, candidate_name=candidate_name)
    return await render_latex_pdf_bytes(tex, job_name="resume")


async def cover_letter_to_pdf_bytes(text: str, title: str = "Cover Letter") -> bytes:
    tex = cover_letter_to_latex(text)
    return await render_latex_pdf_bytes(tex, job_name="cover_letter")
