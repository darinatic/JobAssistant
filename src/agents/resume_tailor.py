"""Resume tailoring agent."""

import re
from datetime import datetime
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.schemas import ParsedJobDescription, SkillMatch, TailoredResume
from src.prompts import get_prompt
from src.utils.config import settings

# Tailoring styles — how much *editorial latitude* the tailor takes. The honesty
# rules (no fabrication / domain / title / method invention) are invariant across
# ALL styles and live in the system prompt; only the cut/reorder/rephrase freedom
# below changes. Each entry is rule #7 of the human prompt.
TAILOR_STYLES = ("faithful", "balanced", "aggressive")

_STYLE_RULES = {
    "faithful": (
        "7. **Preserve everything — reorder and rephrase only.** Keep ALL roles, "
        "bullets, and sections; do not drop or merge them. Retune the summary and "
        "the ordering of skills and bullets to lead with what matches the JD, and "
        "tighten wording where natural. Favor completeness over brevity."
    ),
    "balanced": (
        "7. **Tighten toward one page.** Keep the overall structure, but condense "
        "weak or verbose bullets and DROP clearly irrelevant bullets and stale, "
        "unrelated roles. Lightly reorder sections by relevance. Aim for a focused "
        "one-page resume. Never fabricate to fill space."
    ),
    "aggressive": (
        "7. **Maximize fit — restructure for this role, ONE PAGE HARD.** The result "
        "MUST fit a single page: in this template that is about 45 lines of content "
        "(~40 short bullets TOTAL across the whole resume, fewer once section headers "
        "are counted). Budget space in priority order — header, summary, skills, then "
        "your MOST relevant experience — and cut from the bottom until it fits. CUT "
        "the Projects section FIRST: personal/side projects are the least load-bearing "
        "on an experienced resume, so drop them entirely (keep at most ONE line, and "
        "only if space clearly remains after the experience). Then drop older or "
        "low-relevance roles and weak bullets. Rewrite surviving bullet PHRASING to "
        "foreground what this JD wants (same underlying facts only — never a new claim, "
        "metric, tool, domain, or title). REORDER sections so the most role-relevant "
        "content leads. Every remaining line must earn its place against this JD."
    ),
}


def normalize_style(style: str | None, *, concise: bool = False) -> str:
    """Resolve the effective style. Falls back to the legacy ``concise`` flag
    (concise=True → 'balanced') and finally to 'faithful'."""
    if style in TAILOR_STYLES:
        return style
    return "balanced" if concise else "faithful"


def _budget_rule(target_line_budget: float) -> str:
    """Rule #7 for a "fit to page" re-tailor — an explicit rendered-line budget
    (from ``page_budget.page_fit_target``) that overrides the style's latitude
    rule. Used to compress a small remainder off an under-used trailing page."""
    n = int(round(target_line_budget))
    return (
        f"7. **Fit within about {n} rendered lines — hard length budget.** The current "
        "draft spills a little past a full page and wastes a near-empty trailing page. "
        "Compress to fit: cut the least role-relevant bullets and older/weaker roles "
        "first, tighten verbose bullets, and drop side projects before core experience. "
        "Do NOT fabricate, merge distinct roles, or drop required-skill coverage — trim "
        "only genuinely lower-value content, and preserve every metric on kept bullets."
    )


