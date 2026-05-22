"""Shared pydantic models. Per-domain category whitelisting is enforced by the
engine (post-validation against `domain.advice_categories`) rather than via a
Literal, so each domain can ship its own category vocabulary."""
from __future__ import annotations
from typing import Optional, Union

from pydantic import BaseModel, Field


class Citation(BaseModel):
    paper: str
    page: int


class AdviceItem(BaseModel):
    category: str
    headline: str
    rationale: str
    actionable_step: str
    citations: list[Citation] = Field(default_factory=list)
    applies_to: Optional[str] = None  # ISO date or "week" or null


class AdviceResponseBase(BaseModel):
    """Default response shape: list of advice items + flexible score dict.
    Score keys are validated against `domain.score_fields` by the engine."""
    summary: str
    advice: list[AdviceItem] = Field(default_factory=list)
    scores: dict[str, int] = Field(default_factory=dict)
    red_flags: list[str] = Field(default_factory=list)
    medical_disclaimer: str
    caveats: list[str] = Field(default_factory=list)


class TriageEvidence(BaseModel):
    source: str
    signal: str
    value: Union[float, int, str]
    threshold: Union[float, int, str]


class TriageFlag(BaseModel):
    name: str
    severity: str  # none|low|medium|high
    evidence: list[TriageEvidence] = Field(default_factory=list)
    recommended_action: str
    urgency: str   # routine|prompt|urgent
    citations: list[Citation] = Field(default_factory=list)


class TriageResponse(BaseModel):
    """Triage / alert-doctor response. Each flag carries severity + urgency +
    a trail of evidence pointing back at the deterministic signals."""
    summary: str
    flags: list[TriageFlag] = Field(default_factory=list)
    overall_severity: int = 0
    escalation_recommended: bool = False
    red_flags: list[str] = Field(default_factory=list)
    medical_disclaimer: str
    caveats: list[str] = Field(default_factory=list)
