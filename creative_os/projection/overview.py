from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from creative_os.projection.provenance import Derivation, SourceRef


class ProjectRunStatus(StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OverviewBlocker:
    code: str
    message: str
    derivation: Derivation


@dataclass(frozen=True, slots=True)
class OverviewSnapshot:
    current_stage: str
    run_status: ProjectRunStatus
    chapter_count: int
    blocked_chapter_count: int
    source_refs: tuple[SourceRef, ...]
    blockers: tuple[OverviewBlocker, ...] = ()

    def __post_init__(self) -> None:
        if not self.current_stage.strip():
            raise ValueError("overview_current_stage_required")
        if not isinstance(self.run_status, ProjectRunStatus):
            raise TypeError("overview_run_status_invalid")
        if self.chapter_count < 0 or not 0 <= self.blocked_chapter_count <= self.chapter_count:
            raise ValueError("overview_chapter_counts_invalid")
