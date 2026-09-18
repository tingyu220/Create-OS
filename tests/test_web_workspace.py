from __future__ import annotations

import ast
import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

from creative_os.projection.chapters import ChapterSnapshot, ChapterStatus
from creative_os.projection.model import ProjectSnapshot
from creative_os.projection.overview import OverviewSnapshot, ProjectRunStatus
from creative_os.projection.provenance import SourceHead, SourceRef
from creative_os.projection.quality import QualitySnapshot
from creative_os.projection.trace import TraceSnapshot
from creative_os.workspace_dto import (
    Freshness,
    OperationsSnapshot,
    ProjectionEnvelope,
    ProjectionSection,
    SectionEnvelope,
)
from creative_os.workspace_query import WorkspaceQueryAdapter
from creative_os.workspace_command import CommandError, CommandResult, CommandStatus


HASH = "a" * 64


def _snapshot() -> ProjectSnapshot:
    source_ref = SourceRef("project", "p", "project.json", HASH)
    return ProjectSnapshot.create(
        project_id="p",
        built_at="2026-09-08T00:00:00+00:00",
        source_heads=(SourceHead("project", "p", content_hash=HASH),),
        overview=OverviewSnapshot("complete", ProjectRunStatus.PASSED, 1, 0, (source_ref,)),
        chapters=(ChapterSnapshot("chapter-001", 1, "开端", ChapterStatus.PASSED, 1, 1.5, (source_ref,)),),
        quality=QualitySnapshot((), (), (source_ref,)),
        trace=TraceSnapshot((), (source_ref,)),
    )


class Reader:
    def read_bundle(self, project_id: str):
        snapshot = _snapshot()
        return type("Bundle", (), {
            "project": snapshot,
            "operations": OperationsSnapshot.from_project(snapshot),
            "source_heads": snapshot.source_heads,
            "freshness": {ProjectionSection.PROJECT: Freshness.FRESH, ProjectionSection.OPERATIONS: Freshness.PARTIAL},
            "diagnostics": (),
            "refresh_id": "refresh-1",
        })()

    def current_heads(self, project_id: str):
        return _snapshot().source_heads


def test_web_adapter_exposes_only_query_dto_sections_and_provenance():
    from creative_os.web_workspace import WorkspaceWebAdapter

    payload = WorkspaceWebAdapter(WorkspaceQueryAdapter(Reader()), "p").read()

    assert set(payload) == {"project_id", "overall", "sections", "snapshot", "operations", "source_heads", "refresh_id"}
    assert payload["overall"] == "partial"
    assert payload["sections"]["operations"]["status"] == "partial"
    assert payload["snapshot"]["overview"]["current_stage"] == "complete"
    assert payload["snapshot"]["chapters"][0]["source_refs"][0]["locator"] == "project.json"
    assert payload["operations"]["usage"] is None


