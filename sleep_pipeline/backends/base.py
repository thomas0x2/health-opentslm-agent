"""Backend protocol + shared prompt assembly.

The two backends share everything except the LLM call. Prompt order is fixed
for prompt-caching reasons (system → cached chunks → per-request data).
"""
from __future__ import annotations
import json
from typing import Literal, Protocol

from sleep_pipeline.rag.retrieve import Chunk
from sleep_pipeline.schemas import ADVICE_JSON_SCHEMA

Tone = Literal["clinical", "coach"]


SYSTEM_BASE = """You are a sleep-science assistant that returns structured json advice for a single user, grounded in (a) deterministic per-night and weekly metrics derived from their wearable, (b) a short narrative from a time-series model describing the night's physiology (may be null), and (c) excerpts from peer-reviewed sleep papers.

Hard rules:
- Output ONLY a single json object that validates against the provided schema. No prose outside json.
- Every advice item MUST cite at least one of the provided paper excerpts when making a non-trivial claim. Use the paper title and page exactly as labeled in the excerpts.
- Anything resembling a clinical concern (suspected sleep apnea, arrhythmia, severe insomnia) MUST go in the "medical_flag" category, MUST include the literal phrase "discuss with a clinician", and MUST NOT prescribe treatment.
- consistency_score (0-100): derive from the user's bedtime variability and the provided week metrics; quality_score (0-100): your overall read of the week.
- The "summary" should be at most 3 sentences.

Tone: {tone_instruction}
"""

TONE_INSTRUCTIONS = {
    "clinical": "Precise and clinical. Use specific numbers from the metrics. Avoid hyperbole.",
    "coach": "Warm and motivating, but specific. Use the user's numbers; suggest small wins.",
}


def system_prompt(tone: Tone) -> str:
    tone_str = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["clinical"])
    schema_json = json.dumps(ADVICE_JSON_SCHEMA, indent=2)
    return SYSTEM_BASE.format(tone_instruction=tone_str) + "\n\nResponse json schema:\n" + schema_json


def render_chunks(chunks: list[Chunk]) -> str:
    """Cacheable context block. Order chunks by (paper_title, page) for stability."""
    if not chunks:
        return "(no excerpts available)"
    sorted_chunks = sorted(chunks, key=lambda c: (c.paper_title, c.page))
    parts = []
    for c in sorted_chunks:
        parts.append(f"[{c.paper_title}, p.{c.page}]\n{c.text}")
    return "\n\n---\n\n".join(parts)


def render_data_block(features: dict, opentslm: dict | None) -> str:
    """Per-request payload — placed AFTER the cacheable context."""
    body = {
        "features": features,
        "opentslm": opentslm,
    }
    instruction = (
        "\n\nWrite the advice for THIS user, citing the excerpts above where they apply. "
        "Respond with a single json object matching the schema. No prose outside json."
    )
    return "User data (json):\n" + json.dumps(body, indent=2, default=str) + instruction


class AgentBackend(Protocol):
    name: str

    def synthesize(
        self,
        features: dict,
        opentslm: dict | None,
        chunks: list[Chunk],
        tone: Tone,
    ) -> dict: ...
