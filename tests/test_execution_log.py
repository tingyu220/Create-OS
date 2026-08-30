import json

import pytest

from creative_os.runtime import AppendOnlyEventLog, EventLogError, EventType, ExecutionEvent, ExecutionRecord


def _record(status="succeeded"):
    return ExecutionRecord(
        execution_id="execution-1",
        task_id="task-1",
        context_id="context-1",
        capability="writing",
        domain="novel",
        model="test-model",
        input_refs=(("chapter", "chapter-1"),),
        output_ref="execution-1:output" if status == "succeeded" else None,
        status=status,
        started_at="2026-08-19T00:00:00+00:00",
        finished_at="2026-08-19T00:00:01+00:00",
        elapsed_seconds=1.0,
        error=None if status == "succeeded" else "failed",
    )


def test_execution_log_appends_execution_events_and_can_reload(tmp_path):
    path = tmp_path / ".creative_os/runtime/events.jsonl"
    log = AppendOnlyEventLog(path)

    events = log.append_execution(_record())

    assert [event.sequence for event in events] == [1, 2]
    assert [event.event_type for event in log.events()] == [EventType.CAPABILITY_CALLED, EventType.RESULT_GENERATED]
    reloaded = AppendOnlyEventLog(path)
    assert [event.event_id for event in reloaded.events()] == [event.event_id for event in events]


def test_failed_execution_is_recorded_as_task_failed(tmp_path):
    log = AppendOnlyEventLog(tmp_path / "events.jsonl")

    log.append_execution(_record("failed"))

    assert log.events()[-1].event_type == EventType.TASK_FAILED
    assert log.events()[-1].payload["error"] == "failed"


def test_execution_log_rejects_non_contiguous_events(tmp_path):
    path = tmp_path / "events.jsonl"
    event = ExecutionEvent(
        event_id="event-1",
        event_type=EventType.TASK_CREATED,
        occurred_at="2026-08-19T00:00:00+00:00",
        sequence=2,
        task_id="task-1",
        execution_id=None,
        payload={},
    )

    with pytest.raises(EventLogError, match="sequence"):
        AppendOnlyEventLog(path).append(event)
