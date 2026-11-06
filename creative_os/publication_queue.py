"""自动发布的纯内存逐书逐章队列。"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from .publication_models import (
    ChapterSnapshot,
    IdempotencyRegistry,
    PauseMode,
    PublicationCheckpoint,
    PublicationStatus,
    UnknownStatusError,
)


@dataclass
class PublicationTask:
    snapshot: ChapterSnapshot
    platform_name: str
    work_id: str
    operation_id: str
    status: PublicationStatus = PublicationStatus.READY_TO_PUBLISH
    pause_reason: str | None = None
    pause_requested: PauseMode | None = None
    checkpoint: PublicationCheckpoint | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "platform_name": self.platform_name,
            "work_id": self.work_id,
            "operation_id": self.operation_id,
            "status": self.status.value,
            "pause_reason": self.pause_reason,
            "pause_requested": self.pause_requested.value if self.pause_requested else None,
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PublicationTask":
        checkpoint = data.get("checkpoint")
        return cls(
            snapshot=ChapterSnapshot.from_dict(data["snapshot"]),
            platform_name=data["platform_name"], work_id=data["work_id"],
            operation_id=data["operation_id"], status=PublicationStatus(data["status"]),
            pause_reason=data.get("pause_reason"),
            pause_requested=PauseMode(data["pause_requested"]) if data.get("pause_requested") else None,
            checkpoint=PublicationCheckpoint.from_dict(checkpoint) if checkpoint else None,
        )


class PublicationQueue:
    """按书隔离、按章节排序的内存队列。"""

    def __init__(self) -> None:
        self._tasks: dict[str, PublicationTask] = {}
        self._by_key: dict[str, str] = {}
        self._registry = IdempotencyRegistry()

    def enqueue(self, snapshot: ChapterSnapshot, platform_name: str, work_id: str) -> PublicationTask:
        key = self._registry.key(platform_name, work_id, snapshot.chapter_number, snapshot.source_revision, snapshot.content_sha256)
        if key in self._by_key:
            return self._tasks[self._by_key[key]]
        for existing in self._tasks.values():
            if (existing.snapshot.book_id == snapshot.book_id and existing.snapshot.chapter_number == snapshot.chapter_number
                    and existing.platform_name == platform_name and existing.work_id == work_id
                    and (existing.snapshot.source_revision != snapshot.source_revision
                         or existing.snapshot.content_sha256 != snapshot.content_sha256)):
                task = PublicationTask(snapshot, platform_name, work_id, str(uuid.uuid4()), PublicationStatus.PAUSED, "version_conflict")
                self._tasks[task.operation_id] = task
                self._by_key[key] = task.operation_id
                return task
        operation_id = self._registry.submit(platform_name, work_id, snapshot.chapter_number, snapshot.source_revision, snapshot.content_sha256)
        task = PublicationTask(snapshot, platform_name, work_id, operation_id)
        self._tasks[operation_id] = task
        self._by_key[key] = operation_id
        return task

    def get(self, operation_id: str) -> PublicationTask:
        return self._tasks[operation_id]

    def next_ready(self, book_id: str) -> PublicationTask | None:
        candidates = sorted((t for t in self._tasks.values() if t.snapshot.book_id == book_id),
                            key=lambda t: t.snapshot.chapter_number)
        for task in candidates:
            if task.status is PublicationStatus.PUBLISHED:
                continue
            return task if task.status is PublicationStatus.READY_TO_PUBLISH else None
        return None

    def start(self, operation_id: str) -> PublicationTask:
        task = self.get(operation_id)
        if task.status is PublicationStatus.UNKNOWN:
            task.checkpoint.require_reconciled()
        if task.status in {PublicationStatus.PUBLISHED, PublicationStatus.PAUSED}:
            raise ValueError("任务当前不可启动")
        task.status = PublicationStatus.PUBLISHING
        return task

    def complete(self, operation_id: str) -> PublicationTask:
        task = self.get(operation_id)
        if task.status is not PublicationStatus.PUBLISHING:
            raise ValueError("只有发布中的任务可以完成")
        task.status = PublicationStatus.PUBLISHED
        task.pause_requested = None
        return task

    def mark_unknown(self, operation_id: str, step: str = "publishing") -> PublicationTask:
        task = self.get(operation_id)
        task.status = PublicationStatus.UNKNOWN
        task.checkpoint = PublicationCheckpoint(task.snapshot.book_id, task.snapshot.chapter_number,
            task.snapshot.source_revision, step, task.operation_id, task.snapshot.content_sha256,
            status=PublicationStatus.UNKNOWN, resume_prerequisite="reconcile")
        return task

    def reconcile(self, operation_id: str, status: PublicationStatus) -> PublicationTask:
        task = self.get(operation_id)
        if task.status is not PublicationStatus.UNKNOWN:
            raise ValueError("仅未知状态需要核对")
        if isinstance(status, str):
            status = PublicationStatus(status)
        if status is PublicationStatus.UNKNOWN:
            raise ValueError("核对结果不能仍为 unknown")
        task.checkpoint = task.checkpoint.mark_reconciled(status)
        task.status = status
        return task

    def resume(self, operation_id: str) -> PublicationTask:
        task = self.get(operation_id)
        if task.status is PublicationStatus.UNKNOWN:
            raise UnknownStatusError("状态未知，必须先核对平台结果")
        if task.status is PublicationStatus.PUBLISHED:
            return task
        if task.status is not PublicationStatus.PAUSED and task.status is not PublicationStatus.FAILED:
            raise ValueError("任务当前不可恢复")
        task.status = PublicationStatus.READY_TO_PUBLISH
        task.pause_requested = None
        return task

    def pause(self, book_id: str, mode: PauseMode) -> None:
        if isinstance(mode, str):
            mode = PauseMode(mode)
        for task in self._tasks.values():
            if task.snapshot.book_id != book_id or task.status is not PublicationStatus.PUBLISHING:
                continue
            task.pause_requested = mode
            if mode is PauseMode.IMMEDIATE:
                self.checkpoint(task.operation_id, "interrupted")

    def checkpoint(self, operation_id: str, step: str) -> PublicationCheckpoint:
        task = self.get(operation_id)
        mode = task.pause_requested or PauseMode.SAFE
        task.checkpoint = PublicationCheckpoint(task.snapshot.book_id, task.snapshot.chapter_number,
            task.snapshot.source_revision, step, task.operation_id, task.snapshot.content_sha256,
            pause_mode=mode, resume_prerequisite="resume")
        if task.pause_requested:
            task.status = PublicationStatus.PAUSED
        return task.checkpoint

    def to_dict(self) -> dict[str, Any]:
        return {"tasks": [task.to_dict() for task in self._tasks.values()]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PublicationQueue":
        queue = cls()
        for raw in data.get("tasks", []):
            task = PublicationTask.from_dict(raw)
            queue._tasks[task.operation_id] = task
            key = queue._registry.key(task.platform_name, task.work_id, task.snapshot.chapter_number, task.snapshot.source_revision, task.snapshot.content_sha256)
            queue._by_key[key] = task.operation_id
        return queue

    @classmethod
    def from_json(cls, value: str) -> "PublicationQueue":
        return cls.from_dict(json.loads(value))


__all__ = ["PublicationQueue", "PublicationTask"]
