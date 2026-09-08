from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
import json
from typing import Mapping
from creative_os.projection.codec import encode_project_snapshot
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


def encode_workspace_envelope(envelope: ProjectionEnvelope) -> dict[str, object]:
    """将 Workspace DTO 编码为稳定的 JSON-safe 结构，隔离 Projection 内部类型。"""
    return {
        "project_id": envelope.project_id,
        "overall": envelope.overall.value,
        "sections": {key.value: _encode_section(value) for key, value in sorted(envelope.sections.items(), key=lambda item: item[0].value)},
        "snapshot": None if envelope.snapshot is None else json.loads(encode_project_snapshot(envelope.snapshot)),
        "operations": None if envelope.operations is None else _encode_operations(envelope.operations),
        "source_heads": [_encode_head(item) for item in envelope.source_heads],
        "refresh_id": envelope.refresh_id,
    }


def _encode_section(value: SectionEnvelope) -> dict[str, object]:
    return {"status": value.status.value, "diagnostics": [_encode_diagnostic(item) for item in value.diagnostics]}


def _encode_operations(value: OperationsSnapshot) -> dict[str, object]:
    return {
        "project_id": value.project_id,
        "task_count": value.task_count,
        "execution_count": value.execution_count,
        "failed_count": value.failed_count,
        "attempts": value.attempts,
        "usage": None if value.usage is None else {
            "prompt_tokens": value.usage.prompt_tokens,
            "completion_tokens": value.usage.completion_tokens,
            "total_tokens": value.usage.total_tokens,
        },
        "source_refs": [_encode_ref(item) for item in value.source_refs],
        "diagnostics": [_encode_diagnostic(item) for item in value.diagnostics],
        "tasks": [_encode_task(item) for item in value.tasks],
        "executions": [_encode_execution(item) for item in value.executions],
        "errors": [_encode_error(item) for item in value.errors],
        "recovery": None if value.recovery is None else _encode_recovery(value.recovery),
        "retries": [_encode_retry(item) for item in value.retries],
    }


def _encode_ref(value: SourceRef) -> dict[str, object]:
    return {"source_kind": value.source_kind, "source_id": value.source_id, "locator": value.locator, "content_hash": value.content_hash}


def _encode_head(value: SourceHead) -> dict[str, object]:
    return {"source_kind": value.source_kind, "source_id": value.source_id, "cursor": value.cursor, "content_hash": value.content_hash}


def _encode_diagnostic(value: ProjectionDiagnostic) -> dict[str, object]:
    return {"code": value.code, "severity": value.severity.value, "message": value.message, "source_refs": [_encode_ref(item) for item in value.source_refs]}


def _encode_task(value: TaskDTO) -> dict[str, object]:
    return {"task_id": value.task_id, "status": value.status, "attempts": value.attempts, "elapsed_seconds": value.elapsed_seconds, "source_refs": [_encode_ref(item) for item in value.source_refs]}


def _encode_execution(value: ExecutionDTO) -> dict[str, object]:
    return {"execution_id": value.execution_id, "identity_kind": value.identity_kind, "event_type": value.event_type, "occurred_at": value.occurred_at, "source_refs": [_encode_ref(item) for item in value.source_refs]}


def _encode_error(value: ErrorDTO) -> dict[str, object]:
    return {"code": value.code, "message": value.message, "retryable": value.retryable, "source_refs": [_encode_ref(item) for item in value.source_refs]}


def _encode_recovery(value: RecoveryDTO) -> dict[str, object]:
    return {"state": value.state, "source_refs": [_encode_ref(item) for item in value.source_refs]}


def _encode_retry(value: RetryDTO) -> dict[str, object]:
    return {"attempts": value.attempts, "source_refs": [_encode_ref(item) for item in value.source_refs]}
