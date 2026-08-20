from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from creative_os.llm_metrics import LLMUsage
from creative_os.runtime.records import ExecutionRecord


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: str
    content: str


class ModelAdapter(Protocol):
    def complete(
        self,
        messages: list[ModelMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str | object:
        ...


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    task_id: str
    context_id: str
    capability: str
    domain: str
    model: str
    messages: tuple[ModelMessage, ...]
    input_refs: tuple[tuple[str, str], ...] = ()
    temperature: float = 0.7
    max_tokens: int = 1

    def validate(self) -> None:
        for name in ("task_id", "context_id", "capability", "domain", "model"):
            if not getattr(self, name).strip():
                raise ValueError(f"runtime request {name} is required")
        if not self.messages:
            raise ValueError("runtime request messages are required")
        if self.max_tokens <= 0:
            raise ValueError("runtime request max_tokens must be positive")
        if self.temperature < 0:
            raise ValueError("runtime request temperature must be non-negative")


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    output: str
    elapsed_seconds: float
    usage: LLMUsage | None
    record: ExecutionRecord
    reported_elapsed_seconds: float
