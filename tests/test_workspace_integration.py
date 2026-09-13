import json
import ast
from http.client import HTTPConnection
from threading import Thread

from creative_os.projection.builder import ProjectProjectionBuilder
from creative_os.projection.filesystem_source import FilesystemProjectSource
from creative_os.projection.repository import FileProjectionRepository, RepositoryRefreshBuilder
from creative_os.runtime.events import AppendOnlyEventLog, EventType
from creative_os.workspace import ProjectionRefreshCoordinator, WorkspaceQueryAdapter, ProjectionSection
from creative_os.workspace import CommandBoundary, FileCommandResultStore
from creative_os.workspace_command_adapter import WorkspaceCommandAdapter, WorkspaceProjectionRefreshScheduler, WorkspaceRefreshCommandHandler
from creative_os.web_workspace import WorkspaceWebAdapter, create_server


def _project(root):
    (root / "project.json").write_text(json.dumps({"id": "p"}), encoding="utf-8")
    status = root / "production" / "runs" / "status" / "chapter_001_status.json"
    status.parent.mkdir(parents=True)
    status.write_text(json.dumps({"chapter": 1, "status": "pass", "attempts": 1, "elapsed_seconds": 1.0, "issues": []}), encoding="utf-8")
    return root


def _chain(root):
    source = FilesystemProjectSource(root)
    repository = FileProjectionRepository(root)
    builder = RepositoryRefreshBuilder(root, repository)
    coordinator = ProjectionRefreshCoordinator(builder, repository.journal_path)
    return source, repository, coordinator, WorkspaceQueryAdapter(repository)


def test_domain_event_refresh_returns_latest_workspace(tmp_path):
    root = _project(tmp_path)
    log = AppendOnlyEventLog(root / ".creative_os" / "runtime" / "events.jsonl")
    log.append_simple(EventType.TASK_STARTED, task_id="task-1", payload={})
    log.append_simple(EventType.TASK_COMPLETED, task_id="task-1", payload={})
    source, repository, coordinator, query = _chain(root)
    result = coordinator.handle_event("p", log.events()[-1])
    workspace = query.get_workspace("p")
    assert result.status.value == "succeeded"
    assert workspace.refresh_id == result.refresh_id
    assert workspace.overall.value == "partial"
    assert workspace.operations.execution_count == 2
    assert workspace.snapshot.trace.entries[0].source_refs
    assert workspace.operations.usage is None
    assert workspace.operations.recovery is None
    assert workspace.operations.retries == ()
    assert {item.code for item in workspace.operations.diagnostics} == {
        "operations_usage_unavailable",
        "operations_recovery_unavailable",
        "operations_retry_unavailable",
    }


def test_new_source_head_marks_persisted_projection_stale(tmp_path):
    root = _project(tmp_path)
    log = AppendOnlyEventLog(root / ".creative_os" / "runtime" / "events.jsonl")
    source, repository, coordinator, query = _chain(root)
    coordinator.refresh("p", {ProjectionSection.PROJECT})
    assert query.get_workspace("p").overall.value == "partial"
    log.append_simple(EventType.TASK_STARTED, task_id="task-2", payload={})
    assert query.get_workspace("p").sections[ProjectionSection.PROJECT].status.value == "stale"
    assert query.get_workspace("p").sections[ProjectionSection.OPERATIONS].status.value == "stale"

def test_refresh_failure_survives_restart_and_retry_preserves_stale_bundle(tmp_path):
    root = _project(tmp_path); log = AppendOnlyEventLog(root / ".creative_os" / "runtime" / "events.jsonl")
    source, repository, coordinator, query = _chain(root); coordinator.refresh("p", {ProjectionSection.PROJECT})
    log.append_simple(EventType.TASK_STARTED, task_id="task-3", payload={})
    failed = ProjectionRefreshCoordinator(lambda *_: (_ for _ in ()).throw(RuntimeError("broken")), repository.journal_path).refresh("p", {ProjectionSection.PROJECT})
    assert failed.status.value == "failed" and failed.attempts == 1
    assert query.get_workspace("p").sections[ProjectionSection.PROJECT].status.value == "stale"
    restarted = ProjectionRefreshCoordinator(RepositoryRefreshBuilder(root, repository), repository.journal_path)
    retried = restarted.retry(failed.refresh_id)
    assert retried.status.value == "succeeded" and query.get_workspace("p").overall.value == "partial"

def test_workspace_query_adapter_has_projection_only_dependency():
    tree = ast.parse(open("creative_os/workspace_query.py", encoding="utf-8").read())
    names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
    assert not any(x in str(names) for x in ("domains", "runtime", "knowledge", "filesystem_source"))
    assert "operations_reader" not in open("creative_os/workspace_query.py", encoding="utf-8").read()

