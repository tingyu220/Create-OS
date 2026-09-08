from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping
from creative_os.projection.model import ProjectSnapshot, ProjectionDiagnostic, DiagnosticSeverity
from creative_os.projection.provenance import SourceHead, SourceRef

class ProjectionSection(StrEnum):
    PROJECT = "project"
    OPERATIONS = "operations"

class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"

@dataclass(frozen=True, slots=True)
class UsageDTO:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

@dataclass(frozen=True, slots=True)
class TaskDTO:
    task_id: str
    status: str
    attempts: int | None
    elapsed_seconds: float | None
    source_refs: tuple[SourceRef, ...]

@dataclass(frozen=True, slots=True)
class ExecutionDTO:
    execution_id: str
    identity_kind: str
    event_type: str
    occurred_at: str
    source_refs: tuple[SourceRef, ...]

@dataclass(frozen=True, slots=True)
class ErrorDTO:
    code: str
    message: str
    retryable: bool | None
    source_refs: tuple[SourceRef, ...]

@dataclass(frozen=True, slots=True)
class RecoveryDTO:
    state: str | None
    source_refs: tuple[SourceRef, ...]

@dataclass(frozen=True, slots=True)
class RetryDTO:
    attempts: int | None
    source_refs: tuple[SourceRef, ...]

@dataclass(frozen=True, slots=True)
class OperationsSnapshot:
    project_id: str
    task_count: int | None
    execution_count: int | None
    failed_count: int | None
    attempts: int | None
    usage: UsageDTO | None
    source_refs: tuple[SourceRef, ...]
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()
    tasks: tuple[TaskDTO, ...] = ()
    executions: tuple[ExecutionDTO, ...] = ()
    errors: tuple[ErrorDTO, ...] = ()
    recovery: RecoveryDTO | None = None
    retries: tuple[RetryDTO, ...] = ()

    @classmethod
    def from_project(cls, snapshot: ProjectSnapshot) -> "OperationsSnapshot":
        events = snapshot.trace.entries
        errors = tuple(ErrorDTO(item.event_type, item.summary, None, item.source_refs) for item in events if item.event_type in {"TaskFailed", "ReviewFailed"})
        failed = max(sum(1 for item in snapshot.chapters if item.status.value in {"fail", "blocked"}), len(errors))
        attempts = sum(item.attempts for item in snapshot.chapters)
        tasks = tuple(TaskDTO(item.chapter_id, item.status.value, item.attempts, item.elapsed_seconds, item.source_refs) for item in snapshot.chapters)
        executions = tuple(ExecutionDTO(item.execution_id or item.event_id, "execution_id" if item.execution_id else "event_id", item.event_type, item.occurred_at, item.source_refs) for item in events)
        diagnostics = (
            ProjectionDiagnostic("operations_usage_unavailable", DiagnosticSeverity.WARNING, "权威来源未提供 token usage。"),
            ProjectionDiagnostic("operations_recovery_unavailable", DiagnosticSeverity.WARNING, "权威来源未提供 recovery 状态。"),
            ProjectionDiagnostic("operations_retry_unavailable", DiagnosticSeverity.WARNING, "权威来源未提供 retry 状态。"),
        )
        return cls(
            snapshot.project_id, len(tasks), len(executions), failed, attempts, None,
            snapshot.trace.source_refs, diagnostics, tasks, executions, errors,
        )

@dataclass(frozen=True, slots=True)
class SectionEnvelope:
    status: Freshness
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()

@dataclass(frozen=True, slots=True)
class ProjectionEnvelope:
    project_id: str
    snapshot: ProjectSnapshot | None
    operations: OperationsSnapshot | None
    overall: Freshness
    sections: Mapping[ProjectionSection, SectionEnvelope]
    source_heads: tuple[SourceHead, ...]
    refresh_id: str | None = None

@dataclass(frozen=True, slots=True)
class ProjectionBundle:
    project: ProjectSnapshot | None
    operations: OperationsSnapshot | None
    source_heads: tuple[SourceHead, ...]
    freshness: Mapping[ProjectionSection, Freshness]
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()
    refresh_id: str | None = None
