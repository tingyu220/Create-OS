"""自动发布编排与 HTTP 边界（仅使用 Fake/guard，不访问真实平台）。"""
from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import RLock
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .publication_models import ChapterSnapshot, PauseMode, PublicationStatus, UnknownStatusError, PublicationCheckpoint
from .publication_queue import PublicationQueue, PublicationTask


class PublicationOrchestrator:
    """把不可变快照、检查门槛、队列和平台适配器串起来。"""

    CHECKS = ("source_revision_continuous", "chapter_title", "word_count", "structure_ok",
              "characters_consistent", "settings_consistent", "combat_ok", "sensitive_ok",
              "format_ok", "platform_match", "unpublished", "hash_unchanged")

    def __init__(self, adapter: Any, queue: PublicationQueue | None = None) -> None:
        self.adapter = adapter
        self.queue = queue or PublicationQueue()
        self.global_paused = False
        self.book_paused: set[str] = set()
        self._lock = RLock()
        self._evidence: dict[str, dict[str, Any]] = {}
        self._control_results: dict[tuple[str, str], dict[str, Any]] = {}
        self._errors: dict[str, str] = {}

    def _checkpoint(self, task: PublicationTask, step: str, status: PublicationStatus) -> None:
        task.checkpoint = PublicationCheckpoint(task.snapshot.book_id, task.snapshot.chapter_number,
            task.snapshot.source_revision, step, task.operation_id, task.snapshot.content_sha256,
            resume_prerequisite="resume" if status in {PublicationStatus.FAILED, PublicationStatus.PAUSED} else None,
            status=status, reconciled=status is not PublicationStatus.UNKNOWN)

    def _checks(self, snapshot: ChapterSnapshot, target: Any, checks: dict[str, Any] | None) -> dict[str, Any]:
        values = {name: False for name in self.CHECKS}
        values.update(checks or {})
        if isinstance(target, dict):
            values["platform_match"] = values["platform_match"] and target.get("platform", getattr(self.adapter, "platform_name", None)) == getattr(self.adapter, "platform_name", target.get("platform"))
            values["chapter_title"] = values["chapter_title"] and bool(target.get("chapter_title"))
        values["hash_unchanged"] = values["hash_unchanged"] is True
        return values

    def submit(self, snapshot: ChapterSnapshot, target: Any = None, *, checks: dict[str, Any] | None = None, platform_name: str | None = None, work_id: str | None = None) -> PublicationTask:
        if not isinstance(snapshot, ChapterSnapshot):
            raise TypeError("只接受 ChapterSnapshot 正式稿")
        platform = platform_name or getattr(self.adapter, "platform_name", "unknown")
        work = work_id or getattr(target, "work_id", None) or (target or {}).get("work_id")
        if not work:
            raise ValueError("work_id_required")
        # 队列复用同快照时只读返回，避免终态被新的检查结果篡改。
        existing_ids = set(self.queue._tasks)
        task = self.queue.enqueue(snapshot, platform, work)
        if task.operation_id in existing_ids:
            return task
        # 队列在同书同章发现不同正文版本时已生成 version_conflict；该终态
        # 必须优先于自动检查结果，避免被检查失败覆盖。
        if task.status is PublicationStatus.PAUSED and task.pause_reason == "version_conflict":
            return task
        result = self._checks(snapshot, target, checks)
        task.checks = result  # type: ignore[attr-defined]
        failures = [k for k, ok in result.items() if not ok]
        if failures:
            task.status = PublicationStatus.FAILED
            task.pause_reason = "check_failed:" + ",".join(failures)
        elif self.global_paused or snapshot.book_id in self.book_paused:
            task.status = PublicationStatus.PAUSED
            task.pause_reason = "global_pause" if self.global_paused else "book_pause"
        else:
            try:
                self.adapter.verify_target(target, snapshot)
            except Exception as exc:
                task.status = PublicationStatus.FAILED
                task.pause_reason = str(exc)
        return task

    def run(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            task = self.queue.get(operation_id)
            if task.status is PublicationStatus.UNKNOWN:
                task.checkpoint.require_reconciled()
            if task.status is PublicationStatus.FAILED:
                return self.state(operation_id)
            if task.status is PublicationStatus.PAUSED:
                return self.state(operation_id)
            if task.status is PublicationStatus.PUBLISHED:
                return self.state(operation_id)
            try:
                self._checkpoint(task, "prepare_chapter", PublicationStatus.CHECKING)
                self.adapter.prepare_chapter(task.snapshot)
                self._checkpoint(task, "fill_chapter", PublicationStatus.FILLING)
                self.adapter.fill_chapter(task.snapshot, operation_id=operation_id)
                if task.pause_requested:
                    self.queue.checkpoint(operation_id, "fill_chapter")
                    return self.state(operation_id)
                task.status = PublicationStatus.PUBLISHING
                self._checkpoint(task, "publishing", PublicationStatus.PUBLISHING)
            except Exception as exc:
                task.status, task.pause_reason = PublicationStatus.FAILED, str(exc)
                self._errors[operation_id] = str(exc); self._checkpoint(task, "prepare_chapter" if task.checkpoint and task.checkpoint.current_step == "prepare_chapter" else "fill_chapter", PublicationStatus.FAILED)
                return self.state(operation_id)
            try:
                result = self.adapter.publish(operation_id)
            except Exception as exc:
                self.queue.mark_unknown(operation_id, "publishing")
                task.pause_reason = str(exc)
                self._errors[operation_id] = str(exc)
                return self.state(operation_id)
            status = PublicationStatus(result.get("status", "unknown"))
            if status is PublicationStatus.UNKNOWN:
                self.queue.mark_unknown(operation_id)
            elif status is PublicationStatus.PAUSED:
                task.status, task.pause_reason = status, result.get("pause_reason")
            elif status is PublicationStatus.PUBLISHED:
                self.queue.complete(operation_id)
                self._checkpoint(task, "published", PublicationStatus.PUBLISHED)
                self._evidence[operation_id] = self.adapter.capture_evidence(operation_id)
            else:
                task.status = PublicationStatus.FAILED
            return self.state(operation_id)

    def pause(self, *, operation_id: str | None = None, book_id: str | None = None, mode: PauseMode = PauseMode.SAFE, global_pause: bool = False, step: str | None = None) -> dict[str, Any]:
        if global_pause:
            self.global_paused = True
        if book_id:
            self.book_paused.add(book_id)
            self.queue.pause(book_id, mode)
        if global_pause:
            for task in self.queue._tasks.values():
                if task.status is PublicationStatus.READY_TO_PUBLISH:
                    task.status, task.pause_reason = PublicationStatus.PAUSED, "global_pause"
        elif book_id:
            for task in self.queue._tasks.values():
                if task.snapshot.book_id == book_id and task.status is PublicationStatus.READY_TO_PUBLISH:
                    task.status, task.pause_reason = PublicationStatus.PAUSED, "book_pause"
        if operation_id:
            task = self.queue.get(operation_id)
            if task.status is PublicationStatus.READY_TO_PUBLISH:
                task.status, task.pause_reason = PublicationStatus.PAUSED, "chapter_pause"
                if step: task.pause_reason = "step_pause:" + step; task.pause_step = step  # type: ignore[attr-defined]
            elif task.status is PublicationStatus.PUBLISHING:
                task.pause_requested = mode
                if mode is PauseMode.IMMEDIATE:
                    self.queue.checkpoint(operation_id, "interrupted")
        return self.state(operation_id) if operation_id else {"status": "paused", "scope": "global" if global_pause else "book"}

    def resume(self, operation_id: str) -> dict[str, Any]:
        task = self.queue.resume(operation_id)
        return self.run(operation_id)

    def reconcile(self, operation_id: str) -> dict[str, Any]:
        result = self.adapter.query_result(operation_id)
        status = PublicationStatus(result.get("status", "unknown"))
        if status is PublicationStatus.UNKNOWN:
            # 只有页面返回了明确章节标识与正文哈希，才算可核对的已发布证据。
            # 只有 status=unknown 的响应不能被推断为 published。
            task = self.queue.get(operation_id)
            explicit_evidence = bool(result.get("platform_chapter_id") and result.get("content_sha256") == task.snapshot.content_sha256)
            if "mismatch" in result:
                raise UnknownStatusError("核对结果仍为 unknown")
            if not explicit_evidence:
                return self.state(operation_id)
            status = PublicationStatus.PUBLISHED
        self.queue.reconcile(operation_id, status)
        if status is PublicationStatus.PUBLISHED:
            # 核对成功后重新采集证据，台账不能继续沿用丢响应时的 unknown 证据。
            evidence = self.adapter.capture_evidence(operation_id)
            # Fake/浏览器适配器在丢响应后仍可能保留旧的 unknown 响应，
            # 但本次核对已经以章节 ID 与正文哈希证明了发布结果。
            # 将台账中的证据状态同步为本次核对结论，避免出现“任务已发布、证据仍未知”。
            chapter = evidence.get("chapter") if isinstance(evidence, dict) else None
            if isinstance(chapter, dict) and chapter.get("status") == PublicationStatus.UNKNOWN.value:
                chapter = dict(chapter)
                chapter["status"] = PublicationStatus.PUBLISHED.value
                chapter["reconciled"] = True
                evidence = dict(evidence)
                evidence["chapter"] = chapter
                evidence["evidence_available"] = True
            self._evidence[operation_id] = evidence
        return self.state(operation_id)

    def clear_pause(self, *, scope: str = "global", book_id: str | None = None) -> dict[str, Any]:
        if scope == "global":
            self.global_paused = False
            for task in self.queue._tasks.values():
                if task.status is PublicationStatus.PAUSED and task.pause_reason == "global_pause":
                    task.status, task.pause_reason = PublicationStatus.READY_TO_PUBLISH, None
        elif scope == "book" and book_id:
            self.book_paused.discard(book_id)
            for task in self.queue._tasks.values():
                if task.snapshot.book_id == book_id and task.status is PublicationStatus.PAUSED and task.pause_reason == "book_pause":
                    task.status, task.pause_reason = PublicationStatus.READY_TO_PUBLISH, None
        return {"status": "running", "scope": scope, "book_id": book_id}

    def state(self, operation_id: str) -> dict[str, Any]:
        task = self.queue.get(operation_id)
        return {"book_id": task.snapshot.book_id, "chapter_number": task.snapshot.chapter_number,
                "source_revision": task.snapshot.source_revision, "content_sha256": task.snapshot.content_sha256,
                "operation_id": task.operation_id, "status": task.status.value, "current_step": task.checkpoint.current_step if task.checkpoint else getattr(task, "pause_step", task.status.value),
                "platform_name": task.platform_name, "work_id": task.work_id,
                "pause_reason": task.pause_reason, "error": self._errors.get(operation_id), "evidence": self._evidence.get(operation_id), "checks": getattr(task, "checks", {})}


def _publication_send(handler: Any, status: int, payload: Any) -> None:
    """在独立发布服务和 Writer 工作区服务之间复用 JSON 边界。"""
    if hasattr(handler, "_send_json"):
        body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler._send_json(status, body)
        return
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status); handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body))); handler.end_headers(); handler.wfile.write(body)


