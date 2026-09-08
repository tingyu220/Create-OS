from dataclasses import dataclass
import json

import pytest

from creative_os.workspace import CommandBoundary, CommandRequest, CommandStatus, ProjectionSection, WorkspaceQueryAdapter, OperationsSnapshot, ProjectionRefreshCoordinator, sections_for_event, Freshness, ProjectionBundle, FileCommandResultStore, CommandResultRecord, CommandResult, CommandRecordState, ReserveStatus, CommandStoreError, FileRefreshStateStore, ProjectionRefreshStoreError


@dataclass
class Reader:
    snapshot: object
    heads: tuple[str, ...] = ("head",)

    def read_bundle(self, project_id: str):
        return ProjectionBundle(self.snapshot, OperationsSnapshot(project_id, 2, 1, 0, 1, None, ()), self.heads, {ProjectionSection.PROJECT: Freshness.FRESH, ProjectionSection.OPERATIONS: Freshness.FRESH})

    def current_heads(self, project_id: str):
        return self.heads


def test_query_returns_projection_envelope_with_operations_and_freshness():
    reader = Reader(snapshot=None)
    adapter = WorkspaceQueryAdapter(reader)
    result = adapter.get_workspace("p")
    assert result.project_id == "p"
    assert result.operations.task_count == 2


def test_query_requires_projection_bundle():
    reader = Reader(snapshot=None)
    result = WorkspaceQueryAdapter(reader).get_workspace("p")
    assert result.overall.value == "partial"


def test_refresh_failure_is_diagnostic_and_retryable():
    calls = []
    def build(project_id, sections, _refresh_id):
        calls.append((project_id, sections))
        if len(calls) == 1:
            raise RuntimeError("disk unavailable")
        return type("Receipt", (), {"snapshot_id": "snapshot-1"})()
    coordinator = ProjectionRefreshCoordinator(build)
    failed = coordinator.refresh("p", {ProjectionSection.PROJECT})
    assert failed.status == "failed"
    assert failed.diagnostic.code == "projection_refresh_failed"
    retried = coordinator.retry(failed.refresh_id)
    assert retried.status == "succeeded"

def test_invalid_refresh_receipt_is_recorded_and_retryable():
    calls = []
    def build(_project_id, _sections, _refresh_id):
        calls.append(1)
        return object() if len(calls) == 1 else type("Receipt", (), {"snapshot_id": "snapshot-1"})()
    coordinator = ProjectionRefreshCoordinator(build)
    failed = coordinator.refresh("p", {ProjectionSection.PROJECT})
    assert failed.status == "failed"
    assert failed.diagnostic.code == "projection_refresh_failed"
    assert coordinator.retry(failed.refresh_id).status == "succeeded"


def test_command_boundary_rejects_version_conflict_and_deduplicates_request():
    calls = []
    boundary = CommandBoundary(lambda request: calls.append(request) or ("event-1",), version_reader=lambda _target: 3)
    request = CommandRequest("c1", "r1", "actor", "target", {"x": 1}, expected_version=2, idempotency_key="version-conflict")
    conflict = boundary.execute(request)
    assert conflict.status == CommandStatus.REJECTED
    assert conflict.error.code == "version_conflict"
    request = CommandRequest("c1", "r1", "actor", "target", {"x": 1}, expected_version=3, idempotency_key="i1")
    accepted = boundary.execute(request)
    duplicate = boundary.execute(request)
    assert accepted.status == duplicate.status == CommandStatus.ACCEPTED
    assert len(calls) == 1

def test_unknown_event_has_no_implicit_projection_scope():
    assert sections_for_event("UnknownEvent") == frozenset()

def test_every_known_runtime_event_refreshes_project_and_operations():
    from creative_os.runtime.events import EventType
    expected = frozenset(ProjectionSection)
    assert all(sections_for_event(item.value) == expected for item in EventType)

