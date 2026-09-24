"""面向 Workspace UI 的领域中立 ViewModel。

该模块只消费 ``ProjectionEnvelope``，不访问领域、运行时、文件系统或投影仓库。
ViewModel 仅做展示所需的派生、排序和筛选；来源证据在对象详情层保留为稳定 DTO。
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from creative_os.workspace_dto import Freshness, ProjectionEnvelope, ProjectionSection


@dataclass(frozen=True, slots=True)
class WorkspaceDiagnosticVM:
    code: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class EvidenceRefVM:
    source_kind: str
    source_id: str
    locator: str
    content_hash: str | None


@dataclass(frozen=True, slots=True)
class ChapterSummaryVM:
    total: int
    completed: int
    running: int
    blocked: int
    failed: int
    not_started: int


@dataclass(frozen=True, slots=True)
class QualitySummaryVM:
    total: int
    blocking: int
    unresolved: int


@dataclass(frozen=True, slots=True)
class RuntimeSummaryVM:
    task_count: int
    execution_count: int
    failed_count: int
    attempts: int


@dataclass(frozen=True, slots=True)
class WorkspaceOverviewVM:
    project_id: str
    freshness: Freshness
    current_stage: str
    run_status: str
    chapter_summary: ChapterSummaryVM
    quality_summary: QualitySummaryVM
    runtime_summary: RuntimeSummaryVM
    attention_count: int
    diagnostics: tuple[WorkspaceDiagnosticVM, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceListItemVM:
    detail_key: str
    title: str
    status: str
    status_label: str
    chapter_number: int
    attempts: int
    elapsed_seconds: float
    checkpoint_state: str | None
    stage_label: str | None
    evidence_count: int


@dataclass(frozen=True, slots=True)
class WorkspaceListVM:
    project_id: str
    freshness: Freshness
    query: str
    total: int
    items: tuple[WorkspaceListItemVM, ...]
    diagnostics: tuple[WorkspaceDiagnosticVM, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceDetailVM:
    detail_key: str
    title: str
    status: str
    status_label: str
    attributes: Mapping[str, object]
    evidence: tuple[EvidenceRefVM, ...]
    freshness: Freshness
    diagnostics: tuple[WorkspaceDiagnosticVM, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceModuleVM:
    key: str
    label: str
    freshness: Freshness
    available: bool
    summary: str


_STATUS_LABELS = {
    "not_started": "未开始",
    "running": "运行中",
    "passed": "已通过",
    "failed": "失败",
    "blocked": "已阻塞",
    "unknown": "未知",
}

_STAGE_LABELS = {
    "planning": "规划",
    "admission": "准入",
    "writing": "写作",
    "review": "审阅",
    "compilation": "编译",
}


class WorkspaceViewModelAdapter:
    """把统一投影信封映射成正式 Workspace 使用的页面模型。"""

    def to_overview(self, envelope: ProjectionEnvelope) -> WorkspaceOverviewVM:
        snapshot = envelope.snapshot
        chapters = () if snapshot is None else snapshot.chapters
        quality = () if snapshot is None else snapshot.quality.issues
        operations = envelope.operations
        chapter_summary = ChapterSummaryVM(
            total=len(chapters),
            completed=sum(_value(item.status) == "passed" for item in chapters),
            running=sum(_value(item.status) == "running" for item in chapters),
            blocked=sum(_value(item.status) == "blocked" for item in chapters),
            failed=sum(_value(item.status) == "failed" for item in chapters),
            not_started=sum(_value(item.status) == "not_started" for item in chapters),
        )
        quality_summary = QualitySummaryVM(
            total=len(quality),
            blocking=sum(bool(item.blocking) for item in quality),
            unresolved=sum(_value(item.disposition_status) not in {"accepted", "resolved", "dismissed"} for item in quality),
        )
        runtime_summary = RuntimeSummaryVM(
            task_count=0 if operations is None or operations.task_count is None else operations.task_count,
            execution_count=0 if operations is None or operations.execution_count is None else operations.execution_count,
            failed_count=0 if operations is None or operations.failed_count is None else operations.failed_count,
            attempts=0 if operations is None or operations.attempts is None else operations.attempts,
        )
        current_stage = "未知" if snapshot is None else snapshot.overview.current_stage
        run_status = "unavailable" if snapshot is None else _value(snapshot.overview.run_status)
        return WorkspaceOverviewVM(
            project_id=envelope.project_id,
            freshness=envelope.overall,
            current_stage=current_stage,
            run_status=run_status,
            chapter_summary=chapter_summary,
            quality_summary=quality_summary,
            runtime_summary=runtime_summary,
            attention_count=chapter_summary.blocked + chapter_summary.failed + quality_summary.blocking,
            diagnostics=self._diagnostics(envelope),
        )

    def to_chapter_list(self, envelope: ProjectionEnvelope, query: str = "") -> WorkspaceListVM:
        snapshot = envelope.snapshot
        chapters = () if snapshot is None else tuple(sorted(snapshot.chapters, key=lambda item: item.chapter_number))
        normalized_query = query.strip()
        query_key = normalized_query.casefold()
        items = tuple(self._chapter_item(item) for item in chapters)
        if query_key:
            items = tuple(item for item in items if self._matches(item, query_key))
        return WorkspaceListVM(
            project_id=envelope.project_id,
            freshness=envelope.overall,
            query=normalized_query,
            total=len(items),
            items=items,
            diagnostics=self._diagnostics(envelope),
        )

    def to_chapter_detail(self, envelope: ProjectionEnvelope, chapter_number: int) -> WorkspaceDetailVM | None:
        snapshot = envelope.snapshot
        if snapshot is None:
            return None
        chapter = next((item for item in snapshot.chapters if item.chapter_number == chapter_number), None)
        if chapter is None:
            return None
        stage = _current_stage(chapter)
        attributes = MappingProxyType({
            "chapter_number": chapter.chapter_number,
            "chapter_id": chapter.chapter_id,
            "attempts": chapter.attempts,
            "elapsed_seconds": chapter.elapsed_seconds,
            "checkpoint_state": chapter.checkpoint_state,
            "stage": None if stage is None else _value(stage.stage),
            "stage_status": None if stage is None else _value(stage.status),
        })
        return WorkspaceDetailVM(
            detail_key=f"chapter:{chapter.chapter_number}",
            title=chapter.title,
            status=_value(chapter.status),
            status_label=_status_label(chapter.status, stage),
            attributes=attributes,
            evidence=tuple(_evidence(ref) for ref in chapter.source_refs),
            freshness=envelope.overall,
            diagnostics=self._diagnostics(envelope),
        )

    def modules(self, envelope: ProjectionEnvelope) -> tuple[WorkspaceModuleVM, ...]:
        """返回固定概念模块；可用性来自投影信封，不创造领域事实。"""
        snapshot = envelope.snapshot
        project_status = envelope.sections.get(ProjectionSection.PROJECT)
        operations_status = envelope.sections.get(ProjectionSection.OPERATIONS)
        return (
            WorkspaceModuleVM("overview", "总览", envelope.overall, snapshot is not None, "项目进度与关注项"),
            WorkspaceModuleVM("chapters", "章节", envelope.overall, snapshot is not None, "章节列表与详情"),
            WorkspaceModuleVM("story", "故事", envelope.overall, snapshot is not None, "故事结构与线索"),
            WorkspaceModuleVM("characters", "角色", envelope.overall, snapshot is not None, "角色关系与状态"),
            WorkspaceModuleVM("quality", "质量", envelope.overall, snapshot is not None, "质量问题与审阅"),
            WorkspaceModuleVM("runtime", "运行", Freshness.UNAVAILABLE if operations_status is None else operations_status.status, envelope.operations is not None, "任务与诊断"),
        )

    @staticmethod
    def _chapter_item(chapter: object) -> WorkspaceListItemVM:
        stage = _current_stage(chapter)
        return WorkspaceListItemVM(
            detail_key=f"chapter:{chapter.chapter_number}",
            title=chapter.title,
            status=_value(chapter.status),
            status_label=_status_label(chapter.status, stage),
            chapter_number=chapter.chapter_number,
            attempts=chapter.attempts,
            elapsed_seconds=chapter.elapsed_seconds,
            checkpoint_state=chapter.checkpoint_state,
            stage_label=None if stage is None else _stage_label(stage.stage),
            evidence_count=len(chapter.source_refs),
        )

    @staticmethod
    def _matches(item: WorkspaceListItemVM, query: str) -> bool:
        haystack = " ".join((item.title, item.status, item.status_label, item.stage_label or "", str(item.chapter_number))).casefold()
        return query in haystack

    @staticmethod
    def _diagnostics(envelope: ProjectionEnvelope) -> tuple[WorkspaceDiagnosticVM, ...]:
        values: list[WorkspaceDiagnosticVM] = []
        seen: set[tuple[str, str]] = set()
        for section in envelope.sections.values():
            for diagnostic in section.diagnostics:
                key = (diagnostic.code, diagnostic.message)
                if key not in seen:
                    seen.add(key)
                    values.append(WorkspaceDiagnosticVM(diagnostic.code, _value(diagnostic.severity), diagnostic.message))
        if envelope.operations is not None:
            for diagnostic in envelope.operations.diagnostics:
                key = (diagnostic.code, diagnostic.message)
                if key not in seen:
                    seen.add(key)
                    values.append(WorkspaceDiagnosticVM(diagnostic.code, _value(diagnostic.severity), diagnostic.message))
        if envelope.overall == Freshness.UNAVAILABLE and not values:
            values.append(WorkspaceDiagnosticVM("workspace_unavailable", "warning", "当前 Workspace 数据不可用。"))
        return tuple(values)


def _value(value: object) -> str:
    return getattr(value, "value", value) if value is not None else ""


def _stage_label(stage: object) -> str:
    value = _value(stage)
    return _STAGE_LABELS.get(value, value or "未知")


def _status_label(status: object, stage: object | None = None) -> str:
    value = _value(status)
    label = _STATUS_LABELS.get(value, value or "未知")
    if stage is not None:
        # 同时保留稳定 stage code，便于筛选与未来 Domain Plugin 映射。
        label = f"{label} · {_value(stage.stage)}"
    return label


def _current_stage(chapter: object) -> object | None:
    stages = getattr(chapter, "stages", ())
    if not stages:
        return None
    for stage in reversed(stages):
        if _value(stage.status) in {"running", "blocked", "failed"}:
            return stage
    return stages[-1]


def _evidence(ref: object) -> EvidenceRefVM:
    return EvidenceRefVM(
        source_kind=str(getattr(ref, "source_kind", "")),
        source_id=str(getattr(ref, "source_id", "")),
        locator=str(getattr(ref, "locator", "")),
        content_hash=getattr(ref, "content_hash", None),
    )
