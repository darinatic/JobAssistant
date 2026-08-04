"""Resume structuring agent — turns raw resume text (from MarkItDown) into the
builder's structured section model. One Haiku call, temperature 0. It NEVER
invents content: a field it can't find comes back empty. Block/bullet ids are
assigned client-side, so they are absent from this schema."""

import logging
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.prompts import get_prompt
from src.utils.config import settings

log = logging.getLogger(__name__)


class ResumeField(BaseModel):
    label: str
    value: str = ""


class ResumeChip(BaseModel):
    text: str
    on: bool = True


class ResumeBullet(BaseModel):
    text: str
    on: bool = True


class ResumeBlock(BaseModel):
    title: str = ""
    org: str = Field(default="", description="Company / institution / issuer, plus location")
    dates: str = ""
    credential: str | None = None
    bullets: list[ResumeBullet] = Field(default_factory=list)


class ResumeSection(BaseModel):
    id: str = Field(description="Stable slug: contact, summary, experience, education, skills, certifications, awards, projects")
    label: str
    kind: Literal["fields", "text", "chips", "blocks"]
    on: bool = True
    fields: list[ResumeField] | None = None
    text: str | None = None
    chips: list[ResumeChip] | None = None
    blocks: list[ResumeBlock] | None = None


class ResumeDocModel(BaseModel):
    version: int = 1
    sections: list[ResumeSection]


_HUMAN_PROMPT = """Split the resume below into structured sections following the schema.

Resume:
---
{resume_text}
---

Return the structured sections. Copy the candidate's wording verbatim; never invent."""


class ResumeStructurerAgent:
    PROMPT_NAME = "resume_structurer"

    def __init__(self, model: str | None = None):
        self.llm = ChatAnthropic(
            model=model or settings.anthropic_haiku_model,
            api_key=settings.anthropic_api_key.get_secret_value(),
            max_tokens=8192,
            temperature=0,
        )
        self.structured_llm = self.llm.with_structured_output(ResumeDocModel)
        self.prompt = get_prompt(self.PROMPT_NAME)

    async def structure(self, resume_text: str) -> ResumeDocModel:
        result: ResumeDocModel = await self.structured_llm.ainvoke([
            SystemMessage(content=self.prompt.text),
            HumanMessage(content=_HUMAN_PROMPT.format(resume_text=resume_text)),
        ])
        return result
