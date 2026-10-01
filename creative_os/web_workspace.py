from __future__ import annotations

import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import re
import difflib

from creative_os.web_command_dto import WebCommandValidationError, decode_web_command, encode_command_result
from creative_os.workspace_dto import encode_workspace_envelope
from creative_os.workspace_query import WorkspaceQueryAdapter
from creative_os.writer_draft_store import WriterDraftStore
from creative_os.writer_workspace_dto import WriterChapterEnvelope, WriterChapterDTO, WriterSourceDTO, WriterSourceRole, encode_writer_chapter
from creative_os.workspace_dto import Freshness
from creative_os.agent_intent import AgentIntentRequest, accept_agent_intent
from creative_os.agent_runtime import WriterAgentRuntime


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

    def read_chapter(self, chapter_number: int, *, source: str = "auto") -> bytes:
        draft = self.store.current(chapter_number)
        path = self.project_root / "production" / "final_chapters" / f"chapter_{chapter_number:03d}.md"
        if draft is not None and source == "draft":
            version, content = draft
            source = WriterSourceDTO(WriterSourceRole.WORKING_DRAFT, "当前工作稿", True, version.source_key, content_hash=version.content_hash)
            chapter = WriterChapterDTO(self.project_id, chapter_number, f"第{chapter_number}章", content, source, version, Freshness.FRESH, (version.source_key,))
            return json.dumps(encode_writer_chapter(WriterChapterEnvelope(chapter, Freshness.FRESH)), ensure_ascii=False).encode("utf-8")
        if draft is not None and source == "auto" and not path.exists():
            version, content = draft
            draft_source = WriterSourceDTO(WriterSourceRole.WORKING_DRAFT, "当前工作稿", True, version.source_key, content_hash=version.content_hash)
            chapter = WriterChapterDTO(self.project_id, chapter_number, f"第{chapter_number}章", content, draft_source, version, Freshness.FRESH, (version.source_key,))
            return json.dumps(encode_writer_chapter(WriterChapterEnvelope(chapter, Freshness.FRESH)), ensure_ascii=False).encode("utf-8")
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

    def read_diff(self, chapter_number: int, from_version: int | None, to_version: int | None) -> bytes:
        formal = self.project_root / "production" / "final_chapters" / f"chapter_{chapter_number:03d}.md"
        before = formal.read_text(encoding="utf-8") if formal.exists() else ""
        versions = self.store.versions(chapter_number)
        records = [json.loads(line) for line in self.store._path(chapter_number).read_text(encoding="utf-8").splitlines()] if self.store._path(chapter_number).exists() else []
        if from_version is not None:
            selected = next((item for item in records if item["version"] == from_version), None)
            before = "" if selected is None else selected["content"]
        if to_version is not None:
            selected = next((item for item in records if item["version"] == to_version), None)
            after = "" if selected is None else selected["content"]
        else:
            current = self.store.current(chapter_number)
            after = current[1] if current is not None else before
        diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile="原稿", tofile="新工作稿"))
        return json.dumps({"chapter_number": chapter_number, "diff": diff}, ensure_ascii=False).encode("utf-8")

    def read_context_summary(self) -> bytes:
        final_root = self.project_root / "production" / "final_chapters"
        final_count = len(tuple(final_root.glob("chapter_*.md"))) if final_root.exists() else 0
        draft_count = len(tuple(self.store.root.glob("chapter_*.jsonl"))) if self.store.root.exists() else 0
        draft_chapters = sorted(int(path.stem.split("_")[-1]) for path in self.store.root.glob("chapter_*.jsonl")) if self.store.root.exists() else []
        payload = {"project_id": self.project_id, "formal_chapter_count": final_count, "working_draft_count": draft_count, "working_draft_chapters": draft_chapters}
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class WorkspaceRequestHandler(BaseHTTPRequestHandler):
    """单项目工作台 HTTP 边界，只开放显式声明的工作区命令。"""

    workspace_adapter: WorkspaceWebAdapter
    command_adapter: object | None = None
    review_command_adapter: object | None = None
    chapter_command_adapter: object | None = None
    writer_command_adapter: object | None = None
    writer_adapter: WriterWebAdapter | None = None
    agent_runtime: WriterAgentRuntime | None = None
    web_root: Path = WEB_ROOT

    def do_GET(self) -> None:  # noqa: N802
        request_url = urlsplit(self.path)
        route = request_url.path
        if route == "/api/workspace":
            self._send_json(200, self.workspace_adapter.read_json())
            return
        match = re.fullmatch(r"/api/writer/chapters/(\d+)", route)
        if match and self.writer_adapter is not None:
            source = parse_qs(request_url.query).get("source", ["auto"])[0]
            self._send_json(200, self.writer_adapter.read_chapter(int(match.group(1)), source=source))
            return
        match = re.fullmatch(r"/api/writer/chapters/(\d+)/versions", route)
        if match and self.writer_adapter is not None:
            self._send_json(200, self.writer_adapter.read_versions(int(match.group(1))))
            return
        match = re.fullmatch(r"/api/writer/chapters/(\d+)/diff", route)
        if match and self.writer_adapter is not None:
            query = parse_qs(request_url.query)
            self._send_json(200, self.writer_adapter.read_diff(int(match.group(1)), *(int(query[name][0]) if query.get(name) else None for name in ("from", "to"))))
            return
        if route == "/api/writer/context":
            if self.writer_adapter is None:
                self._send_text(503, "Writer unavailable")
            else:
                self._send_json(200, self.writer_adapter.read_context_summary())
            return
        match = re.fullmatch(r"/api/agent/jobs/([a-z0-9-]+)", route)
        if match and self.agent_runtime is not None:
            job = self.agent_runtime.get(match.group(1))
            if job is None:
                self._send_json(404, json.dumps({"error": {"message": "任务不存在。"}}, ensure_ascii=False).encode("utf-8"))
            else:
                self._send_json(200, json.dumps({"job_id": job.job_id, "status": job.status, "message": job.message, "chapter_number": job.chapter_number, "draft_version": job.draft_version, "updated_at": job.updated_at, "mode": job.mode, "decision_id": job.decision_id, "target_words": job.target_words, "tolerance_words": job.tolerance_words, "min_words": job.min_words, "max_words": job.max_words, "actual_words": job.actual_words, "within_word_range": job.within_word_range}, ensure_ascii=False).encode("utf-8"))
            return
        match = re.fullmatch(r"/api/agent/decisions/([a-z0-9-]+)", route)
        if match and self.agent_runtime is not None:
            try:
                self._send_json(200, json.dumps(self.agent_runtime.get_decision(match.group(1)), ensure_ascii=False).encode("utf-8"))
            except FileNotFoundError:
                self._send_json(404, json.dumps({"error": {"message": "创作决策不存在。"}}, ensure_ascii=False).encode("utf-8"))
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
        if route in {"/api/commands/save-writer-draft", "/api/commands/restore-writer-version", "/api/commands/publish-writer-draft", "/api/commands/open-writer-chapter"}:
            self._handle_command(self.writer_command_adapter)
            return
        if route == "/api/agent/intents":
            self._handle_agent_intent()
            return
        if route == "/api/agent/decisions/act":
            self._handle_agent_decision_act()
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
            if self.agent_runtime is None:
                self._send_json(503, json.dumps({"error": {"code": "agent_runtime_unavailable", "message": "Agent Runtime 尚未启动。"}}, ensure_ascii=False).encode("utf-8"), close=True)
                return
            job = self.agent_runtime.submit(receipt.instruction, request.chapter_number, request.actor, target_words=int(raw.get("target_words", 4500)), tolerance_words=int(raw.get("tolerance_words", 300)))
            self._send_json(202, json.dumps({"intent_id": receipt.intent_id, "job_id": job.job_id, "status": job.status, "message": job.message, "instruction": receipt.instruction}, ensure_ascii=False).encode("utf-8"), close=True)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._send_json(422, '{"error":{"code":"agent_intent_invalid","message":"Agent 检查请求无效。"}}'.encode("utf-8"), close=True)

    def _handle_agent_decision_act(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            raw = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.agent_runtime is None:
                raise RuntimeError("agent_runtime_unavailable")
            job = self.agent_runtime.submit_from_decision(str(raw["decision_id"]), str(raw.get("actor", "作者")), str(raw.get("feedback", "")))
            self._send_json(202, json.dumps({"job_id": job.job_id, "status": job.status, "mode": job.mode}, ensure_ascii=False).encode("utf-8"), close=True)
        except ValueError as error:
            self._send_json(404, json.dumps({"error": {"code": str(error), "message": "创作决策不存在。"}}, ensure_ascii=False).encode("utf-8"), close=True)
        except (KeyError, TypeError, json.JSONDecodeError):
            self._send_json(422, '{"error":{"code":"decision_invalid","message":"创作决策请求无效。"}}'.encode("utf-8"), close=True)

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
    agent_runtime: WriterAgentRuntime | None = None,
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
    bound_agent_runtime = agent_runtime

    class BoundWorkspaceRequestHandler(WorkspaceRequestHandler):
        workspace_adapter = adapter
        command_adapter = bound_command_adapter
        review_command_adapter = bound_review_command_adapter
        chapter_command_adapter = bound_chapter_command_adapter
        writer_command_adapter = bound_writer_command_adapter
        writer_adapter = bound_writer_adapter
        agent_runtime = bound_agent_runtime
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