def test_missing_projection_is_unavailable_and_overall_partial():
    result = WorkspaceQueryAdapter(Reader(snapshot=None)).get_workspace("p")
    assert result.sections[ProjectionSection.PROJECT].status == Freshness.UNAVAILABLE
    assert result.overall == Freshness.PARTIAL

def test_operations_snapshot_has_explicit_unknown_usage():
    operations = OperationsSnapshot("p", 1, 0, 0, 1, None, ())
    assert operations.usage is None

def _record(key="c"):
    return CommandResultRecord("fp-" + key, CommandRecordState.COMPLETED, CommandResult(CommandStatus.ACCEPTED, key, "r" + key))

def test_file_command_store_survives_restart_without_reexecuting_handler(tmp_path):
    first = FileCommandResultStore(tmp_path); first.reserve("k", "fp-k"); first.complete("k", "fp-k", _record("k").result)
    second = FileCommandResultStore(tmp_path)
    assert second.read("k") == _record("k")
    assert not first.path.with_suffix(".lock").exists()

def test_two_file_command_store_instances_merge_without_lost_update(tmp_path):
    first, second = FileCommandResultStore(tmp_path), FileCommandResultStore(tmp_path)
    first.reserve("a", "fp-a"); first.complete("a", "fp-a", _record("a").result); second.reserve("b", "fp-b"); second.complete("b", "fp-b", _record("b").result)
    reopened = FileCommandResultStore(tmp_path)
    assert reopened.read("a") and reopened.read("b") and not reopened.lock_path.exists()

def test_file_command_store_same_key_different_fingerprint_conflicts(tmp_path):
    store = FileCommandResultStore(tmp_path); store.reserve("k", "fp-k")
    assert store.reserve("k", "other").status == ReserveStatus.CONFLICT
    assert not store.lock_path.exists()

def test_file_command_store_rejects_corrupt_schema(tmp_path):
    path = tmp_path / ".creative_os" / "commands" / "results.json"; path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema_version": 999, "records": {}}), encoding="utf-8")
    with pytest.raises(CommandStoreError, match="command_store_corrupt"):
        FileCommandResultStore(tmp_path)
    assert not path.with_suffix(".lock").exists()

def test_command_complete_failure_leaves_reservation_and_prevents_reexecution(tmp_path):
    calls = []
    base = FileCommandResultStore(tmp_path)
    class FaultyCompleteStore:
        def read(self, key): return base.read(key)
        def reserve(self, key, fingerprint): return base.reserve(key, fingerprint)
        def complete(self, key, fingerprint, result): raise CommandStoreError("complete_failed")
    request = CommandRequest("c", "r", "actor", "target", {}, idempotency_key="k")
    first = CommandBoundary(lambda _request: calls.append(1) or ("event-1",), version_reader=lambda _: 0, store=FaultyCompleteStore()).execute(request)
    second = CommandBoundary(lambda _request: calls.append(1) or ("event-2",), version_reader=lambda _: 0, store=base).execute(request)
    assert first.error.code == second.error.code == "command_outcome_unknown"
    assert first.error.retryable is False and len(calls) == 1

def test_command_store_busy_is_failed_retryable_without_handler_execution(tmp_path):
    calls = []
    store = FileCommandResultStore(tmp_path)
    store.lock_path.parent.mkdir(parents=True, exist_ok=True); store.lock_path.write_text("busy", encoding="utf-8")
    request = CommandRequest("busy", "busy-request", "actor", "target", {}, idempotency_key="busy-key")
    result = CommandBoundary(lambda _request: calls.append(1) or (), version_reader=lambda _: 0, store=store).execute(request)
    assert result.status == CommandStatus.FAILED and result.error.code == "command_store_busy" and result.error.retryable
    assert calls == []
    store.lock_path.unlink()
    result = CommandBoundary(lambda _request: calls.append(1) or (), version_reader=lambda _: 0, store=store).execute(request)
    assert result.status == CommandStatus.ACCEPTED and calls == [1]

