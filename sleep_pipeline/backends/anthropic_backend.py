"""Anthropic / Claude backend with explicit prompt caching."""
from __future__ import annotations
import json
import re

from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from sleep_pipeline.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from sleep_pipeline.rag.retrieve import Chunk
from sleep_pipeline.schemas import AdviceResponse

from .base import (
    Tone,
    render_chunks,
    render_data_block,
    system_prompt,
)


class AnthropicBackend:
    name = "anthropic"

    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        import anthropic

        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self._RetryableErrors = self._collect_retryable_errors()

    @staticmethod
    def _collect_retryable_errors() -> tuple[type[Exception], ...]:
        import anthropic
        return (anthropic.APIError, anthropic.RateLimitError, anthropic.APIConnectionError)

    def synthesize(
        self,
        features: dict,
        opentslm: dict | None,
        chunks: list[Chunk],
        tone: Tone,
    ) -> dict:
        sys_p = system_prompt(tone)
        context = render_chunks(chunks)
        data = render_data_block(features, opentslm)

        system_blocks = [{"type": "text", "text": sys_p, "cache_control": {"type": "ephemeral"}}]
        user_blocks = [
            {
                "type": "text",
                "text": f"Reference excerpts:\n\n{context}",
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": data},
        ]
        raw = self._call(system_blocks, user_blocks)
        parsed, err = _validate(raw)
        if parsed is not None:
            return parsed
        repair_user = user_blocks + [
            {"type": "text", "text": f"Previous response failed validation: {err}. Reissue valid json only."}
        ]
        raw2 = self._call(system_blocks, repair_user)
        parsed2, err2 = _validate(raw2)
        if parsed2 is not None:
            return parsed2
        raise RuntimeError(f"Claude returned invalid JSON twice: {err2}")

    def _call(self, system_blocks: list[dict], user_blocks: list[dict]) -> str:
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(self._RetryableErrors),
            reraise=True,
        )
        def _do():
            resp = self._client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                temperature=0.3,
                system=system_blocks,
                messages=[{"role": "user", "content": user_blocks}],
            )
            return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return _do()


def _validate(raw: str) -> tuple[dict | None, str]:
    text = raw.strip()
    # Claude isn't a strict json-mode model; tolerate a fenced block.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"JSONDecodeError: {e}"
    try:
        validated = AdviceResponse.model_validate(data)
        return validated.model_dump(), ""
    except ValidationError as e:
        return None, str(e)