def handle_publication_get(handler: Any, orchestrator: PublicationOrchestrator) -> None:
    query = parse_qs(urlsplit(handler.path).query); op = query.get("operation_id", [None])[0]
    if op:
        try:
            _publication_send(handler, 200, orchestrator.state(op))
        except KeyError:
            _publication_send(handler, 404, {"error": {"code": "operation_not_found", "operation_id": op}})
    else:
        _publication_send(handler, 200, {"status": "ok"})


def handle_publication_post(handler: Any, orchestrator: PublicationOrchestrator) -> None:
    try:
        length = int(handler.headers.get("Content-Length", 0)); data = json.loads(handler.rfile.read(length) or b"{}")
        action, op = data.get("action", ""), data.get("operation_id")
        control_key = (str(op), action)
        if action != "submit" and op and control_key in orchestrator._control_results:
            _publication_send(handler, 200, orchestrator._control_results[control_key]); return
        if action == "submit":
            snapshot = ChapterSnapshot.from_dict(data["snapshot"])
            task = orchestrator.submit(snapshot, data.get("target"), checks=data.get("checks"), platform_name=data.get("platform_name"), work_id=data.get("work_id"))
            out = orchestrator.state(task.operation_id)
        elif action == "pause":
            out = orchestrator.pause(operation_id=op, book_id=data.get("book_id"), mode=PauseMode(data.get("mode", "safe")), global_pause=data.get("scope") == "global", step=data.get("step"))
        elif action == "resume": out = orchestrator.resume(op)
        elif action == "continue": out = orchestrator.clear_pause(scope=data.get("scope", "global"), book_id=data.get("book_id")) if not op else orchestrator.resume(op)
        elif action == "reconcile": out = orchestrator.reconcile(op)
        elif action == "run": out = orchestrator.run(op)
        else: raise ValueError("action_invalid")
        if action != "submit" and op: orchestrator._control_results[control_key] = out
        _publication_send(handler, 200, out)
    except Exception as exc:
        _publication_send(handler, 409, {"error": str(exc)})


class PublicationRequestHandler(BaseHTTPRequestHandler):
    orchestrator: PublicationOrchestrator
    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self) -> None:
        handle_publication_get(self, self.orchestrator)
    def do_POST(self) -> None:
        handle_publication_post(self, self.orchestrator)
    def log_message(self, *_args: Any) -> None: return


def create_publication_server(orchestrator: PublicationOrchestrator, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    class Bound(PublicationRequestHandler):
        pass
    Bound.orchestrator = orchestrator
    server = ThreadingHTTPServer((host, port), Bound); server.daemon_threads = True; return server


PublicationWebAdapter = PublicationOrchestrator
PublicationHTTPAdapter = PublicationOrchestrator

__all__ = ["PublicationOrchestrator", "PublicationWebAdapter", "PublicationHTTPAdapter", "PublicationRequestHandler", "create_publication_server", "handle_publication_get", "handle_publication_post"]