def test_persistent_command_boundary_deduplicates_rejected_result(tmp_path):
    calls = []
    request = CommandRequest("rejected", "request-rejected", "", "target", {}, idempotency_key="rejected-key")
    first = CommandBoundary(lambda _request: calls.append(1) or (), version_reader=lambda _: 0, store=FileCommandResultStore(tmp_path)).execute(request)
    second = CommandBoundary(lambda _request: calls.append(1) or (), version_reader=lambda _: 0, store=FileCommandResultStore(tmp_path)).execute(request)
    assert first.status == second.status == CommandStatus.REJECTED
    assert first.error.code == second.error.code == "validation_failed"
    assert calls == []

def test_handler_exception_is_unknown_and_never_automatically_reexecuted(tmp_path):
    calls = []
    request = CommandRequest("failed", "request-failed", "actor", "target", {}, idempotency_key="failed-key")
    def fail(_request):
        calls.append(1)
        raise RuntimeError("side effect outcome is unknown")
    first = CommandBoundary(fail, version_reader=lambda _: 0, store=FileCommandResultStore(tmp_path)).execute(request)
    second = CommandBoundary(fail, version_reader=lambda _: 0, store=FileCommandResultStore(tmp_path)).execute(request)
    assert first.error.code == second.error.code == "command_outcome_unknown"
    assert first.error.retryable is second.error.retryable is False
    assert calls == [1]

@pytest.mark.parametrize(
    "command_request",
    [
        CommandRequest("command", "", "actor", "target", {}),
        CommandRequest("command", "request", "actor", "target", {"invalid": object()}),
    ],
)
def test_command_boundary_returns_validation_error_for_invalid_web_request(command_request):
    result = CommandBoundary(lambda _request: (), version_reader=lambda _: 0).execute(command_request)
    assert result.status == CommandStatus.REJECTED
    assert result.error.code == "validation_failed"
    assert result.error.retryable is False

def test_command_boundary_does_not_invent_projection_refresh_id():
    result = CommandBoundary(lambda _request: ("event-1",), version_reader=lambda _: 0).execute(
        CommandRequest("command", "request", "actor", "target", {})
    )
    assert result.status == CommandStatus.ACCEPTED
    assert result.projection_refresh_id is None

def test_command_boundary_returns_real_projection_refresh_receipt():
    calls = []
    boundary = CommandBoundary(
        lambda _request: calls.append("domain") or ("event-1",),
        version_reader=lambda _: 0,
        refresh_scheduler=lambda refs, trace_id: calls.append((refs, trace_id)) or "refresh-real",
    )
    result = boundary.execute(CommandRequest("command", "request", "actor", "target", {}))
    assert result.status == CommandStatus.ACCEPTED
    assert result.projection_refresh_id == "refresh-real"
    assert calls[0] == "domain"
    assert calls[1][0] == ("event-1",)
    assert calls[1][1] == result.trace_id

def test_version_reader_failure_can_retry_without_stale_reservation(tmp_path):
    reads = []; handled = []
    def read_version(_target):
        reads.append(1)
        if len(reads) == 1:
            raise OSError("version store unavailable")
        return 2
    boundary = CommandBoundary(
        lambda _request: handled.append(1) or ("event-1",),
        version_reader=read_version,
        store=FileCommandResultStore(tmp_path),
    )
    request = CommandRequest("command", "request", "actor", "target", {}, 2, "retry-key")
    failed = boundary.execute(request)
    accepted = boundary.execute(request)
    assert failed.status == CommandStatus.FAILED
    assert failed.error.code == "command_version_unavailable"
    assert failed.error.retryable is True
    assert accepted.status == CommandStatus.ACCEPTED
    assert handled == [1]

