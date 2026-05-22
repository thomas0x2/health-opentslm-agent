"""Domain abstraction. Every recommendation domain (sleep, cardio, training,
nutrition, triage) ships a single frozen `Domain` instance describing the
prompt, schema, feature extractor, query heuristics, and optional TSLM
narrator. The engine consumes these uniformly."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional

from pydantic import BaseModel


@dataclass(frozen=True)
class Domain:
    name: str
    title: str
    description: str
    persona: str

    advice_categories: tuple[str, ...]
    score_fields: tuple[str, ...]

    response_model: type[BaseModel]

    always_on_queries: tuple[str, ...]

    # (df, start, end) -> dict
    extract: Callable[..., dict]

    # (features dict) -> list[str]
    derive_queries: Callable[[dict], list[str]]

    # (df, features) -> {summaries: list | str, error: str | None} | None
    narrate: Optional[Callable[..., Optional[dict]]] = None

    # (features dict) -> list[dict]; each dict shaped like TriageEvidence
    flag_rules: Optional[Callable[[dict], list[dict]]] = None

    accepts_cross_domain_evidence: bool = False

    # Extra rule bullets appended to the system prompt.
    hard_rules_extra: tuple[str, ...] = ()

    def response_schema_json(self) -> dict:
        return self.response_model.model_json_schema()
