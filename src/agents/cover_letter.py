"""Cover letter generation agent."""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.schemas import CoverLetter, ParsedJobDescription, SkillMatch, TailoredResume
from src.prompts import get_prompt
from src.utils.config import settings


class CoverLetterAgent:
    PROMPT_NAME = "cover_letter"

    def __init__(self, model: str | None = None):
        self.llm = ChatAnthropic(
            model=model or settings.anthropic_sonnet_model,
            api_key=settings.anthropic_api_key.get_secret_value(),
            max_tokens=2048,
        )
        self.structured_llm = self.llm.with_structured_output(CoverLetter)
        self.prompt = get_prompt(self.PROMPT_NAME)

    async def generate(
        self,
        parsed_jd: ParsedJobDescription,
        skill_match: SkillMatch,
        tailored_resume: TailoredResume,
        company_context: str | None = None,
    ) -> CoverLetter:
        messages = [
            SystemMessage(content=self.prompt.text),
            HumanMessage(content=self._build_prompt(parsed_jd, skill_match, tailored_resume, company_context)),
        ]
        return await self.structured_llm.ainvoke(messages)

    def generate_sync(
        self,
        parsed_jd: ParsedJobDescription,
        skill_match: SkillMatch,
        tailored_resume: TailoredResume,
        company_context: str | None = None,
    ) -> CoverLetter:
        messages = [
            SystemMessage(content=self.prompt.text),
            HumanMessage(content=self._build_prompt(parsed_jd, skill_match, tailored_resume, company_context)),
        ]
        return self.structured_llm.invoke(messages)

    def _build_prompt(
        self,
        parsed_jd: ParsedJobDescription,
        skill_match: SkillMatch,
        tailored_resume: TailoredResume,
        company_context: str | None,
    ) -> str:
        context_section = f"\n## Additional Company Context\n{company_context}\n" if company_context else ""

        return f"""Generate a personalized cover letter for this application.

## Target Position

**Company**: {parsed_jd.company}
**Role**: {parsed_jd.title}
**Location**: {parsed_jd.location} ({parsed_jd.work_arrangement.value})

### Key Requirements to Address
{self._format_list(parsed_jd.required_skills[:5])}

### Responsibilities to Reference
{self._format_list(parsed_jd.responsibilities[:3])}
{context_section}
## Candidate Strengths for This Role

### Matched Skills (emphasize these)
{self._format_list(skill_match.matched_required)}

### Transferable Skills (mention if relevant)
{self._format_list(skill_match.transferable_skills)}

### Match Score Context
Score: {skill_match.overall_score}/100
Reasoning: {skill_match.reasoning}

## Candidate Background (from tailored resume)

{tailored_resume.markdown_content}

---

## Instructions

1. Write a 250-350 word cover letter
2. Include at least ONE specific reference to {parsed_jd.company}
3. Highlight 2-3 specific achievements that match their requirements
4. Mention Singapore Citizen status (advantageous for local hiring)
5. End with a clear call to action
6. List what personalization points you included"""

    def _format_list(self, items: list[str]) -> str:
        if not items:
            return "- None specified"
        return "\n".join(f"- {item}" for item in items)


def format_cover_letter(cover_letter: CoverLetter) -> str:
    lines = [
        cover_letter.content,
        "",
        "---",
        f"*Word count: {cover_letter.word_count}*",
        "",
        "**Personalization points:**",
    ]
    lines.extend(f"- {point}" for point in cover_letter.personalization_points)
    return "\n".join(lines)