@pytest.mark.parametrize("bad", [{"usage": True}, {"tasks": "bad"}, {"executions": "bad"}, {"errors": "bad"}, {"recovery": {"x": 1}}, {"retries": "bad"}, {"diagnostics": "bad"}, {"source_refs": "bad"}])
def test_projection_bundle_rejects_invalid_nested_operations(bad):
    from creative_os.workspace import decode_projection_bundle, ProjectionRepositoryError
    payload = {"schema_version": 1, "project": None, "operations": {"project_id": "p", "task_count": 0, "execution_count": 0, "failed_count": 0, "attempts": 0, "usage": None, "source_refs": [], "diagnostics": [], "tasks": [], "executions": [], "errors": [], "recovery": None, "retries": []}, "source_heads": [], "freshness": {"project": "unavailable", "operations": "unavailable"}, "diagnostics": [], "refresh_id": None}
    payload["operations"].update(bad)
    with pytest.raises(ProjectionRepositoryError): decode_projection_bundle(json.dumps(payload))

def _refresh_state(project, terminal=False):
    return {"project_id": project, "sections": ["project"], "status": "succeeded" if terminal else "failed", "attempts": 1, "diagnostic": None, "trace_id": "trace-" + project, "terminal": terminal, "receipt": {"refresh_id": project, "project_id": project, "sections": ["project"], "snapshot_id": "snapshot-" + project, "trace_id": "trace-" + project} if terminal else None, "requested_at": "2026-01-01T00:00:00Z", "completed_at": "2026-01-01T00:00:01Z"}

@pytest.mark.parametrize("mutate", [
    lambda row: row["receipt"].pop("snapshot_id"),
    lambda row: row["receipt"].update(trace_id="wrong-trace"),
    lambda row: row["receipt"].update(sections=[1]),
    lambda row: row["receipt"].update(sections=["unknown"]),
    lambda row: row["diagnostic"].pop("message"),
    lambda row: row.update(requested_at=42),
])
def test_refresh_state_store_rejects_invalid_nested_state(tmp_path, mutate):
    state = _refresh_state("a", True)
    state["diagnostic"] = {"code": "failed", "message": "failure"}
    mutate(state)
    path = tmp_path / "states.json"
    path.write_text(json.dumps({"a": state}), encoding="utf-8")
    with pytest.raises(ProjectionRefreshStoreError, match="store_corrupt"):
        FileRefreshStateStore(path)

def test_two_refresh_state_store_instances_merge_without_lost_update(tmp_path):
    first, second = FileRefreshStateStore(tmp_path / "states.json"), FileRefreshStateStore(tmp_path / "states.json")
    first.save("a", _refresh_state("a")); second.save("b", _refresh_state("b"))
    reopened = FileRefreshStateStore(tmp_path / "states.json")
    assert set(reopened.states) == {"a", "b"} and not reopened.path.with_suffix(".lock").exists()

def test_refresh_state_store_rejects_terminal_overwrite(tmp_path):
    store = FileRefreshStateStore(tmp_path / "states.json"); store.save("a", _refresh_state("a", True))
    with pytest.raises(ProjectionRefreshStoreError, match="terminal_conflict"):
        store.save("a", _refresh_state("changed"))
    assert not store.path.with_suffix(".lock").exists()

def test_refresh_receipt_binds_refresh_project_sections_snapshot_and_trace(tmp_path):
    calls = []
    class Snapshot:
        snapshot_id = "snapshot-fixed"
    def builder(project, sections, refresh_id): calls.append((project, sections, refresh_id)); return Snapshot()
    clock_values = iter(["2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z"])
    journal = tmp_path / "states.json"
    first = ProjectionRefreshCoordinator(builder, journal, clock=lambda: next(clock_values))
    result = first.refresh("project-a", {ProjectionSection.OPERATIONS, ProjectionSection.PROJECT})
    assert result.receipt.project_id == "project-a"
    assert result.receipt.sections == ("operations", "project")
    assert result.receipt.snapshot_id == "snapshot-fixed" and result.receipt.trace_id == result.trace_id
    second = ProjectionRefreshCoordinator(builder, journal)
    restored = second.retry(result.refresh_id)
    assert restored == result and len(calls) == 1
