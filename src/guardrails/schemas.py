"""Schemas for the PII guardrail layer."""

from pydantic import BaseModel, Field


class RedactionSummary(BaseModel):
    """What was stripped from the CV before the model ever saw it."""

    counts: dict[str, int] = Field(default_factory=dict)  # {"PERSON": 1, "EMAIL_ADDRESS": 1, ...}
    total: int = 0


class GuardrailReport(BaseModel):
    """Advisory report for one tailor/cover-letter call. Never blocks a response.

    ``available`` is False when redaction was disabled or errored and we failed
    open (tailored on the real CV) — the app keeps working, privacy just wasn't
    applied that time.
    """

    redaction: RedactionSummary = Field(default_factory=RedactionSummary)
    all_restored: bool = True   # did every redacted identifier round-trip through the model
    header_forced: bool = False  # did the header safety-net fire (model mangled a token)
    leaks: list[str] = Field(default_factory=list)  # human-readable notes when all_restored is False
    available: bool = True
