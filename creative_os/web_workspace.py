from __future__ import annotations

import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import re
import difflib
from dataclasses import asdict

from creative_os.web_command_dto import WebCommandValidationError, decode_web_command, encode_command_result
from creative_os.workspace_dto import encode_workspace_envelope
from creative_os.workspace_query import WorkspaceQueryAdapter
from creative_os.writer_draft_store import WriterDraftStore
from creative_os.writer_workspace_dto import WriterChapterEnvelope, WriterChapterDTO, WriterSourceDTO, WriterSourceRole, encode_writer_chapter
from creative_os.workspace_dto import Freshness
from creative_os.agent_intent import AgentIntentRequest, accept_agent_intent
from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.author_home_query import AuthorHomeQuery
from creative_os.project_registry import select_project
from creative_os.story_web import handle_story_get, handle_story_post
from creative_os.bookshelf_web import handle_bookshelf_get, handle_bookshelf_post
from creative_os.bookshelf_issues_web import handle_issues_get, handle_issues_post, guard_data_request
from creative_os.publication_web import handle_publication_get, handle_publication_post
from creative_os.publication_browser_workbench import BrowserWorkbenchError, ReconnectionMismatch
from creative_os.workspace_command import CommandRejectedError, CommandResult, CommandStatus, CommandError


