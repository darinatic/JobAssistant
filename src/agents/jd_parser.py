"""JD parsing agent."""

import re
from typing import Optional

import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.schemas import ParsedJobDescription
from src.prompts import get_prompt
from src.utils.config import settings


_HUMAN_PROMPT_TEMPLATE = """Parse the following job description and extract all relevant information.

Job Description:
---
{jd_text}
---

Extract the structured information according to the schema. Be thorough with skills, responsibilities, and red flags."""


class JDParserAgent:
    PROMPT_NAME = "jd_parser"

    def __init__(self, model: str | None = None):
        self.llm = ChatAnthropic(
            model=model or settings.anthropic_haiku_model,
            api_key=settings.anthropic_api_key.get_secret_value(),
            max_tokens=4096,
            temperature=0,
        )
        self.structured_llm = self.llm.with_structured_output(ParsedJobDescription)
        self.prompt = get_prompt(self.PROMPT_NAME)

    def _build_messages(self, jd_text: str) -> list:
        return [
            SystemMessage(content=self.prompt.text),
            HumanMessage(content=_HUMAN_PROMPT_TEMPLATE.format(jd_text=jd_text)),
        ]

    async def parse(
        self,
        jd_text: str,
        source_url: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> ParsedJobDescription:
        result: ParsedJobDescription = await self.structured_llm.ainvoke(
            self._build_messages(jd_text)
        )
        result.source_url = source_url
        result.platform = platform or self._detect_platform(source_url)
        return result

    def parse_sync(
        self,
        jd_text: str,
        source_url: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> ParsedJobDescription:
        result: ParsedJobDescription = self.structured_llm.invoke(
            self._build_messages(jd_text)
        )
        result.source_url = source_url
        result.platform = platform or self._detect_platform(source_url)
        return result

    async def parse_from_url(self, url: str) -> ParsedJobDescription:
        jd_text = await self._fetch_jd_from_url(url)
        return await self.parse(jd_text, source_url=url, platform=self._detect_platform(url))

    async def _fetch_jd_from_url(self, url: str) -> str:
        # Simple HTTP fetch; LinkedIn/some ATS need browser automation instead.
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text

            html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
            html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()

            if len(text) < 100:
                raise ValueError(
                    f"Fetched content too short ({len(text)} chars). "
                    "URL may require browser automation."
                )

            return text

    def _detect_platform(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None

        url_lower = url.lower()
        for needle, name in (
            ("linkedin.com", "LinkedIn"),
            ("jobstreet", "Jobstreet"),
            ("mycareersfuture", "MyCareersFuture"),
            ("indeed.com", "Indeed"),
            ("glassdoor", "Glassdoor"),
            ("greenhouse.io", "Greenhouse"),
            ("lever.co", "Lever"),
            ("workday", "Workday"),
        ):
            if needle in url_lower:
                return name
        return "Direct"


def format_parsed_jd(parsed: ParsedJobDescription) -> str:
    lines = [
        f"## {parsed.title} at {parsed.company}",
        f"**Location:** {parsed.location} ({parsed.work_arrangement.value})",
        f"**Experience:** {parsed.experience_required} ({parsed.experience_level.value})",
        "",
    ]

    if parsed.salary_range:
        lines.append(f"**Salary:** {parsed.salary_range}")
        lines.append("")

    if parsed.required_skills:
        lines.append("### Required Skills")
        lines.extend(f"- {skill}" for skill in parsed.required_skills)
        lines.append("")

    if parsed.preferred_skills:
        lines.append("### Preferred Skills")
        lines.extend(f"- {skill}" for skill in parsed.preferred_skills)
        lines.append("")

    if parsed.tech_stack:
        lines.append("### Tech Stack")
        lines.append(", ".join(parsed.tech_stack))
        lines.append("")

    if parsed.responsibilities:
        lines.append("### Responsibilities")
        lines.extend(f"- {resp}" for resp in parsed.responsibilities[:5])
        lines.append("")

    if parsed.red_flags:
        lines.append("### Red Flags")
        for flag in parsed.red_flags:
            lines.append(f"- **{flag.severity.upper()}**: {flag.flag}")
            lines.append(f"  - {flag.reason}")
        lines.append("")

    if parsed.keywords_for_resume:
        lines.append("### Keywords for Resume")
        lines.append(", ".join(parsed.keywords_for_resume))

    return "\n".join(lines)
