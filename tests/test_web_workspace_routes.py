from __future__ import annotations

from http.client import HTTPConnection
from threading import Thread

from creative_os.web_workspace import WorkspaceWebAdapter, create_server
from creative_os.workspace_query import WorkspaceQueryAdapter


class EmptyReader:
    def read_bundle(self, _project_id):
        return None

    def current_heads(self, _project_id):
        return ()


def _get(server, path: str):
    connection = HTTPConnection(*server.server_address)
    connection.request("GET", path)
    response = connection.getresponse()
    return response.status, response.getheader("Content-Type"), response.read().decode("utf-8")


def test_root_workspace_and_projection_inspector_have_separate_routes():
    server = create_server(WorkspaceWebAdapter(WorkspaceQueryAdapter(EmptyReader()), "book"), port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        root_status, _, root_html = _get(server, "/")
        inspector_status, _, inspector_html = _get(server, "/inspector")
        inspector_js_status, inspector_js_type, inspector_js = _get(server, "/inspector.js")

        assert root_status == 200
        assert "Creative OS · Workspace" in root_html
        assert inspector_status == 200
        assert "Projection Inspector" in inspector_html
        assert 'src="/inspector.js"' in inspector_html
        assert 'id="projection-json"' in inspector_html
        assert inspector_js_status == 200
        assert inspector_js_type.startswith("text/javascript")
        assert 'fetch("/api/workspace"' in inspector_js
        assert "JSON.stringify(payload, null, 2)" in inspector_js
        assert "来源引用" in inspector_html
        assert "Trace" in inspector_html
    finally:
        server.shutdown()
        server.server_close()


def test_inspector_route_keeps_existing_workspace_query_endpoint():
    server = create_server(WorkspaceWebAdapter(WorkspaceQueryAdapter(EmptyReader()), "book"), port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, content_type, payload = _get(server, "/api/workspace")

        assert status == 200
        assert content_type.startswith("application/json")
        assert '"project_id":"book"' in payload
        assert '"overall":"unavailable"' in payload
    finally:
        server.shutdown()
        server.server_close()