class ResumeTailorAgent:
    PROMPT_NAME = "resume_tailor"

    def __init__(self, model: str | None = None):
        self.llm = ChatAnthropic(
            model=model or settings.anthropic_sonnet_model,
            api_key=settings.anthropic_api_key.get_secret_value(),
            max_tokens=8192,
            temperature=0,
        )
        self.structured_llm = self.llm.with_structured_output(TailoredResume)
        self._master_cv: str | None = None
        self.prompt = get_prompt(self.PROMPT_NAME)

    @property
    def master_cv(self) -> str:
        if self._master_cv is None:
            self._master_cv = settings.get_master_cv()
        return self._master_cv

    def reload_cv(self) -> None:
        self._master_cv = None

    async def tailor(
        self,
        parsed_jd: ParsedJobDescription,
        skill_match: SkillMatch,
        *,
        master_cv: str | None = None,
        style: str = "faithful",
        target_line_budget: float | None = None,
    ) -> TailoredResume:
        messages = [
            SystemMessage(content=self.prompt.text),
            HumanMessage(content=self._build_tailor_prompt(
                parsed_jd, skill_match, master_cv=master_cv, style=style,
                target_line_budget=target_line_budget,
            )),
        ]
        return await self.structured_llm.ainvoke(messages)

    def tailor_sync(
        self,
        parsed_jd: ParsedJobDescription,
        skill_match: SkillMatch,
    ) -> TailoredResume:
        messages = [
            SystemMessage(content=self.prompt.text),
            HumanMessage(content=self._build_tailor_prompt(parsed_jd, skill_match)),
        ]
        return self.structured_llm.invoke(messages)

    def _build_tailor_prompt(
        self,
        parsed_jd: ParsedJobDescription,
        skill_match: SkillMatch,
        *,
        master_cv: str | None = None,
        style: str = "faithful",
        target_line_budget: float | None = None,
    ) -> str:
        cv = master_cv if master_cv is not None else self.master_cv
        # An explicit page-fit budget overrides the style's latitude rule.
        length_rule = (
            _budget_rule(target_line_budget) if target_line_budget is not None
            else _STYLE_RULES.get(style, _STYLE_RULES["faithful"])
        )

        return f"""Tailor this resume for the following job opportunity.

## Target Job

**Position**: {parsed_jd.title} at {parsed_jd.company}
**Location**: {parsed_jd.location}
**Experience Level**: {parsed_jd.experience_level.value}

### Required Skills (PRIORITIZE THESE)
{self._format_list(parsed_jd.required_skills)}

### Preferred Skills
{self._format_list(parsed_jd.preferred_skills)}

### Tech Stack
{', '.join(parsed_jd.tech_stack) if parsed_jd.tech_stack else 'Not specified'}

### Key Responsibilities
{self._format_list(parsed_jd.responsibilities[:5])}

### Keywords to Incorporate
{', '.join(parsed_jd.keywords_for_resume)}

## Match Analysis

**Score**: {skill_match.overall_score}/100
**Recommendation**: {skill_match.recommendation.value}

### Matched Skills to Emphasize
{self._format_list(skill_match.matched_required + skill_match.matched_preferred)}

### Transferable Skills to Highlight
{self._format_list(skill_match.transferable_skills)}

### Skills NOT in the candidate's CV — NEVER claim or add these (honesty rule)
{self._format_list(skill_match.missing_required)}

## Original Resume (Master CV)

{cv}

---

## Instructions

1. Tailor the resume above for this specific role.
2. **Markdown structure (required for correct PDF rendering)**: output clean
   markdown — `# Full Name` for the header; then ONE contact line with items
   separated by ` | ` and links as short text (`linkedin.com/in/x`,
   `github.com/x` — DROP the `https://`); `## ` for each section heading; `### `
   for each role/project title. Write EVERY experience and project achievement as
   its own bullet starting with `- ` (never as a plain paragraph). Put each role's
   date range at the END of its `### ` heading after a ` | ` separator (e.g.
   `### ML Engineer, Acme Corp | 2023 - Present`) so it right-aligns in the PDF;
   do NOT put the date on its own line. Use `**bold**` only for in-bullet emphasis.
3. **Honesty (hard rule)**: only use skills, tools, and experience that appear in
   the candidate's CV above. NEVER add any skill from the "Skills NOT in the
   candidate's CV" list, and never invent domains, metrics, methods, or titles.
3. **ATS exact-keyword matching**: where the CV genuinely supports a required
   skill, use the JD's EXACT wording for it — ATS parsers weight literal matches
   over synonyms. Spell out then abbreviate on first use, e.g. "Machine Learning
   (ML)", so both the full term and the acronym match.
4. Reorder the skills section and experience bullets to lead with matched skills.
   Keep **Skills** as a compact plain list — comma-separated, or the CV's own
   grouping if it already has one. Do NOT invent category headers like "Languages:"
   / "Frameworks:" / "Tools:": a flat list matches real resumes and saves space.
5. Incorporate keywords naturally (don't keyword-stuff).
6. **Summary — write like a person, not a keyword dump.** 2-3 tight sentences that
   LEAD with the single most relevant thing about this candidate for THIS role, so a
   recruiter is sold in the first sentence or two. Don't cram every skill in — leave
   the rest for the Skills and Experience sections. Plain, confident, specific;
   no buzzword stacking or generic "results-driven professional" filler.
{length_rule}
8. Output the complete markdown resume, then list changes made and keywords incorporated."""

    def _format_list(self, items: list[str]) -> str:
        if not items:
            return "- None specified"
        return "\n".join(f"- {item}" for item in items)

    async def save_tailored_resume(
        self,
        tailored: TailoredResume,
        parsed_jd: ParsedJobDescription,
        output_dir: Path | None = None,
    ) -> Path:
        if output_dir is None:
            output_dir = settings.project_root / settings.outputs_dir

        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{self._slugify(parsed_jd.company)}_{self._slugify(parsed_jd.title)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = output_dir / filename
        filepath.write_text(tailored.markdown_content, encoding="utf-8")
        return filepath

    def _slugify(self, text: str) -> str:
        slug = re.sub(r"[^\w\s-]", "", text.lower())
        slug = re.sub(r"[\s-]+", "_", slug)
        return slug[:30]

    async def save_as_pdf(
        self,
        tailored: TailoredResume,
        parsed_jd: ParsedJobDescription,
        output_dir: Path | None = None,
    ) -> Path:
        from src.utils.pdf_converter import convert_resume_to_pdf

        if output_dir is None:
            output_dir = settings.project_root / settings.outputs_dir

        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{self._slugify(parsed_jd.company)}_{self._slugify(parsed_jd.title)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = output_dir / filename

        candidate_name = "Resume"
        for line in tailored.markdown_content.split("\n"):
            if line.startswith("# "):
                candidate_name = line[2:].strip()
                break

        await convert_resume_to_pdf(tailored.markdown_content, filepath, candidate_name)
        return filepath

    async def save_both(
        self,
        tailored: TailoredResume,
        parsed_jd: ParsedJobDescription,
        output_dir: Path | None = None,
    ) -> tuple[Path, Path]:
        md_path = await self.save_tailored_resume(tailored, parsed_jd, output_dir)
        pdf_path = await self.save_as_pdf(tailored, parsed_jd, output_dir)
        return md_path, pdf_path


def format_tailored_resume_summary(tailored: TailoredResume) -> str:
    lines = ["## Tailoring Summary", "", "### Changes Made"]
    lines.extend(f"- {change}" for change in tailored.changes_made)
    lines.append("")
    lines.append("### Keywords Incorporated")
    lines.append(", ".join(tailored.keywords_added) if tailored.keywords_added else "None")

    if tailored.sections_reordered:
        lines.append("")
        lines.append("*Sections/bullets were reordered for relevance*")

    return "\n".join(lines)
