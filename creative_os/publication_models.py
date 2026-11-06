"""自动发布领域的纯数据模型。"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, ClassVar


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class PublicationStatus(_ValueEnum):
    WRITING = "writing"
    CHECKING = "checking"
    READY_TO_FILL = "ready_to_fill"
    FILLING = "filling"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHING = "publishing"
    VERIFYING = "verifying"
    PUBLISHED = "published"
    FAILED = "failed"
    UNKNOWN = "unknown"
    PAUSED = "paused"
    writing = WRITING
    checking = CHECKING
    ready_to_fill = READY_TO_FILL
    filling = FILLING
    ready_to_publish = READY_TO_PUBLISH
    publishing = PUBLISHING
    verifying = VERIFYING
    published = PUBLISHED
    failed = FAILED
    unknown = UNKNOWN
    paused = PAUSED


class PauseMode(_ValueEnum):
    SAFE = "safe"
    IMMEDIATE = "immediate"
    safe = SAFE
    immediate = IMMEDIATE

class UnknownStatusError(RuntimeError):
    """平台结果未知时，禁止继续发布。"""


class _JsonMixin:
    def to_dict(self) -> dict[str, Any]:
        result = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            result[name] = value.value if isinstance(value, Enum) else value
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ChapterSnapshot(_JsonMixin):
    book_id: str
    chapter_number: int
    source_revision: str
    content: str
    content_sha256: str | None = None

    def __post_init__(self) -> None:
        digest = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if self.content_sha256 is None:
            object.__setattr__(self, "content_sha256", digest)
        elif self.content_sha256 != digest:
            raise ValueError("content_sha256 与正文不匹配")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChapterSnapshot":
        return cls(**data)

    @classmethod
    def from_json(cls, value: str) -> "ChapterSnapshot":
        return cls.from_dict(json.loads(value))


@dataclass(frozen=True)
class PublicationCheckpoint(_JsonMixin):
    book_id: str
    chapter_number: int
    source_revision: str
    current_step: str
    operation_id: str
    content_sha256: str
    pause_mode: PauseMode | None = None
    resume_prerequisite: str | None = None
    status: PublicationStatus = PublicationStatus.UNKNOWN
    reconciled: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.pause_mode, str):
            object.__setattr__(self, "pause_mode", PauseMode(self.pause_mode))
        if isinstance(self.status, str):
            object.__setattr__(self, "status", PublicationStatus(self.status))

    def require_reconciled(self) -> None:
        if self.status is PublicationStatus.UNKNOWN and not self.reconciled:
            raise UnknownStatusError("状态未知，必须先核对平台结果")

    def mark_reconciled(self, status: PublicationStatus) -> "PublicationCheckpoint":
        if status is PublicationStatus.UNKNOWN:
            raise ValueError("核对后不能仍为 unknown")
        return replace(self, status=status, reconciled=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PublicationCheckpoint":
        return cls(**data)

    @classmethod
    def from_json(cls, value: str) -> "PublicationCheckpoint":
        return cls.from_dict(json.loads(value))


@dataclass(frozen=True)
class PublicationLedgerEntry(_JsonMixin):
    platform_name: str
    platform_work_id: str
    platform_chapter_id: str
    status: PublicationStatus
    published_at: str | None = None
    evidence_ref: str | None = None
    operation_id: str | None = None
    needs_reconciliation: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            object.__setattr__(self, "status", PublicationStatus(self.status))
        if self.status is PublicationStatus.UNKNOWN and not self.needs_reconciliation:
            object.__setattr__(self, "needs_reconciliation", True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PublicationLedgerEntry":
        return cls(**data)

    @classmethod
    def from_json(cls, value: str) -> "PublicationLedgerEntry":
        return cls.from_dict(json.loads(value))


class IdempotencyRegistry:
    def __init__(self) -> None:
        self._operations: dict[str, str] = {}

    @staticmethod
    def key(platform_name: str, work_id: str, chapter_number: int, source_revision: str, content_sha256: str) -> str:
        return json.dumps([platform_name, work_id, chapter_number, source_revision, content_sha256], ensure_ascii=False, separators=(",", ":"))

    def submit(self, platform_name: str, work_id: str, chapter_number: int, source_revision: str, content_sha256: str) -> str:
        key = self.key(platform_name, work_id, chapter_number, source_revision, content_sha256)
        if key not in self._operations:
            self._operations[key] = str(uuid.uuid4())
        return self._operations[key]

    def to_dict(self) -> dict[str, str]:
        return dict(self._operations)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> "IdempotencyRegistry":
        instance = cls()
        instance._operations = dict(json.loads(value))
        return instance



