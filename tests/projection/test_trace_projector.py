from __future__ import annotations

from creative_os.projection.projectors.trace import project_trace
from creative_os.projection.provenance import SourceRef
from creative_os.projection.source import ExecutionEventFact, ProjectFacts, RuntimeReportFact


def _event(sequence: int) -> ExecutionEventFact:
    reference = SourceRef("runtime_event", f"event-{sequence}", f"events.jsonl:sequence={sequence}", "c" * 64)
    return ExecutionEventFact(
        event_id=f"event-{sequence}",
        event_type="TaskStarted",
        occurred_at=f"2026-09-01T00:00:0{sequence}+00:00",
        sequence=sequence,
        task_id="chapter-001",
        execution_id=None,
        payload_json='{"secret":"must-not-leak"}',
        source_ref=reference,
    )


def test_trace_orders_events_and_does_not_expose_raw_payload() -> None:
    """捕获事件乱序或把完整敏感 payload 带入 UI 读模型的实现。"""
    events = (_event(3), _event(1), _event(2))
    facts = ProjectFacts("book-a", (), (), (), events, (), (), tuple(item.source_ref for item in events))

    trace = project_trace(facts)

    assert [entry.sequence for entry in trace.entries] == [1, 2, 3]
    assert all("must-not-leak" not in entry.summary for entry in trace.entries)


def test_trace_represents_writer_report_as_report_not_fabricated_event() -> None:
    reference = SourceRef("writer_validation_report", "real_writer_validation", "reports/real.json", "d" * 64)
    report = RuntimeReportFact(
        report_id="real_writer_validation",
        mode="live",
        model="test-model",
        chapter_id="chapter_001",
        stage="compile_candidate_ready",
        elapsed_seconds=12.5,
        source_ref=reference,
    )
    facts = ProjectFacts("book-a", (), (), (), (), (report,), (), (reference,))

    trace = project_trace(facts)

    assert trace.entries[0].trace_kind == "runtime_report"
    assert trace.entries[0].event_id is None
    assert trace.entries[0].source_refs == (reference,)
