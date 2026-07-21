"""Resume markdown helpers.

The old Markdown→HTML→Patchright PDF path was retired in favour of the LaTeX
renderer (`src/utils/latex_renderer.py`). Only this tiny helper survives — it
pulls the candidate's name off the first `# ` heading for the PDF filename.
"""


def candidate_name_from_markdown(md_content: str, default: str = "Resume") -> str:
    for line in md_content.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return default
