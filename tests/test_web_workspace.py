from __future__ import annotations

import ast
import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

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
    assert "fetch(\"/api/" not in javascript.replace('fetch("/api/workspace"', "")
    assert "POST" not in javascript


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
