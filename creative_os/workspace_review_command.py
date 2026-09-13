from __future__ import annotations

from typing import Mapping

from creative_os.domains.review_issue_command import (
    AcceptReviewIssueCommand,
    CommandStatus as DomainCommandStatus,
    accept_review_issue,
)
from creative_os.workspace_command import (
    CommandError,
    CommandHandlerResult,
    CommandRejectedError,
    CommandRequest,
    CommandStatus,
)


class WorkspaceReviewIssueCommandHandler:
    """把工作区请求转换为领域命令，不在 Web 层复制领域校验。"""

    def __init__(self, project_id: str, store, event_sink) -> None:
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("workspace_project_id_required")
        self._project_id = project_id.strip()
        self._store = store
        self._event_sink = event_sink

    def validate(self, request: CommandRequest) -> None:
        if request.command_id != "accept_review_issue":
            raise CommandRejectedError("command_not_allowed", "当前只允许接受审阅问题命令。")
        if request.expected_version is not None:
            raise CommandRejectedError("validation_failed", "接受审阅问题命令不支持顶层 expected_version。")
        if not isinstance(request.target, Mapping) or set(request.target) != {"project_id", "issue_id"}:
            raise CommandRejectedError("validation_failed", "目标必须包含 project_id 与 issue_id。")
        if request.target.get("project_id") != self._project_id:
            raise CommandRejectedError("target_not_found", "目标小说项目不存在。")
        if not isinstance(request.payload, Mapping):
            raise CommandRejectedError("validation_failed", "命令载荷必须是对象。")

    def execute_with_trace(self, request: CommandRequest, trace_id: str) -> CommandHandlerResult:
        self.validate(request)
        command = AcceptReviewIssueCommand(
            command_id=request.command_id,
            request_id=request.request_id,
            actor=request.actor,
            target=dict(request.target),  # type: ignore[arg-type]
            payload=dict(request.payload),
            idempotency_key=request.idempotency_key,
            trace_id=trace_id,
            status=request.status,
        )
        outcome = accept_review_issue(command, self._store, self._event_sink)
        if outcome.status is DomainCommandStatus.ACCEPTED:
            if outcome.receipt is None or outcome.event_id is None or outcome.audit_ref is None:
                raise RuntimeError("review_issue_command_receipt_missing")
            return CommandHandlerResult(
                emitted_event_refs=(outcome.event_id,),
                audit_ref=outcome.audit_ref,
            )
        if outcome.error is None:
            raise RuntimeError("review_issue_command_error_missing")
        status = CommandStatus.REJECTED if outcome.status in {
            DomainCommandStatus.REJECTED,
            DomainCommandStatus.CONFLICT,
        } else CommandStatus.FAILED
        return CommandHandlerResult(
            status=status,
            error=CommandError(outcome.error.code, outcome.error.message, outcome.error.retryable),
            audit_ref=outcome.audit_ref,
        )
