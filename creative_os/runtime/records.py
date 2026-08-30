from __future__ import annotations

from dataclasses import asdict, dataclass
import json


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    execution_id: str
    task_id: str
    context_id: str
    capability: str
    domain: str
    model: str
    input_refs: tuple[tuple[str, str], ...]
    output_ref: str | None
    status: str
    started_at: str
    finished_at: str
    elapsed_seconds: float
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)
