"""Pydantic models for the sleep-advice response."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

AdviceCategory = Literal[
    "consistency", "duration", "hygiene", "environment", "recovery", "medical_flag"
]


class Citation(BaseModel):
    paper: str
    page: int


class AdviceItem(BaseModel):
    category: AdviceCategory
    headline: str
    rationale: str
    actionable_step: str
    citations: list[Citation] = Field(default_factory=list)
    applies_to_night: str | None = None


class AdviceResponse(BaseModel):
    summary: str
    advice: list[AdviceItem] = Field(default_factory=list)
    consistency_score: int = 0
    quality_score: int = 0
    red_flags: list[str] = Field(default_factory=list)
    medical_disclaimer: str
    caveats: list[str] = Field(default_factory=list)


ADVICE_JSON_SCHEMA = AdviceResponse.model_json_schema()
