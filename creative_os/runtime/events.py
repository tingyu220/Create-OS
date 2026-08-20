from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from creative_os.runtime.records import ExecutionRecord


class EventType(StrEnum):
    PROJECT_CREATED = "ProjectCreated"
    TASK_CREATED = "TaskCreated"
    TASK_STARTED = "TaskStarted"
    TASK_COMPLETED = "TaskCompleted"
    TASK_FAILED = "TaskFailed"
    CONTEXT_BUILT = "ContextBuilt"
    CAPABILITY_CALLED = "CapabilityCalled"
    RESULT_GENERATED = "ResultGenerated"
    REVIEW_PASSED = "ReviewPassed"
    REVIEW_FAILED = "ReviewFailed"
    KNOWLEDGE_UPDATED = "KnowledgeUpdated"
    STATE_CHANGED = "StateChanged"
    USER_REVISED = "UserRevised"


class EventLogError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    event_id: str
    event_type: EventType
    occurred_at: str
    sequence: int
    task_id: str | None
    execution_id: str | None
    payload: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, content: str) -> "ExecutionEvent":
        try:
            payload = json.loads(content)
            return cls(
                event_id=str(payload["event_id"]),
                event_type=EventType(payload["event_type"]),
                occurred_at=str(payload["occurred_at"]),
                sequence=int(payload["sequence"]),
                task_id=payload.get("task_id"),
                execution_id=payload.get("execution_id"),
                payload=dict(payload.get("payload", {})),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise EventLogError("invalid execution event") from error


class AppendOnlyEventLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._events = self._read()

    def append(self, event: ExecutionEvent) -> ExecutionEvent:
        expected = len(self._events) + 1
        if event.sequence not in (0, expected):
            raise EventLogError(f"event sequence must be {expected}")
        if event.sequence == 0:
            event = replace(event, sequence=expected)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(event.to_json() + "\n")
        self._events.append(event)
        return event

    def append_execution(self, record: ExecutionRecord) -> tuple[ExecutionEvent, ...]:
        capability = self.append(self._event(
            EventType.CAPABILITY_CALLED,
            record,
            {"capability": record.capability, "model": record.model},
        ))
        result_type = EventType.RESULT_GENERATED if record.status == "succeeded" else EventType.TASK_FAILED
        result = self.append(self._event(
            result_type,
            record,
            {"status": record.status, "output_ref": record.output_ref, "error": record.error},
        ))
        return capability, result

    def append_simple(
        self,
        event_type: EventType,
        *,
        task_id: str | None,
        payload: dict[str, Any],
        execution_id: str | None = None,
    ) -> ExecutionEvent:
        return self.append(ExecutionEvent(
            event_id=f"event-{uuid4().hex}",
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            sequence=0,
            task_id=task_id,
            execution_id=execution_id,
            payload=payload,
        ))

    def events(self) -> list[ExecutionEvent]:
        return list(self._events)

    def _event(self, event_type: EventType, record: ExecutionRecord, payload: dict[str, Any]) -> ExecutionEvent:
        return ExecutionEvent(
            event_id=f"event-{uuid4().hex}",
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            sequence=0,
            task_id=record.task_id,
            execution_id=record.execution_id,
            payload=payload,
        )

    def _read(self) -> list[ExecutionEvent]:
        if not self.path.exists():
            return []
        events: list[ExecutionEvent] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                event = ExecutionEvent.from_json(line)
                if event.sequence != len(events) + 1:
                    raise EventLogError("execution event sequence is not contiguous")
                events.append(event)
        return events
