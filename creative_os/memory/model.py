from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable


class MemoryKind(StrEnum):
    WORKING = "working"
    PROJECT_DECISION = "project_decision"
    USER_PREFERENCE = "user_preference"
    DOMAIN_METHOD = "domain_method"
    EXPERIENCE = "experience"


class MemoryScope(StrEnum):
    TASK = "task"
    PROJECT = "project"
    USER = "user"
    DOMAIN = "domain"
    GLOBAL = "global"


class MemoryStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class MemoryLifecycleError(ValueError):
    pass


class MemoryValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MemoryEvidence:
    source_type: str
    source_id: str
    note: str = ""

    def __post_init__(self) -> None:
        if not self.source_type.strip() or not self.source_id.strip():
            raise MemoryValidationError("memory evidence requires source_type and source_id")


@dataclass(frozen=True, slots=True)
class MemoryItem:
    id: str
    kind: MemoryKind
    scope: MemoryScope
    scope_id: str
    title: str
    content: str
    applicability: tuple[str, ...]
    exceptions: tuple[str, ...]
    tags: frozenset[str]
    evidence: tuple[MemoryEvidence, ...]
    status: MemoryStatus
    confidence: float
    version: int
    created_at: str
    updated_at: str
    approved_by: str | None = None

    def __post_init__(self) -> None:
        required = (self.id, self.scope_id, self.title, self.content)
        if any(not value.strip() for value in required):
            raise MemoryValidationError("memory requires id, scope_id, title and content")
        if not self.evidence:
            raise MemoryValidationError("memory requires at least one evidence record")
        if not 0.0 <= self.confidence <= 1.0:
            raise MemoryValidationError("memory confidence must be between 0 and 1")
        if self.version < 1:
            raise MemoryValidationError("memory version must be positive")

    @classmethod
    def new_candidate(
        cls,
        *,
        id: str,
        kind: MemoryKind,
        scope: MemoryScope,
        scope_id: str,
        title: str,
        content: str,
        evidence: Iterable[MemoryEvidence],
        applicability: Iterable[str] = (),
        exceptions: Iterable[str] = (),
        tags: Iterable[str] = (),
        confidence: float = 0.5,
    ) -> "MemoryItem":
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=id,
            kind=kind,
            scope=scope,
            scope_id=scope_id,
            title=title,
            content=content,
            applicability=tuple(applicability),
            exceptions=tuple(exceptions),
            tags=frozenset(tags),
            evidence=tuple(evidence),
            status=MemoryStatus.CANDIDATE,
            confidence=confidence,
            version=1,
            created_at=now,
            updated_at=now,
        )

    def activate(self, *, actor: str) -> "MemoryItem":
        normalized_actor = actor.strip()
        if self.status != MemoryStatus.CANDIDATE:
            raise MemoryLifecycleError(f"cannot activate memory in status {self.status}")
        if not normalized_actor or normalized_actor.casefold() == "system":
            raise MemoryLifecycleError("memory activation requires a human actor")
        return replace(
            self,
            status=MemoryStatus.ACTIVE,
            approved_by=normalized_actor,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def reject(self, *, actor: str) -> "MemoryItem":
        self._require_human_actor(actor)
        if self.status != MemoryStatus.CANDIDATE:
            raise MemoryLifecycleError(f"cannot reject memory in status {self.status}")
        return replace(self, status=MemoryStatus.REJECTED, updated_at=datetime.now(timezone.utc).isoformat())

    def archive(self, *, actor: str) -> "MemoryItem":
        self._require_human_actor(actor)
        if self.status not in {MemoryStatus.ACTIVE, MemoryStatus.REJECTED}:
            raise MemoryLifecycleError(f"cannot archive memory in status {self.status}")
        return replace(self, status=MemoryStatus.ARCHIVED, updated_at=datetime.now(timezone.utc).isoformat())

    @staticmethod
    def _require_human_actor(actor: str) -> str:
        normalized_actor = actor.strip()
        if not normalized_actor or normalized_actor.casefold() == "system":
            raise MemoryLifecycleError("memory transition requires a human actor")
        return normalized_actor