WEB_ROOT = Path(__file__).with_name("web")
MAX_COMMAND_BODY_BYTES = 16 * 1024
MAX_STORY_COMMAND_BODY_BYTES = 200 * 1024


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
        # auto 始终优先展示最新工作稿；正式稿仍通过 source=formal 明确查看。
        if draft is not None and source == "auto":
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
        summary = AuthorHomeQuery(self.project_root, self.project_id).read()
        chapters = sorted(summary["chapters"], key=lambda item: item["chapter_number"])
        payload = {"project_id": self.project_id, "title": summary["title"], "chapters": chapters,
                   "formal_chapter_count": summary["counts"]["formal"], "formal_chapters": [item["chapter_number"] for item in chapters if item["has_formal"]],
                   "working_draft_count": summary["counts"]["draft"], "working_draft_chapters": [item["chapter_number"] for item in chapters if item["has_draft"]],
                   "candidate_count": summary["counts"]["candidate"], "notices": summary["notices"]}
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
    project_registry = None
    routed_project_id = None
    migration_service = None
    migration_unavailable = False
    default_project_id = None
    default_project_root = None
    publication_orchestrator = None
    browser_workbench = None

    def do_GET(self) -> None:  # noqa: N802
        if handle_issues_get(self) or guard_data_request(self):
            return
        if handle_bookshelf_get(self):
            return
        if select_project(self) or handle_story_get(self):
            return
        request_url = urlsplit(self.path)
        route = request_url.path
        if route == "/api/publication":
            if self.publication_orchestrator is None:
                self._send_json(503, b'{"error":{"code":"publication_unavailable"}}')
            else:
                handle_publication_get(self, self.publication_orchestrator)
            return
        if route == "/api/publication/browser":
            if self.browser_workbench is None:
                self._send_json(503, b'{"error":{"code":"browser_workbench_unavailable"}}')
            else:
                self._send_json(200, json.dumps(self.browser_workbench.view(), ensure_ascii=False).encode("utf-8"))
            return
        if route == "/api/author-home":
            if self.writer_adapter is None:
                self._send_text(503, "作者稿件摘要暂不可用")
            else:
                from creative_os.author_home_query import AuthorHomeQuery
                query = AuthorHomeQuery(self.writer_adapter.project_root, self.writer_adapter.project_id)
                self._send_json(200, query.read_json())
            return
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
        match = re.fullmatch(r"/api/agent/conversations/([1-9]\d*)", route)
        if match and self.agent_runtime is not None:
            project_id = parse_qs(request_url.query).get("project_id", [None])[0]
            if project_id != self.agent_runtime.project_id:
                self._send_json(422, b'{"error":{"code":"project_scope_mismatch"}}')
                return
            session = self.agent_runtime.conversation(int(match.group(1)))
            self._send_json(200, json.dumps(session, ensure_ascii=False).encode("utf-8"))
            return
        match = re.fullmatch(r"/api/agent/jobs/([a-z0-9-]+)/context-sources", route)
        if match and self.agent_runtime is not None:
            try:
                query = parse_qs(request_url.query, keep_blank_values=True)
                required = {"project_id", "chapter_number", "session_id"}
                if not required <= query.keys() or query.keys() - required - {"source_id"} or any(len(values) != 1 for values in query.values()):
                    raise ValueError("context_query_invalid")
                result = self.agent_runtime.context_sources.read(
                    project_id=query["project_id"][0], chapter_number=int(query["chapter_number"][0]),
                    session_id=query["session_id"][0], job_id=match.group(1),
                    source_id=query.get("source_id", [None])[0])
                self._send_json(200, json.dumps(result, ensure_ascii=False).encode("utf-8"))
            except (ValueError, FileNotFoundError) as error:
                self._agent_error(error)
            return
        match = re.fullmatch(r"/api/agent/jobs/([a-z0-9-]+)", route)
        if match and self.agent_runtime is not None:
            job = self.agent_runtime.get(match.group(1))
            if self.routed_project_id and not self._matches_job_query(job, request_url.query):
                self._agent_error(ValueError("session_scope_mismatch"))
                return
            if job is None:
                self._send_json(404, json.dumps({"error": {"message": "任务不存在。"}}, ensure_ascii=False).encode("utf-8"))
            else:
                public_job = self.agent_runtime.job_view(job)
                public_job.pop("context_snapshot", None)
                self._send_json(200, json.dumps(public_job, ensure_ascii=False).encode("utf-8"))
            return
        match = re.fullmatch(r"/api/agent/proposals/([a-z0-9-]+)", route)
        if match and self.agent_runtime is not None:
            try:
                query = parse_qs(request_url.query)
                proposal = self.agent_runtime.proposals.view(match.group(1))
                if (query.get("project_id", [None])[0] != proposal["project_id"]
                        or query.get("chapter_number", [None])[0] != str(proposal["chapter_number"])
                        or query.get("session_id", [None])[0] != proposal["session_id"]):
                    raise ValueError("proposal_scope_mismatch")
                self._send_json(200, json.dumps(proposal, ensure_ascii=False).encode("utf-8"))
            except (ValueError, FileNotFoundError) as error:
                self._agent_error(error)
            return
        match = re.fullmatch(r"/api/agent/decisions/([a-z0-9-]+)", route)
        if match and self.agent_runtime is not None:
            try:
                decision = self.agent_runtime.get_decision(match.group(1))
                if self.routed_project_id:
                    query = parse_qs(request_url.query)
                    if query != {"project_id": [decision.get("project_id")], "chapter_number": [str(decision["target_chapter"])], "session_id": [decision.get("session_id")]}:
                        raise ValueError("session_scope_mismatch")
                self._send_json(200, json.dumps(decision, ensure_ascii=False).encode("utf-8"))
            except (FileNotFoundError, ValueError):
                self._send_json(404, json.dumps({"error": {"message": "创作决策不存在。"}}, ensure_ascii=False).encode("utf-8"))
            return
        static_files = {
            "/overview": ("author-home.html", "text/html; charset=utf-8"),
            "/author-home.js": ("author-home.js", "text/javascript; charset=utf-8"),
            "/author-home.css": ("author-home.css", "text/css; charset=utf-8"),
            "/story": ("story.html", "text/html; charset=utf-8"),
            "/story.js": ("story.js", "text/javascript; charset=utf-8"),
            "/story.css": ("story.css", "text/css; charset=utf-8"),
            "/project-scope.js": ("project-scope.js", "text/javascript; charset=utf-8"),
            "/workspace-navigation.js": ("workspace-navigation.js", "text/javascript; charset=utf-8"),
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/bookshelf-issues.js": ("bookshelf-issues.js", "text/javascript; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/inspector": ("inspector.html", "text/html; charset=utf-8"),
            "/inspector.js": ("inspector.js", "text/javascript; charset=utf-8"),
            "/writer": ("writer.html", "text/html; charset=utf-8"),
            "/writer.js": ("writer.js", "text/javascript; charset=utf-8"),
            "/writer-agent.js": ("writer-agent.js", "text/javascript; charset=utf-8"),
            "/publication-panel.js": ("publication-panel.js", "text/javascript; charset=utf-8"),
            "/combat-panel.js": ("combat-panel.js", "text/javascript; charset=utf-8"),
            "/writer-agent-progress.js": ("writer-agent-progress.js", "text/javascript; charset=utf-8"),
            "/writer-lessons.js": ("writer-lessons.js", "text/javascript; charset=utf-8"),
            "/writer-sources.js": ("writer-sources.js", "text/javascript; charset=utf-8"),
            "/writer.css": ("writer.css", "text/css; charset=utf-8"),
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
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # 页面跳转会取消旧查询；迟到响应不再向已断开的连接写入。
            return

    def do_POST(self) -> None:  # noqa: N802
        if handle_issues_post(self) or guard_data_request(self, writable=True):
            return
        if handle_bookshelf_post(self):
            return
        if select_project(self) or handle_story_post(self):
            return
        route = urlsplit(self.path).path
        if route == "/api/publication":
            if self.publication_orchestrator is None:
                self._send_json(503, b'{"error":{"code":"publication_unavailable"}}')
            else:
                handle_publication_post(self, self.publication_orchestrator)
            return
        if route == "/api/publication/browser":
            self._handle_browser_workbench()
            return
        if route in {"/api/commands/edit-story-candidate", "/api/commands/confirm-story-candidate", "/api/commands/adopt-combat-candidate"}:
            self._handle_command(self.agent_runtime.story_commands if self.agent_runtime else None)
            return
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
        if route in {"/api/commands/review-writer-proposal", "/api/commands/reconcile-writer-proposal"}:
            self._handle_command(self.agent_runtime.proposal_commands if self.agent_runtime else None)
            return
        if route == "/api/commands/manage-writer-lesson":
            self._handle_command(self.agent_runtime.lesson_commands if self.agent_runtime else None)
            return
        if route == "/api/agent/intents":
            self._handle_agent_intent()
            return
        if route == "/api/agent/decisions/act":
            self._handle_agent_decision_act()
            return
        match = re.fullmatch(r"/api/agent/jobs/([a-z0-9-]+)/retry", route)
        if match:
            self._handle_agent_retry(match.group(1))
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
        limit = MAX_STORY_COMMAND_BODY_BYTES if urlsplit(self.path).path in {"/api/commands/edit-story-candidate", "/api/commands/confirm-story-candidate"} else MAX_COMMAND_BODY_BYTES
        if length > limit:
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
        if self.routed_project_id:
            try:
                command_adapter.validate_request(request)
            except CommandRejectedError as error:
                result = CommandResult(CommandStatus.REJECTED, request.command_id, request.request_id,
                                       CommandError(error.code, error.message, error.retryable))
                self._send_json(_command_http_status(result), json.dumps(encode_command_result(result), ensure_ascii=False).encode("utf-8"), close=True)
                return
            except (ValueError, TypeError, KeyError, AttributeError):
                result = CommandResult(CommandStatus.REJECTED, request.command_id, request.request_id,
                                       CommandError("validation_failed", "命令参数无效。", False))
                self._send_json(422, json.dumps(encode_command_result(result), ensure_ascii=False).encode("utf-8"), close=True)
                return
            self._activate_project()
            command_adapter = self._route_command_adapter()
        result = command_adapter.execute(request)
        status = _command_http_status(result)
        self._send_json(status, json.dumps(encode_command_result(result), ensure_ascii=False, sort_keys=True).encode("utf-8"), close=True)

    def _activate_project(self):
        """仅在完整预检后装配可写对象；装配本身不恢复任何中断任务。"""
        if self.routed_project_id:
            entry = self.project_registry.get(self.routed_project_id, writable=True)
            for key, value in entry.items():
                setattr(self, key, value)
        return self.agent_runtime

    def _route_command_adapter(self):
        route = urlsplit(self.path).path
        if route in {"/api/commands/edit-story-candidate", "/api/commands/confirm-story-candidate", "/api/commands/adopt-combat-candidate"}:
            return self.agent_runtime.story_commands
        if route in {"/api/commands/review-writer-proposal", "/api/commands/reconcile-writer-proposal"}:
            return self.agent_runtime.proposal_commands
        if route == "/api/commands/manage-writer-lesson":
            return self.agent_runtime.lesson_commands
        if route == "/api/commands/refresh-workspace":
            return self.command_adapter
        if route == "/api/commands/accept-review-issue":
            return self.review_command_adapter or self.command_adapter
        if route == "/api/commands/start-chapter-run":
            return self.chapter_command_adapter
        return self.writer_command_adapter

    def _read_agent_request(self) -> dict:
        if self.agent_runtime is None:
            raise ValueError("agent_runtime_unavailable")
        length = int(self.headers.get("Content-Length", "-1"))
        if self.headers.get_content_type() != "application/json" or not 0 < length <= MAX_COMMAND_BODY_BYTES:
            raise ValueError("agent_request_invalid")
        raw = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(raw, dict) or raw.get("project_id") != self.agent_runtime.project_id:
            raise ValueError("project_scope_mismatch")
        if type(raw.get("chapter_number")) is not int or raw["chapter_number"] <= 0:
            raise ValueError("chapter_number_invalid")
        if self.routed_project_id and raw.get("session_id") != self.agent_runtime.conversations.read(raw["chapter_number"])["session_id"]:
            raise ValueError("session_scope_mismatch")
        return raw

    def _matches_job_query(self, job, query_text):
        query = parse_qs(query_text, keep_blank_values=True)
        if job is None:
            return False
        if job.scope == "story":
            return query == {"project_id": [job.project_id], "scope": ["story"], "session_id": [job.session_id]}
        return query == {"project_id": [job.project_id], "chapter_number": [str(job.chapter_number)], "session_id": [job.session_id]}

    def _agent_error(self, error: Exception) -> None:
        code = str(error) if isinstance(error, ValueError) else "agent_request_invalid"
        status = 503 if code == "agent_runtime_unavailable" else 422
        self._send_json(status, json.dumps({"error": {"code": code, "message": f"Agent 请求未受理：{code}"}}, ensure_ascii=False).encode("utf-8"), close=True)

    def _handle_agent_intent(self) -> None:
        try:
            raw = self._read_agent_request()
            request = AgentIntentRequest(raw["project_id"], raw["chapter_number"], raw["instruction"], raw.get("actor", "作者"), raw.get("requested_expert"))
            receipt = accept_agent_intent(request)
            if self.agent_runtime is None:
                self._send_json(503, json.dumps({"error": {"code": "agent_runtime_unavailable", "message": "Agent Runtime 尚未启动。"}}, ensure_ascii=False).encode("utf-8"), close=True)
                return
            require_confirmed_combat = raw.get("require_confirmed_combat", False)
            if type(require_confirmed_combat) is not bool:
                raise ValueError("combat_plan_scope_invalid")
            options = {"target_words": raw.get("target_words", 4500), "tolerance_words": raw.get("tolerance_words", 300), "session_id": raw.get("session_id"), "mode": raw.get("mode", "analyze"), "requested_expert": request.requested_expert, "require_confirmed_combat": require_confirmed_combat}
            self.agent_runtime.validate_submit(receipt.instruction, request.chapter_number, request.actor, **options)
            job = self._activate_project().submit(receipt.instruction, request.chapter_number, request.actor, **options)
            self._send_json(202, json.dumps({"intent_id": receipt.intent_id, **{key: value for key, value in asdict(job).items() if key != "context_snapshot"}}, ensure_ascii=False).encode("utf-8"), close=True)
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            self._agent_error(error)

    def _handle_agent_decision_act(self) -> None:
        try:
            raw = self._read_agent_request()
            decision = self.agent_runtime.get_decision(str(raw["decision_id"]))
            if decision["target_chapter"] != raw["chapter_number"] or decision.get("session_id") != raw.get("session_id"):
                raise ValueError("session_scope_mismatch")
            actor, feedback = raw.get("actor", "作者"), raw.get("feedback", "")
            if not isinstance(feedback, str):
                raise ValueError("feedback_invalid")
            require_confirmed_combat = raw.get("require_confirmed_combat", False)
            if type(require_confirmed_combat) is not bool:
                raise ValueError("combat_plan_scope_invalid")
            self.agent_runtime.validate_submit(decision.get("analysis") or decision.get("intent") or "执行已确认决策", raw["chapter_number"], actor,
                                               target_words=int(decision.get("target_words", 4500)), tolerance_words=int(decision.get("tolerance_words", 300)), session_id=raw.get("session_id"), mode="act", require_confirmed_combat=require_confirmed_combat)
            job = self._activate_project().submit_from_decision(str(raw["decision_id"]), actor, feedback, require_confirmed_combat=require_confirmed_combat)
            self._send_json(202, json.dumps({key: value for key, value in asdict(job).items() if key != "context_snapshot"}, ensure_ascii=False).encode("utf-8"), close=True)
        except (KeyError, TypeError, ValueError, FileNotFoundError) as error:
            self._agent_error(error)

    def _handle_agent_retry(self, job_id: str) -> None:
        try:
            raw = self._read_agent_request()
            self.agent_runtime.validate_retry(job_id, chapter_number=raw["chapter_number"], session_id=raw["session_id"])
            job = self._activate_project().retry(job_id, chapter_number=raw["chapter_number"], session_id=raw["session_id"])
            self._send_json(202, json.dumps({key: value for key, value in asdict(job).items() if key != "context_snapshot"}, ensure_ascii=False).encode("utf-8"), close=True)
        except (KeyError, TypeError, ValueError) as error:
            self._agent_error(error)

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send_json(self, status: int, content: bytes, *, close: bool = False) -> None:
        # 读到一半目录完成移动时，不能把旧根的空结果作为正常数据发送。
        if getattr(self, "command", None) == "GET" and status < 400 and guard_data_request(self):
            return
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if close:
            self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _send_text(self, status: int, content: str) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _handle_browser_workbench(self) -> None:
        if self.browser_workbench is None:
            self._send_json(503, b'{"error":{"code":"browser_workbench_unavailable"}}')
            return
        try:
            if self.headers.get_content_type() != "application/json":
                raise ValueError("unsupported_media_type")
            length = int(self.headers.get("Content-Length", "-1"))
            if not 0 < length <= MAX_COMMAND_BODY_BYTES:
                raise ValueError("browser_request_invalid")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("browser_request_invalid")
            action = body.get("action")
            if action in {"connect", "reconnect"}:
                payload = {key: body.get(key) for key in ("platform", "session_id", "page_id", "page_url", "work_id", "work_title", "chapter_number", "platform_work_title", "platform_chapter_number", "content_sha256", "login_state")}
                result = self.browser_workbench.handoff(reconnect=action == "reconnect", **payload)
            elif action == "interrupt":
                result = self.browser_workbench.mark_interrupted(str(body.get("reason") or "browser_session_interrupted"))
            elif action == "pause":
                result = self.browser_workbench.pause(str(body.get("mode") or "safe"), str(body.get("reason") or "user_pause"))
            else:
                raise ValueError("browser_action_invalid")
            self._send_json(200, json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except (ValueError, BrowserWorkbenchError, ReconnectionMismatch, json.JSONDecodeError) as error:
            self._send_json(409, json.dumps({"error": {"code": str(error)}}, ensure_ascii=False).encode("utf-8"))


def create_server(
    adapter: WorkspaceWebAdapter,
    *,
    command_adapter: object | None = None,
    review_command_adapter: object | None = None,
    chapter_command_adapter: object | None = None,
    writer_command_adapter: object | None = None,
    writer_adapter: WriterWebAdapter | None = None,
    agent_runtime: WriterAgentRuntime | None = None,
    publication_orchestrator: object | None = None,
    browser_workbench: object | None = None,
    project_registry=None,
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
    bound_publication_orchestrator = publication_orchestrator
    bound_browser_workbench = browser_workbench
    if project_registry is not None and agent_runtime is not None:
        project_registry.register(agent_runtime.project_id, {
            "workspace_adapter": adapter, "command_adapter": command_adapter,
            "review_command_adapter": review_command_adapter, "chapter_command_adapter": chapter_command_adapter,
            "writer_command_adapter": writer_command_adapter, "writer_adapter": writer_adapter, "agent_runtime": agent_runtime,
            "publication_orchestrator": publication_orchestrator,
        })

    class BoundWorkspaceRequestHandler(WorkspaceRequestHandler):
        workspace_adapter = adapter
        command_adapter = bound_command_adapter
        review_command_adapter = bound_review_command_adapter
        chapter_command_adapter = bound_chapter_command_adapter
        writer_command_adapter = bound_writer_command_adapter
        writer_adapter = bound_writer_adapter
        agent_runtime = bound_agent_runtime
        publication_orchestrator = bound_publication_orchestrator
        browser_workbench = bound_browser_workbench
        web_root = asset_root

    server = ThreadingHTTPServer((host, port), BoundWorkspaceRequestHandler)
    BoundWorkspaceRequestHandler.project_registry = project_registry
    BoundWorkspaceRequestHandler.default_project_id = getattr(writer_adapter, "project_id", None) or getattr(agent_runtime, "project_id", None)
    BoundWorkspaceRequestHandler.default_project_root = getattr(writer_adapter, "project_root", None) or getattr(agent_runtime, "root", None)
    if project_registry is not None:
        from creative_os.project_migration import ProjectMigrationService
        try:
            BoundWorkspaceRequestHandler.migration_service = ProjectMigrationService(
                project_registry.root, project_registry.root.parent / ".backup/project-directory-migrations", project_registry,
                default_project_id=BoundWorkspaceRequestHandler.default_project_id,
                default_root=BoundWorkspaceRequestHandler.default_project_root)
        except (OSError, ValueError, RuntimeError):
            BoundWorkspaceRequestHandler.migration_unavailable = True
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
