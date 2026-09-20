from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from creative_os.projection.provenance import Derivation, SourceRef


class ChapterStatus(StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class ChapterStage(StrEnum):
    PLANNING = "planning"
    ADMISSION = "admission"
    WRITING = "writing"
    REVIEW = "review"
    COMPILATION = "compilation"


class StageStatus(StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ChapterStageSnapshot:
    stage: ChapterStage
    status: StageStatus
    source_refs: tuple[SourceRef, ...]
    derivations: tuple[Derivation, ...] = ()


@dataclass(frozen=True, slots=True)
class ChapterSnapshot:
    chapter_id: str
    chapter_number: int
    title: str
    status: ChapterStatus
    attempts: int
    elapsed_seconds: float
    source_refs: tuple[SourceRef, ...]
    stages: tuple[ChapterStageSnapshot, ...] = ()
    derivations: tuple[Derivation, ...] = ()
    blocked_by: tuple[Derivation, ...] = ()
    checkpoint_state: str | None = None

    def __post_init__(self) -> None:
        if not self.chapter_id.strip() or self.chapter_number < 1:
            raise ValueError("chapter_identity_invalid")
        if not self.title.strip():
            raise ValueError("chapter_title_required")
        if not isinstance(self.status, ChapterStatus):
            raise TypeError("chapter_status_invalid")
        if self.attempts < 0 or self.elapsed_seconds < 0:
            raise ValueError("chapter_metrics_invalid")
