from __future__ import annotations

import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import re

from creative_os.web_command_dto import WebCommandValidationError, decode_web_command, encode_command_result
from creative_os.workspace_dto import encode_workspace_envelope
from creative_os.workspace_query import WorkspaceQueryAdapter
from creative_os.writer_draft_store import WriterDraftStore
from creative_os.writer_workspace_dto import WriterChapterEnvelope, WriterChapterDTO, WriterSourceDTO, WriterSourceRole, encode_writer_chapter
from creative_os.workspace_dto import Freshness
from creative_os.agent_intent import AgentIntentRequest, accept_agent_intent


WEB_ROOT = Path(__file__).with_name("web")
MAX_COMMAND_BODY_BYTES = 16 * 1024


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


class WriterWebAdapter:
    """Writer 只读查询适配器；工作稿读取来自独立版本存储。"""

    def __init__(self, project_root: str | Path, project_id: str) -> None:
        self.project_root = Path(project_root)
        self.project_id = project_id
        self.store = WriterDraftStore(project_root)

    def read_chapter(self, chapter_number: int) -> bytes:
        draft = self.store.current(chapter_number)
        if draft is not None:
            version, content = draft
            source = WriterSourceDTO(WriterSourceRole.WORKING_DRAFT, "当前工作稿", True, version.source_key, content_hash=version.content_hash)
            chapter = WriterChapterDTO(self.project_id, chapter_number, f"第{chapter_number}章", content, source, version, Freshness.FRESH, (version.source_key,))
            return json.dumps(encode_writer_chapter(WriterChapterEnvelope(chapter, Freshness.FRESH)), ensure_ascii=False).encode("utf-8")
        path = self.project_root / "production" / "final_chapters" / f"chapter_{chapter_number:03d}.md"
        if not path.exists():
            return json.dumps(encode_writer_chapter(WriterChapterEnvelope(None, Freshness.UNAVAILABLE, ("章节内容暂不可用",))), ensure_ascii=False).encode("utf-8")
        content = path.read_text(encoding="utf-8")
        source = WriterSourceDTO(WriterSourceRole.CANONICAL, "正式章节（只读）", False, f"canonical:chapter-{chapter_number:03d}", str(path.relative_to(self.project_root)))
        chapter = WriterChapterDTO(self.project_id, chapter_number, f"第{chapter_number}章", content, source, None, Freshness.FRESH, (source.source_key,))
        return json.dumps(encode_writer_chapter(WriterChapterEnvelope(chapter, Freshness.FRESH)), ensure_ascii=False).encode("utf-8")

    def read_versions(self, chapter_number: int) -> bytes:
        versions = self.store.versions(chapter_number)
        payload = {"chapter_number": chapter_number, "versions": [
            {"version": item.version, "created_at": item.created_at, "actor": item.actor, "parent_version": item.parent_version}
            for item in reversed(versions)
        ]}
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read_context_summary(self) -> bytes:
        final_root = self.project_root / "production" / "final_chapters"
        final_count = len(tuple(final_root.glob("chapter_*.md"))) if final_root.exists() else 0
        draft_count = len(tuple(self.store.root.glob("chapter_*.jsonl"))) if self.store.root.exists() else 0
        payload = {"project_id": self.project_id, "formal_chapter_count": final_count, "working_draft_count": draft_count}
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class WorkspaceRequestHandler(BaseHTTPRequestHandler):
    """单项目工作台 HTTP 边界，只开放显式声明的工作区命令。"""

    workspace_adapter: WorkspaceWebAdapter
    command_adapter: object | None = None
    review_command_adapter: object | None = None
    chapter_command_adapter: object | None = None
    writer_command_adapter: object | None = None
    writer_adapter: WriterWebAdapter | None = None
    web_root: Path = WEB_ROOT

    def do_GET(self) -> None:  # noqa: N802
        route = urlsplit(self.path).path
        if route == "/api/workspace":
            self._send_json(200, self.workspace_adapter.read_json())
            return
        match = re.fullmatch(r"/api/writer/chapters/(\d+)", route)
        if match and self.writer_adapter is not None:
            self._send_json(200, self.writer_adapter.read_chapter(int(match.group(1))))
            return
        match = re.fullmatch(r"/api/writer/chapters/(\d+)/versions", route)
        if match and self.writer_adapter is not None:
            self._send_json(200, self.writer_adapter.read_versions(int(match.group(1))))
            return
        if route == "/api/writer/context":
            if self.writer_adapter is None:
                self._send_text(503, "Writer unavailable")
            else:
                self._send_json(200, self.writer_adapter.read_context_summary())
            return
        static_files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/inspector": ("inspector.html", "text/html; charset=utf-8"),
            "/inspector.js": ("inspector.js", "text/javascript; charset=utf-8"),
            "/writer": ("writer.html", "text/html; charset=utf-8"),
            "/writer.js": ("writer.js", "text/javascript; charset=utf-8"),
        }
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
        route = urlsplit(self.path).path
        if route == "/api/commands/refresh-workspace":
            self._handle_command(self.command_adapter)
            return
        if route == "/api/commands/accept-review-issue":
            self._handle_command(self.review_command_adapter or self.command_adapter)
            return
        if route == "/api/commands/start-chapter-run":
            self._handle_command(self.chapter_command_adapter)
            return
        if route in {"/api/commands/save-writer-draft", "/api/commands/restore-writer-version", "/api/commands/open-writer-chapter"}:
            self._handle_command(self.writer_command_adapter)
            return
        if route == "/api/agent/intents":
            self._handle_agent_intent()
            return
        if route == "/api/workspace":
            self.send_response(405)
            self.send_header("Allow", "GET")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send_text(404, "Not found")

    def _handle_command(self, command_adapter: object | None) -> None:
        self.close_connection = True
        if command_adapter is None:
            self._send_json(503, json.dumps({"error": {"code": "command_unavailable", "message": "命令边界不可用。"}}).encode("utf-8"), close=True)
            return
        if self.headers.get_content_type() != "application/json":
            self._send_json(415, '{"error":{"code":"unsupported_media_type","message":"只接受 application/json。"}}'.encode("utf-8"), close=True)
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0:
            self._send_json(400, '{"error":{"code":"invalid_content_length","message":"请求体长度无效。"}}'.encode("utf-8"), close=True)
            return
        if length > MAX_COMMAND_BODY_BYTES:
            self._send_json(413, '{"error":{"code":"payload_too_large","message":"命令请求体超过大小限制。"}}'.encode("utf-8"), close=True)
            return
        try:
            raw = json.loads(self.rfile.read(length).decode("utf-8"))
            request = decode_web_command(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, '{"error":{"code":"invalid_json","message":"请求体不是有效 JSON。"}}'.encode("utf-8"), close=True)
            return
        except WebCommandValidationError as error:
            body = json.dumps({"error": {"code": error.code, "message": error.message}}, ensure_ascii=False).encode("utf-8")
            self._send_json(400, body, close=True)
            return
        result = command_adapter.execute(request)
        status = _command_http_status(result)
        self._send_json(status, json.dumps(encode_command_result(result), ensure_ascii=False, sort_keys=True).encode("utf-8"), close=True)

    def _handle_agent_intent(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            raw = json.loads(self.rfile.read(length).decode("utf-8"))
            request = AgentIntentRequest(raw["project_id"], int(raw["chapter_number"]), raw["instruction"], raw.get("actor", "作者"))
            receipt = accept_agent_intent(request)
            self._send_json(202, json.dumps({"intent_id": receipt.intent_id, "status": receipt.status, "message": receipt.message, "instruction": receipt.instruction}, ensure_ascii=False).encode("utf-8"), close=True)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._send_json(422, '{"error":{"code":"agent_intent_invalid","message":"Agent 检查请求无效。"}}'.encode("utf-8"), close=True)

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send_json(self, status: int, content: bytes, *, close: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if close:
            self.send_header("Connection", "close")
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
    command_adapter: object | None = None,
    review_command_adapter: object | None = None,
    chapter_command_adapter: object | None = None,
    writer_command_adapter: object | None = None,
    writer_adapter: WriterWebAdapter | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    web_root: str | Path = WEB_ROOT,
) -> ThreadingHTTPServer:
    """创建绑定单个查询适配器的 HTTP 服务，不组装或读取底层来源。"""
    if not isinstance(adapter, WorkspaceWebAdapter):
        raise TypeError("workspace_web_adapter_required")
    asset_root = Path(web_root)
    bound_command_adapter = command_adapter
    bound_review_command_adapter = review_command_adapter
    bound_chapter_command_adapter = chapter_command_adapter
    bound_writer_command_adapter = writer_command_adapter
    bound_writer_adapter = writer_adapter

    class BoundWorkspaceRequestHandler(WorkspaceRequestHandler):
        workspace_adapter = adapter
        command_adapter = bound_command_adapter
        review_command_adapter = bound_review_command_adapter
        chapter_command_adapter = bound_chapter_command_adapter
        writer_command_adapter = bound_writer_command_adapter
        writer_adapter = bound_writer_adapter
        web_root = asset_root

    server = ThreadingHTTPServer((host, port), BoundWorkspaceRequestHandler)
    server.daemon_threads = True
    return server


def _command_http_status(result: object) -> int:
    status = getattr(getattr(result, "status", None), "value", None)
    if status == "accepted":
        return 202
    if status == "rejected":
        code = getattr(getattr(result, "error", None), "code", None)
        return 409 if code in {
            "idempotency_conflict",
            "version_conflict",
            "reviewer_disposition_conflict",
            "disposition_conflict",
        } else 422
    return 503