def test_command_boundary_contract_is_web_reusable():
    calls = []; refresh_calls = []; enabled = [False]
    boundary = __import__("creative_os.workspace", fromlist=["CommandBoundary"]).CommandBoundary(
        lambda r: (_ for _ in ()).throw(RuntimeError()) if not enabled[0] else ("event-1",),
        version_reader=lambda _: 2,
        refresh_scheduler=lambda _request, refs, trace_id: refresh_calls.append((refs, trace_id)) or "refresh-1",
    )
    from creative_os.workspace import CommandRequest, CommandStatus
    request = CommandRequest("c", "r", "actor", "target", {"x": 1}, 2, "key")
    failed = boundary.execute(request); assert failed.status == CommandStatus.FAILED and failed.error.code == "command_outcome_unknown" and not failed.error.retryable
    enabled[0] = True; accepted = boundary.execute(request); assert accepted.status == CommandStatus.ACCEPTED
    assert accepted.audit_ref and accepted.trace_id and accepted.emitted_event_refs and accepted.projection_refresh_id
    assert refresh_calls == [(("event-1",), accepted.trace_id)]
    assert boundary.execute(request) == accepted
    conflict = boundary.execute(CommandRequest("c", "r2", "actor", "target", {"x": 2}, 2, "key"))
    assert conflict.error.code == "idempotency_conflict"


def _web_chain(root):
    source = FilesystemProjectSource(root)
    repository = FileProjectionRepository(root)
    coordinator = ProjectionRefreshCoordinator(RepositoryRefreshBuilder(root, repository), repository.journal_path)
    query = WorkspaceQueryAdapter(repository)
    handler = WorkspaceRefreshCommandHandler("p")
    boundary = CommandBoundary(
        handler,
        version_reader=lambda _target: 0,
        store=FileCommandResultStore(root),
        refresh_scheduler=WorkspaceProjectionRefreshScheduler(coordinator),
        request_validator=handler.validate,
    )
    server = create_server(WorkspaceWebAdapter(query, "p"), command_adapter=WorkspaceCommandAdapter(boundary), port=0)
    return source, repository, coordinator, query, server


def _refresh_request():
    return {
        "command_id": "refresh_workspace_projection",
        "request_id": "request-refresh-1",
        "actor": "local-user",
        "target": "p",
        "payload": {"sections": ["project", "operations"]},
        "expected_version": None,
        "idempotency_key": "refresh-key-1",
    }


def test_web_refresh_command_returns_real_receipt_and_replay_is_idempotent(tmp_path):
    root = _project(tmp_path)
    _source, repository, coordinator, query, server = _web_chain(root)
    initial = coordinator.refresh("p", {ProjectionSection.PROJECT, ProjectionSection.OPERATIONS})
    assert initial.status.value == "succeeded"
    log = AppendOnlyEventLog(root / ".creative_os" / "runtime" / "events.jsonl")
    log.append_simple(EventType.TASK_STARTED, task_id="task-refresh", payload={})
    assert query.get_workspace("p").sections[ProjectionSection.PROJECT].status.value == "stale"
    body = json.dumps(_refresh_request()).encode("utf-8")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection(*server.server_address)
        connection.request("POST", "/api/commands/refresh-workspace", body=body, headers={"Content-Type": "application/json", "Content-Length": str(len(body))})
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 202
        assert payload["status"] == "accepted"
        workspace = query.get_workspace("p")
        assert payload["projection_refresh_id"] == workspace.refresh_id
        assert workspace.sections[ProjectionSection.PROJECT].status.value != "stale"
        assert workspace.sections[ProjectionSection.OPERATIONS].status.value != "stale"
        journal_before = repository.journal_path.read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()

    _source, _repository, _coordinator, _query, restarted = _web_chain(root)
    restarted_thread = Thread(target=restarted.serve_forever, daemon=True)
    restarted_thread.start()
    try:
        connection = HTTPConnection(*restarted.server_address)
        connection.request("POST", "/api/commands/refresh-workspace", body=body, headers={"Content-Type": "application/json", "Content-Length": str(len(body))})
        replay = connection.getresponse()
        replay_payload = json.loads(replay.read())
        assert replay.status == 202
        assert replay_payload == payload
        assert repository.journal_path.read_text(encoding="utf-8") == journal_before
    finally:
        restarted.shutdown()
        restarted.server_close()


def test_refresh_command_trace_is_persisted_in_real_receipt_after_restart(tmp_path):
    root = _project(tmp_path)
    _source, repository, coordinator, _query = _chain(root)
    result = coordinator.refresh("p", {ProjectionSection.PROJECT}, trace_id="trace-command-1")

    assert result.receipt.trace_id == "trace-command-1"
    restarted = ProjectionRefreshCoordinator(RepositoryRefreshBuilder(root, repository), repository.journal_path)
    restored = restarted.retry(result.refresh_id)

    assert restored.receipt == result.receipt
    assert restored.trace_id == "trace-command-1"
