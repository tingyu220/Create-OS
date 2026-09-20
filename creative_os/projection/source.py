from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from creative_os.projection.model import ProjectionDiagnostic
from creative_os.projection.provenance import SourceHead, SourceRef


@dataclass(frozen=True, slots=True)
class ProjectionCursor:
    source_heads: tuple[SourceHead, ...]


@dataclass(frozen=True, slots=True)
class ProjectionChangeSet:
    changed_source_kinds: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChapterStatusFact:
    chapter_number: int
    status: str
    attempts: int
    elapsed_seconds: float
    issues: tuple[str, ...]
    source_ref: SourceRef


@dataclass(frozen=True, slots=True)
class ChapterCheckpointFact:
    chapter_number: int
    state: str
    sequence: int
    checkpoint_hash: str
    refs: tuple[str, ...]
    source_ref: SourceRef


@dataclass(frozen=True, slots=True)
class QualityIssueFact:
    issue_id: str
    code: str
    severity: str
    blocking: bool
    scope: str
    source_ref: SourceRef


@dataclass(frozen=True, slots=True)
class GateResultFact:
    gate_id: str
    status: str
    chapter_number: int | None
    source_ref: SourceRef


@dataclass(frozen=True, slots=True)
class ExecutionEventFact:
    event_id: str
    event_type: str
    occurred_at: str
    sequence: int
    task_id: str | None
    execution_id: str | None
    payload_json: str
    source_ref: SourceRef


@dataclass(frozen=True, slots=True)
class RuntimeReportFact:
    report_id: str
    mode: str
    model: str
    chapter_id: str
    stage: str
    elapsed_seconds: float
    source_ref: SourceRef


@dataclass(frozen=True, slots=True)
class ActiveStateFact:
    kind: str
    subject: str
    fields_json: str
    source_ref: SourceRef
    evidence_refs: tuple[SourceRef, ...] = ()


@dataclass(frozen=True, slots=True)
class EngagementExpectationFact:
    """已获批准且完成 transition 的 engagement 事实。"""

    expectation_id: str
    from_state: str
    to_state: str
    content_hash: str
    source_ref: SourceRef
    decision_source_ref: SourceRef


@dataclass(frozen=True, slots=True)
class ProjectFacts:
    project_id: str
    chapter_statuses: tuple[ChapterStatusFact, ...]
    quality_issues: tuple[QualityIssueFact, ...]
    gate_results: tuple[GateResultFact, ...]
    execution_events: tuple[ExecutionEventFact, ...]
    runtime_reports: tuple[RuntimeReportFact, ...]
    diagnostics: tuple[ProjectionDiagnostic, ...]
    source_refs: tuple[SourceRef, ...]
    active_states: tuple[ActiveStateFact, ...] = ()
    engagement_expectations: tuple[EngagementExpectationFact, ...] = ()
    chapter_checkpoints: tuple[ChapterCheckpointFact, ...] = ()


class ProjectSource(Protocol):
    def read_head(self) -> tuple[SourceHead, ...]: ...

    def read_facts(self, cursor: ProjectionCursor | None = None) -> ProjectFacts: ...
