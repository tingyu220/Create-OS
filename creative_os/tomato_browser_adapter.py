"""番茄浏览器 Fake 适配器，仅用于 guard 测试，不连接网络。"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from .publication_models import ChapterSnapshot

@dataclass(frozen=True)
class TargetSpec:
    work_id: str
    title: str
    chapter_number: int
    chapter_title: str
    platform: str = "tomato"

@dataclass
class FakeTomatoPage:
    work_id: str
    title: str
    capabilities: set[str] = field(default_factory=lambda: {"fill_chapter", "publish", "query_result", "capture_evidence"})
    logged_in: bool = True
    captcha_required: bool = False
    drop_next_response: bool = False
    chapters: dict[int, dict[str, Any]] = field(default_factory=dict)

class TomatoBrowserAdapter:
    platform_name = "tomato"
    def __init__(self, page: FakeTomatoPage, *, auto_login: bool = False):
        if auto_login:
            raise ValueError("Fake 适配器禁止自动登录")
        self.page = page
        self._connected = False
        self._targets: dict[str, TargetSpec] = {}
        self._operations: dict[str, dict[str, Any]] = {}

    def connect(self, require_existing: bool = False) -> dict[str, Any]:
        if not self.page.work_id or require_existing and not self.page.logged_in:
            raise ConnectionError("必须使用用户已打开的番茄作品")
        self._connected = True
        return {"status": "connected", "platform": self.platform_name, "work_id": self.page.work_id}

    @staticmethod
    def _target(value: TargetSpec | dict[str, Any]) -> TargetSpec:
        if isinstance(value, TargetSpec): return value
        return TargetSpec(**value)

    def verify_target(self, target: TargetSpec | dict[str, Any], snapshot: ChapterSnapshot | None = None) -> dict[str, Any]:
        if not self._connected: raise ConnectionError("尚未连接已打开作品")
        target = self._target(target)
        if target.platform != self.platform_name or target.work_id != self.page.work_id or target.title != self.page.title:
            raise ValueError("目标作品标识或书名不匹配")
        if not {"fill_chapter", "publish", "query_result", "capture_evidence"}.issubset(self.page.capabilities):
            raise ValueError("目标平台缺少发布能力")
        if snapshot is not None and snapshot.chapter_number != target.chapter_number:
            raise ValueError("章节编号不匹配")
        existing = self.page.chapters.get(target.chapter_number)
        if existing and existing.get("title") != target.chapter_title:
            raise ValueError("章节编号或标题不匹配")
        self._targets[target.chapter_number] = target
        return {"ok": True, "platform": self.platform_name, "work_id": target.work_id, "chapter_number": target.chapter_number, "chapter_title": target.chapter_title}

    def prepare_chapter(self, snapshot: ChapterSnapshot, target: TargetSpec | dict[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(snapshot, ChapterSnapshot): raise TypeError("只接受 ChapterSnapshot 正式稿")
        if target is not None: self.verify_target(target, snapshot)
        return {"status": "ready", "chapter_number": snapshot.chapter_number, "content_sha256": snapshot.content_sha256}

    def fill_chapter(self, snapshot: ChapterSnapshot, target: TargetSpec | dict[str, Any] | None = None, operation_id: str | None = None) -> dict[str, Any]:
        if not isinstance(snapshot, ChapterSnapshot): raise TypeError("只接受不可变正式稿快照")
        target = self._target(target) if target is not None else self._targets.get(snapshot.chapter_number)
        if target is None or target.work_id != self.page.work_id or target.chapter_number != snapshot.chapter_number:
            raise ValueError("填充目标不匹配")
        digest = hashlib.sha256(snapshot.content.encode("utf-8")).hexdigest()
        if digest != snapshot.content_sha256: raise ValueError("正文哈希变化")
        if operation_id in self._operations and self._operations[operation_id]["snapshot"].content_sha256 != snapshot.content_sha256:
            raise ValueError("同一 operation_id 的正文哈希已变化")
        self.verify_target(target, snapshot)
        operation_id = operation_id or f"fill-{snapshot.chapter_number}-{snapshot.content_sha256[:12]}"
        self._operations[operation_id] = {"snapshot": snapshot, "target": target, "status": "filled"}
        self.page.chapters[snapshot.chapter_number] = {"title": target.chapter_title, "content": snapshot.content, "content_sha256": snapshot.content_sha256, "platform_chapter_id": f"tomato-{snapshot.chapter_number}"}
        return {"status": "filled", "operation_id": operation_id, "content_sha256": snapshot.content_sha256}

    def publish(self, operation_id: str) -> dict[str, Any]:
        op = self._operations.get(operation_id)
        if op is None: raise KeyError(operation_id)
        if op["status"] in {"published", "unknown"}: return dict(op["result"])
        if self.page.captcha_required: return self._pause(op, "captcha_required")
        if not self.page.logged_in: return self._pause(op, "login_expired")
        if self.page.drop_next_response:
            self.page.drop_next_response = False; op["status"] = "unknown"
            op["result"] = {"status": "unknown", "operation_id": operation_id, "pause_reason": "response_lost"}
            return dict(op["result"])
        op["status"] = "published"; op["result"] = {"status": "published", "operation_id": operation_id, "platform_chapter_id": self.page.chapters[op["snapshot"].chapter_number]["platform_chapter_id"], "content_sha256": op["snapshot"].content_sha256, "published_at": datetime.now(timezone.utc).isoformat()}
        return dict(op["result"])

    def _pause(self, op: dict[str, Any], reason: str) -> dict[str, Any]:
        result = {"status": "paused", "operation_id": next(k for k,v in self._operations.items() if v is op), "pause_reason": reason}
        op["result"] = result
        return dict(result)

    def query_result(self, operation_id: str) -> dict[str, Any]:
        op = self._operations.get(operation_id)
        if op is None: raise KeyError(operation_id)
        snapshot = op["snapshot"]
        result = dict(op.get("result", {})); chapter = self.page.chapters.get(snapshot.chapter_number)
        expected_id = f"tomato-{snapshot.chapter_number}"
        if not chapter:
            return {"status": "unknown", "operation_id": operation_id, "mismatch": "chapter_missing", "expected_platform_chapter_id": expected_id, "expected_content_sha256": snapshot.content_sha256}
        actual_id, actual_hash = chapter.get("platform_chapter_id"), chapter.get("content_sha256")
        if actual_id != expected_id:
            return {"status": "unknown", "operation_id": operation_id, "mismatch": "platform_chapter_id", "expected_platform_chapter_id": expected_id, "actual_platform_chapter_id": actual_id, "expected_content_sha256": snapshot.content_sha256, "actual_content_sha256": actual_hash}
        if actual_hash != snapshot.content_sha256:
            return {"status": "unknown", "operation_id": operation_id, "mismatch": "content_sha256", "expected_platform_chapter_id": expected_id, "actual_platform_chapter_id": actual_id, "expected_content_sha256": snapshot.content_sha256, "actual_content_sha256": actual_hash}
        result.update({"platform_chapter_id": actual_id, "content_sha256": actual_hash})
        return result

    def capture_evidence(self, operation_id: str) -> dict[str, Any]:
        result = self.query_result(operation_id)
        return {"platform": self.platform_name, "work_id": self.page.work_id, "operation_id": operation_id, "chapter": result, "evidence_available": result.get("status") != "unknown" and "mismatch" not in result}

__all__ = ["FakeTomatoPage", "TargetSpec", "TomatoBrowserAdapter"]

