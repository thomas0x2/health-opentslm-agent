"""Backend protocol + shared prompt assembly. The two backends share everything
except the LLM call. Prompt order is fixed for prompt-caching reasons
(system → cached chunks → per-request data)."""
from __future__ import annotations
import json
from typing import Literal, Protocol, TYPE_CHECKING

from health_pipeline.rag.retrieve import Chunk

if TYPE_CHECKING:
    from health_pipeline.domains.base import Domain

Tone = Literal["clinical", "coach"]


TONE_INSTRUCTIONS = {
    "clinical": "Precise and clinical. Use specific numbers from the metrics. Avoid hyperbole.",
    "coach": "Warm and motivating, but specific. Use the user's numbers; suggest small wins.",
}


def system_prompt(domain: "Domain", tone: Tone) -> str:
    tone_str = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["clinical"])
    schema_json = json.dumps(domain.response_schema_json(), indent=2)
    cats = ", ".join(domain.advice_categories) if domain.advice_categories else "(none)"
    scores = ", ".join(domain.score_fields) if domain.score_fields else "(none)"

    extras = ""
    if domain.hard_rules_extra:
        extras = "\n" + "\n".join(f"- {r}" for r in domain.hard_rules_extra)

    return (
        f"{domain.persona}\n\n"
        "Hard rules:\n"
        "- Output ONLY a single json object that validates against the schema below. No prose outside json.\n"
        "- Cite at least one of the provided paper excerpts for each non-trivial claim, using the exact paper title and page from the excerpts.\n"
        "- Anything resembling a clinical concern MUST include the literal phrase 'discuss with a clinician' and MUST NOT prescribe treatment.\n"
        f"- Allowed category values: {cats}\n"
        f"- Required score keys (when applicable): {scores}\n"
        f"- Tone: {tone_str}"
        f"{extras}\n\n"
        f"Response JSON schema:\n{schema_json}"
    )


def render_chunks(chunks: list[Chunk]) -> str:
    """Cacheable context block. Order chunks by (paper_title, page) for stability."""
    if not chunks:
        return "(no excerpts available)"
    sorted_chunks = sorted(chunks, key=lambda c: (c.paper_title, c.page))
    parts = []
    for c in sorted_chunks:
        parts.append(f"[{c.paper_title}, p.{c.page}]\n{c.text}")
    return "\n\n---\n\n".join(parts)


def render_data_block(features: dict, narration: dict | None) -> str:
    """Per-request payload — placed AFTER the cacheable context."""
    body = {
        "features": features,
        "narration": narration,
    }
    instruction = (
        "\n\nWrite the response for THIS user, citing the excerpts above where they apply. "
        "Respond with a single json object matching the schema. No prose outside json."
    )
    return "User data (json):\n" + json.dumps(body, indent=2, default=str) + instruction


class AgentBackend(Protocol):
    name: str

    def synthesize(
        self,
        domain: "Domain",
        features: dict,
        narration: dict | None,
        chunks: list[Chunk],
        tone: Tone,
    ) -> dict: ...
