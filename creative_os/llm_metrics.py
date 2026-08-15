from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class TimedCompletion:
    content: str
    elapsed_seconds: float
    usage: LLMUsage | None


def parse_usage(payload: dict[str, Any]) -> LLMUsage | None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    return LLMUsage(
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
        total_tokens=int(usage.get("total_tokens", 0)),
    )
