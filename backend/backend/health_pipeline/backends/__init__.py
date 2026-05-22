"""Agent backend registry."""
from __future__ import annotations
from .base import AgentBackend


def get_backend(name: str) -> AgentBackend:
    name = name.lower()
    if name == "deepseek":
        from .deepseek_backend import DeepSeekBackend
        return DeepSeekBackend()
    if name == "anthropic":
        from .anthropic_backend import AnthropicBackend
        return AnthropicBackend()
    raise ValueError(f"Unknown AGENT_BACKEND: {name!r} (expected 'deepseek' or 'anthropic')")
