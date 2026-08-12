"""Resume structuring agent — turns raw resume text (from MarkItDown) into the
builder's structured section model. One Haiku call, temperature 0. It NEVER
invents content: a field it can't find comes back empty. Block/bullet ids are
assigned client-side, so they are absent from this schema."""

import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.llm import chat_model
from src.prompts import get_prompt

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
    conf: float = Field(default=1.0, ge=0.0, le=1.0, description="0..1 confidence that this section was parsed/mapped correctly")
    issue: str | None = Field(default=None, description="One short sentence for the user to confirm when the mapping was ambiguous; null when clean")
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

_HUMAN_OCR_PROMPT = (
    "This resume is a scanned/image document with no extractable text. Read all of its "
    "text and split it into structured sections following the schema. Copy the "
    "candidate's wording verbatim; never invent."
)


class ResumeStructurerAgent:
    PROMPT_NAME = "resume_structurer"

    def __init__(self, model: str | None = None):
        self.llm = chat_model("fast", override=model, max_tokens=8192, temperature=0)
        self.structured_llm = self.llm.with_structured_output(ResumeDocModel)
        self.prompt = get_prompt(self.PROMPT_NAME)

    async def structure(self, resume_text: str) -> ResumeDocModel:
        result: ResumeDocModel = await self.structured_llm.ainvoke([
            SystemMessage(content=self.prompt.text),
            HumanMessage(content=_HUMAN_PROMPT.format(resume_text=resume_text)),
        ])
        return result

    async def structure_from_file(self, data: bytes, media_type: str) -> ResumeDocModel:
        """OCR path for scanned PDFs (or images): send the file to the model's vision
        as a content block and structure it in one call — no extra dep.

        Uses langchain's **standard** multimodal blocks rather than a provider-native
        shape, so this path follows whatever provider the role is pointed at. Each
        integration translates them (langchain_anthropic turns ``file`` into its
        ``document``/``source`` block). ``filename`` is required by OpenAI for PDFs
        and ignored elsewhere.
        """
        import base64

        b64 = base64.standard_b64encode(data).decode("ascii")  # no newlines
        if media_type == "application/pdf":
            block: dict = {
                "type": "file", "base64": b64, "mime_type": media_type, "filename": "resume.pdf",
            }
        else:
            block = {"type": "image", "base64": b64, "mime_type": media_type}
        result: ResumeDocModel = await self.structured_llm.ainvoke([
            SystemMessage(content=self.prompt.text),
            HumanMessage(content=[block, {"type": "text", "text": _HUMAN_OCR_PROMPT}]),
        ])
        return result
