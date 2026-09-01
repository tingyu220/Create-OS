from __future__ import annotations

from creative_os.projection.source import ProjectFacts, ProjectionChangeSet
from creative_os.projection.trace import TraceEntrySnapshot, TraceSnapshot


def project_trace(
    facts: ProjectFacts,
    previous: TraceSnapshot | None = None,
    changes: ProjectionChangeSet | None = None,
) -> TraceSnapshot:
    del previous, changes
    entries: list[TraceEntrySnapshot] = []
    for event in sorted(facts.execution_events, key=lambda item: item.sequence):
        entries.append(TraceEntrySnapshot(
            trace_kind="event",
            sequence=event.sequence,
            event_id=event.event_id,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            task_id=event.task_id,
            execution_id=event.execution_id,
            summary=_event_summary(event.event_type, event.task_id),
            source_refs=(event.source_ref,),
        ))
    for report in sorted(facts.runtime_reports, key=lambda item: item.report_id):
        entries.append(TraceEntrySnapshot(
            trace_kind="runtime_report",
            sequence=None,
            event_id=None,
            event_type="WriterValidationReport",
            occurred_at="unknown",
            task_id=report.chapter_id,
            execution_id=None,
            summary=f"{report.mode}:{report.stage} model={report.model} elapsed={report.elapsed_seconds:.3f}s",
            source_refs=(report.source_ref,),
        ))
    references = tuple(dict.fromkeys(ref for entry in entries for ref in entry.source_refs))
    return TraceSnapshot(entries=tuple(entries), source_refs=references)


def _event_summary(event_type: str, task_id: str | None) -> str:
    return f"{event_type} task={task_id or 'unknown'}"