def test_web_adapter_does_not_import_authority_or_filesystem_layers():
    tree = ast.parse(Path("creative_os/web_workspace.py").read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported |= {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    forbidden = ("creative_os.projection", "creative_os.domains", "creative_os.runtime", "filesystem_source", "repository")
    assert not any(name.startswith(forbidden) or name in forbidden for name in imported)


def test_web_adapter_preserves_unavailable_and_partial_states_without_inventing_data():
    from creative_os.web_workspace import WorkspaceWebAdapter

    class MissingReader:
        def read_bundle(self, _project_id):
            return None

        def current_heads(self, _project_id):
            return ()

    payload = WorkspaceWebAdapter(WorkspaceQueryAdapter(MissingReader()), "p").read()

    assert payload["overall"] == "unavailable"
    assert payload["snapshot"] is None
    assert payload["operations"] is None
    assert payload["sections"]["project"]["status"] == "unavailable"
    assert payload["sections"]["operations"]["status"] == "unavailable"


def test_frontend_reads_only_workspace_api_and_has_all_read_only_views():
    html = Path("creative_os/web/index.html").read_text(encoding="utf-8")
    javascript = Path("creative_os/web/app.js").read_text(encoding="utf-8")

    assert all(anchor in html for anchor in ("#overview", "#chapters", "#quality", "#runtime"))
    assert 'fetch("/api/workspace"' in javascript
    assert 'fetch("/api/commands/refresh-workspace"' in javascript
    assert javascript.count('fetch("/api/') == 2
    assert "/api/commands/" in javascript


def test_frontend_exposes_read_only_chapter_matrix_filter():
    html = Path("creative_os/web/index.html").read_text(encoding="utf-8")
    javascript = Path("creative_os/web/app.js").read_text(encoding="utf-8")
    assert 'id="chapter-filter"' in html
    assert 'id="chapter-filter-count"' in html
    assert 'chapterRows.filter' in javascript
    assert 'addEventListener("input", renderChapterMatrix)' in javascript


def test_frontend_exposes_runtime_diagnostics_and_recovery_read_model():
    html = Path("creative_os/web/index.html").read_text(encoding="utf-8")
    javascript = Path("creative_os/web/app.js").read_text(encoding="utf-8")
    assert all(marker in html for marker in ("runtime-tasks", "runtime-errors", "runtime-recovery", "runtime-retries"))
    assert all(marker in javascript for marker in ("operations.tasks", "operations.errors", "operations.recovery", "operations.retries"))
    assert "retryable" in javascript


def _command_request() -> dict[str, object]:
    return {
        "command_id": "refresh_workspace_projection",
        "request_id": "request-1",
        "actor": "local-user",
        "target": "p",
        "payload": {"sections": ["project", "operations"]},
        "expected_version": None,
        "idempotency_key": "refresh-1",
    }


class CommandStub:
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.result


def _command_server(command_stub: CommandStub):
    from creative_os.web_workspace import WorkspaceWebAdapter, create_server

    return create_server(
        WorkspaceWebAdapter(WorkspaceQueryAdapter(Reader()), "p"),
        command_adapter=command_stub,
        port=0,
    )


def _post(server, body: object, *, content_type: str = "application/json"):
    connection = HTTPConnection(*server.server_address)
    encoded = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    connection.request(
        "POST",
        "/api/commands/refresh-workspace",
        body=encoded,
        headers={"Content-Type": content_type, "Content-Length": str(len(encoded))},
    )
    return connection.getresponse()


def test_refresh_command_http_returns_202_and_stable_result():
    command = CommandStub(CommandResult(CommandStatus.ACCEPTED, "refresh_workspace_projection", "request-1", trace_id="trace-1", projection_refresh_id="refresh-1"))
    server = _command_server(command)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = _post(server, _command_request())
        assert response.status == 202
        assert response.getheader("Connection") == "close"
        assert json.loads(response.read())["projection_refresh_id"] == "refresh-1"
        assert command.requests[0].target == "p"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    ("body", "content_type", "status"),
    [
        (b"{bad", "application/json", 400),
        (b"{}", "text/plain", 415),
        (b"x" * (16 * 1024 + 1), "application/json", 413),
    ],
)
def test_refresh_command_http_rejects_invalid_transport(body, content_type, status):
    command = CommandStub(CommandResult(CommandStatus.ACCEPTED, "refresh_workspace_projection", "request-1"))
    server = _command_server(command)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert _post(server, body, content_type=content_type).status == status
        assert command.requests == []
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    ("result", "status"),
    [
        (CommandResult(CommandStatus.REJECTED, "refresh_workspace_projection", "request-1", CommandError("validation_failed", "bad", False)), 422),
        (CommandResult(CommandStatus.REJECTED, "refresh_workspace_projection", "request-1", CommandError("idempotency_conflict", "conflict", False)), 409),
        (CommandResult(CommandStatus.FAILED, "refresh_workspace_projection", "request-1", CommandError("command_outcome_unknown", "unknown", False)), 503),
    ],
)
def test_refresh_command_http_maps_command_statuses(result, status):
    server = _command_server(CommandStub(result))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert _post(server, _command_request()).status == status
    finally:
        server.shutdown()
        server.server_close()


def test_arbitrary_post_route_is_not_a_generic_command_dispatcher():
    command = CommandStub(CommandResult(CommandStatus.ACCEPTED, "refresh_workspace_projection", "request-1"))
    server = _command_server(command)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection(*server.server_address)
        connection.request("POST", "/api/commands/delete-project", body=b"{}", headers={"Content-Type": "application/json"})
        assert connection.getresponse().status == 404
        assert command.requests == []
    finally:
        server.shutdown()
        server.server_close()


def test_frontend_exposes_only_refresh_workspace_command():
    html = Path("creative_os/web/index.html").read_text(encoding="utf-8")
    javascript = Path("creative_os/web/app.js").read_text(encoding="utf-8")

    assert 'data-command="refresh-workspace"' in html
    assert 'fetch("/api/commands/refresh-workspace"' in javascript
    assert 'loadWorkspace()' in javascript
    assert 'aria-live="polite"' in html
    assert "editor" not in html.lower()
    assert "approval" not in html.lower()
    assert "portfolio" not in html.lower()


def test_read_only_http_workspace_serves_json_and_ui_without_write_routes():
    from creative_os.web_workspace import WorkspaceWebAdapter, create_server

    server = create_server(WorkspaceWebAdapter(WorkspaceQueryAdapter(Reader()), "p"), port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection(*server.server_address)
        connection.request("GET", "/api/workspace")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["project_id"] == "p"

        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        assert b"Chapter Matrix" in response.read()

        connection.request("POST", "/api/workspace")
        assert connection.getresponse().status == 405
    finally:
        server.shutdown()
        server.server_close()
