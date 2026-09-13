from __future__ import annotations

from typing import Mapping, Protocol

from creative_os.workspace_command import (
    CommandBoundary,
    CommandRejectedError,
    CommandRequest,
    CommandResult,
)
from creative_os.workspace_dto import ProjectionSection
from creative_os.workspace_review_command import WorkspaceReviewIssueCommandHandler


class ProjectionRefreshCoordinatorLike(Protocol):
    def refresh(self, project_id: str, sections: set[ProjectionSection], trace_id: str | None = None): ...


class WorkspaceRefreshCommandHandler:
    """唯一允许的工作区命令处理器，只校验投影刷新请求。"""

    def __init__(self, project_id: str) -> None:
        if not project_id.strip():
            raise ValueError("workspace_project_id_required")
        self._project_id = project_id.strip()

    def validate(self, request: CommandRequest) -> None:
        if request.command_id != "refresh_workspace_projection":
            raise CommandRejectedError("command_not_allowed", "当前只允许刷新工作区投影命令。")
        if request.expected_version is not None:
            raise CommandRejectedError("validation_failed", "刷新投影命令不支持 expected_version。")
        if request.target != self._project_id:
            raise CommandRejectedError("target_not_found", "目标小说项目不存在。")
        sections = _sections(request)
        if not sections:
            raise CommandRejectedError("validation_failed", "至少需要请求一个投影分区。")

    def __call__(self, request: CommandRequest) -> tuple[str, ...]:
        self.validate(request)
        return ()


class WorkspaceProjectionRefreshScheduler:
    def __init__(self, coordinator: ProjectionRefreshCoordinatorLike) -> None:
        self._coordinator = coordinator

    def __call__(self, request: CommandRequest, _event_refs: tuple[str, ...], trace_id: str) -> str:
        sections = _sections(request)
        if not sections:
            raise CommandRejectedError("validation_failed", "至少需要请求一个投影分区。")
        result = self._coordinator.refresh(request.target, sections, trace_id=trace_id)
        if getattr(getattr(result, "status", None), "value", None) != "succeeded":
            raise RuntimeError("projection_refresh_failed")
        receipt = getattr(result, "receipt", None)
        refresh_id = getattr(receipt, "refresh_id", None)
        expected_sections = tuple(sorted(item.value for item in sections))
        if not isinstance(refresh_id, str) or not refresh_id:
            raise RuntimeError("projection_refresh_receipt_missing")
        if result.refresh_id != refresh_id:
            raise RuntimeError("projection_refresh_receipt_refresh_id_mismatch")
        if receipt.project_id != request.target:
            raise RuntimeError("projection_refresh_receipt_project_mismatch")
        if tuple(receipt.sections) != expected_sections:
            raise RuntimeError("projection_refresh_receipt_sections_mismatch")
        if not isinstance(receipt.snapshot_id, str) or not receipt.snapshot_id:
            raise RuntimeError("projection_refresh_receipt_snapshot_missing")
        if receipt.trace_id != trace_id:
            raise RuntimeError("projection_refresh_receipt_trace_mismatch")
        return refresh_id


class WorkspaceReviewIssueProjectionRefreshScheduler:
    """接受审阅问题后刷新质量所属的项目投影。"""

    def __init__(self, coordinator: ProjectionRefreshCoordinatorLike) -> None:
        self._coordinator = coordinator

    def __call__(self, request: CommandRequest, event_refs: tuple[str, ...], trace_id: str) -> str:
        return self.schedule_with_context(request, event_refs, trace_id, None)

    def schedule_with_context(
        self,
        request: CommandRequest,
        event_refs: tuple[str, ...],
        trace_id: str,
        audit_ref: str | None,
    ) -> str:
        target = request.target
        if not isinstance(target, Mapping):
            raise CommandRejectedError("validation_failed", "接受审阅问题命令目标格式无效。")
        project_id = target.get("project_id")
        if not isinstance(project_id, str) or not project_id:
            raise CommandRejectedError("validation_failed", "接受审阅问题命令项目目标无效。")
        refresh_with_context = getattr(self._coordinator, "refresh_command", None)
        if callable(refresh_with_context):
            result = refresh_with_context(
                project_id,
                {ProjectionSection.PROJECT},
                event_refs=event_refs,
                audit_ref=audit_ref,
                trace_id=trace_id,
            )
        else:
            result = self._coordinator.refresh(project_id, {ProjectionSection.PROJECT}, trace_id=trace_id)
        if getattr(getattr(result, "status", None), "value", None) != "succeeded":
            raise RuntimeError("projection_refresh_failed")
        receipt = getattr(result, "receipt", None)
        refresh_id = getattr(receipt, "refresh_id", None)
        if not isinstance(refresh_id, str) or not refresh_id:
            raise RuntimeError("projection_refresh_receipt_missing")
        if result.refresh_id != refresh_id:
            raise RuntimeError("projection_refresh_receipt_refresh_id_mismatch")
        if receipt.project_id != project_id:
            raise RuntimeError("projection_refresh_receipt_project_mismatch")
        if tuple(receipt.sections) != (ProjectionSection.PROJECT.value,):
            raise RuntimeError("projection_refresh_receipt_sections_mismatch")
        if not isinstance(receipt.snapshot_id, str) or not receipt.snapshot_id:
            raise RuntimeError("projection_refresh_receipt_snapshot_missing")
        if receipt.trace_id != trace_id:
            raise RuntimeError("projection_refresh_receipt_trace_mismatch")
        return refresh_id


class WorkspaceCommandAdapter:
    """将已解码的 Web 命令交给统一 Command Boundary。"""

    def __init__(self, boundary: CommandBoundary) -> None:
        self._boundary = boundary

    def execute(self, request: CommandRequest) -> CommandResult:
        return self._boundary.execute(request)


def _sections(request: CommandRequest) -> set[ProjectionSection]:
    payload = request.payload
    raw_sections = payload.get("sections") if isinstance(payload, Mapping) else None
    if not isinstance(raw_sections, list) or not raw_sections:
        raise CommandRejectedError("validation_failed", "payload.sections 必须是非空数组。")
    if any(not isinstance(item, str) for item in raw_sections):
        raise CommandRejectedError("validation_failed", "payload.sections 只能包含字符串。")
    if len(raw_sections) != len(set(raw_sections)):
        raise CommandRejectedError("validation_failed", "payload.sections 不得包含重复分区。")
    try:
        sections = {ProjectionSection(item) for item in raw_sections}
    except (TypeError, ValueError) as error:
        raise CommandRejectedError("validation_failed", "payload.sections 包含未知投影分区。") from error
    if len(sections) != len(raw_sections):
        raise CommandRejectedError("validation_failed", "payload.sections 包含无效分区。")
    return sections
