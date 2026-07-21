"""Pydantic models for the Intel panel (red flags)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RedFlag(BaseModel):
    code: str
    label: str
    severity: Literal["info", "warn", "high"]
    evidence: str = ""
    source: str = ""
