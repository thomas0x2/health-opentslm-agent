"""DeepSeek API backend (default). OpenAI-compatible transport, JSON mode."""
from __future__ import annotations
import json
from typing import Any

from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from sleep_pipeline.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from sleep_pipeline.rag.retrieve import Chunk
from sleep_pipeline.schemas import AdviceResponse

from .base import (
    AgentBackend,
    Tone,
    render_chunks,
    render_data_block,
    system_prompt,
)


class DeepSeekBackend:
    name = "deepseek"

    def __init__(self):
        if not DEEPSEEK_API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY not set")
        from openai import OpenAI  # local import keeps `import backends` cheap

        self._client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        self._RetryableErrors = self._collect_retryable_errors()

    @staticmethod
    def _collect_retryable_errors() -> tuple[type[Exception], ...]:
        import openai
        return (openai.APIError, openai.RateLimitError, openai.APIConnectionError)

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

        messages = [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": f"Reference excerpts:\n\n{context}"},
            {"role": "user", "content": data},
        ]

        raw = self._call(messages)
        parsed, err = _validate(raw)
        if parsed is not None:
            return parsed
        repair = messages + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    "Your previous response did not validate. Errors:\n"
                    f"{err}\n\nReissue as a single valid json object matching the schema."
                ),
            },
        ]
        raw2 = self._call(repair)
        parsed2, err2 = _validate(raw2)
        if parsed2 is not None:
            return parsed2
        raise RuntimeError(f"DeepSeek returned invalid JSON twice: {err2}")

    def _call(self, messages: list[dict]) -> str:
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(self._RetryableErrors),
            reraise=True,
        )
        def _do():
            resp = self._client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=1024,
            )
            return resp.choices[0].message.content or ""
        return _do()


def _validate(raw: str) -> tuple[dict | None, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"JSONDecodeError: {e}"
    try:
        validated = AdviceResponse.model_validate(data)
        return validated.model_dump(), ""
    except ValidationError as e:
        return None, str(e)
