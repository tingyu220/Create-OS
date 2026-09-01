from __future__ import annotations

from dataclasses import dataclass

from creative_os.projection.provenance import SourceRef


@dataclass(frozen=True, slots=True)
class TraceEntrySnapshot:
    trace_kind: str
    sequence: int | None
    event_id: str | None
    event_type: str
    occurred_at: str
    task_id: str | None
    execution_id: str | None
    summary: str
    source_refs: tuple[SourceRef, ...]

    def __post_init__(self) -> None:
        if self.trace_kind not in {"event", "runtime_report"}:
            raise ValueError("trace_kind_invalid")
        if self.trace_kind == "event" and (self.sequence is None or self.event_id is None):
            raise ValueError("trace_event_identity_required")
        if self.trace_kind == "runtime_report" and self.event_id is not None:
            raise ValueError("runtime_report_must_not_fabricate_event_id")


@dataclass(frozen=True, slots=True)
class TraceSnapshot:
    entries: tuple[TraceEntrySnapshot, ...]
    source_refs: tuple[SourceRef, ...]
