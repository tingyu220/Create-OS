from __future__ import annotations

import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from creative_os.workspace_dto import encode_workspace_envelope
from creative_os.workspace_query import WorkspaceQueryAdapter


WEB_ROOT = Path(__file__).with_name("web")


class WorkspaceWebAdapter:
    """把统一查询 DTO 编码为只读 Web JSON，不读取权威来源。"""

    def __init__(self, query: WorkspaceQueryAdapter, project_id: str) -> None:
        if not project_id.strip():
            raise ValueError("web_project_id_required")
        self._query = query
        self._project_id = project_id.strip()

    def read(self) -> dict[str, object]:
        return encode_workspace_envelope(self._query.get_workspace(self._project_id))

    def read_json(self) -> bytes:
        return json.dumps(self.read(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class WorkspaceRequestHandler(BaseHTTPRequestHandler):
    """单项目只读工作台 HTTP 边界；没有写入或命令路由。"""

    workspace_adapter: WorkspaceWebAdapter
    web_root: Path = WEB_ROOT

    def do_GET(self) -> None:  # noqa: N802
        route = urlsplit(self.path).path
        if route == "/api/workspace":
            self._send_json(200, self.workspace_adapter.read_json())
            return
        static_files = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/styles.css": ("styles.css", "text/css; charset=utf-8")}
        file_info = static_files.get(route)
        if file_info is None:
            self._send_text(404, "Not found")
            return
        filename, content_type = file_info
        try:
            content = (self.web_root / filename).read_bytes()
        except OSError:
            self._send_text(500, "Web asset unavailable")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send_json(self, status: int, content: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_text(self, status: int, content: str) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def create_server(
    adapter: WorkspaceWebAdapter,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    web_root: str | Path = WEB_ROOT,
) -> ThreadingHTTPServer:
    """创建绑定单个查询适配器的 HTTP 服务，不组装或读取底层来源。"""
    if not isinstance(adapter, WorkspaceWebAdapter):
        raise TypeError("workspace_web_adapter_required")
    asset_root = Path(web_root)

    class BoundWorkspaceRequestHandler(WorkspaceRequestHandler):
        workspace_adapter = adapter
        web_root = asset_root

    server = ThreadingHTTPServer((host, port), BoundWorkspaceRequestHandler)
    server.daemon_threads = True
    return server
