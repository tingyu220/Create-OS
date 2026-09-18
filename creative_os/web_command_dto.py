from __future__ import annotations

from dataclasses import dataclass
import json
from creative_os.workspace_command import CommandRequest, CommandResult


_REQUEST_FIELDS = frozenset(
    {
        "command_id",
        "request_id",
        "actor",
        "target",
        "payload",
        "expected_version",
        "idempotency_key",
    }
)
_REVIEW_REQUEST_FIELDS = _REQUEST_FIELDS | {"status"}


@dataclass(frozen=True, slots=True)
class WebCommandValidationError(ValueError):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def decode_web_command(raw: object) -> CommandRequest:
    if not isinstance(raw, dict) or not _has_valid_request_fields(raw):
        raise WebCommandValidationError("validation_failed", "命令请求字段必须严格匹配契约。")

    command_id = _required_string(raw["command_id"], "command_id")
    request_id = _required_string(raw["request_id"], "request_id")
    actor = _required_string(raw["actor"], "actor")
    target = raw["target"]
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise WebCommandValidationError("validation_failed", "命令载荷必须是 JSON 对象。")
    try:
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise WebCommandValidationError("validation_failed", "命令载荷必须是有效 JSON。") from error

    expected_version = raw["expected_version"]
    if command_id == "refresh_workspace_projection":
        target = _required_string(target, "target")
        if expected_version is not None:
            raise WebCommandValidationError("validation_failed", "刷新投影命令不支持 expected_version。")
    elif command_id == "accept_review_issue":
        target = _review_issue_target(target)
        if expected_version is not None:
            raise WebCommandValidationError("validation_failed", "接受审阅问题命令不支持顶层 expected_version。")
        _validate_review_issue_payload(payload)
    elif command_id == "start_chapter_run":
        target = _chapter_run_target(target)
        if expected_version is not None:
            raise WebCommandValidationError("validation_failed", "章节运行命令不支持 expected_version。")
        if payload:
            raise WebCommandValidationError("validation_failed", "章节运行命令载荷必须为空对象。")
    else:
        raise WebCommandValidationError("command_not_allowed", "当前命令不在允许范围内。")
    idempotency_key = _required_string(raw["idempotency_key"], "idempotency_key")
    status = raw.get("status", "accepted")
    if type(status) is not str or not status.strip():
        raise WebCommandValidationError("validation_failed", "status 必须是非空字符串。")
    return CommandRequest(command_id, request_id, actor, target, payload, expected_version, idempotency_key, status=status)


def encode_command_result(result: CommandResult) -> dict[str, object]:
    return {
        "status": result.status.value,
        "command_id": result.command_id,
        "request_id": result.request_id,
        "error": None
        if result.error is None
        else {
            "code": result.error.code,
            "message": result.error.message,
            "retryable": result.error.retryable,
        },
        "audit_ref": result.audit_ref,
        "trace_id": result.trace_id,
        "emitted_event_refs": list(result.emitted_event_refs),
        "projection_refresh_id": result.projection_refresh_id,
    }


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WebCommandValidationError("validation_failed", f"{field} 必须是非空字符串。")
    return value


def _has_valid_request_fields(raw: dict[object, object]) -> bool:
    fields = frozenset(raw)
    command_id = raw.get("command_id")
    if command_id == "accept_review_issue":
        return fields in {_REQUEST_FIELDS, _REVIEW_REQUEST_FIELDS}
    return fields == _REQUEST_FIELDS


def _review_issue_target(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"project_id", "issue_id"}:
        raise WebCommandValidationError("validation_failed", "target 必须严格包含 project_id 与 issue_id。")
    return {
        "project_id": _required_string(value["project_id"], "target.project_id"),
        "issue_id": _required_string(value["issue_id"], "target.issue_id"),
    }


def _chapter_run_target(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"project_id", "chapter_number"}:
        raise WebCommandValidationError("validation_failed", "target 必须严格包含 project_id 与 chapter_number。")
    project_id = _required_string(value["project_id"], "target.project_id")
    chapter_number = value["chapter_number"]
    if type(chapter_number) is not int or chapter_number <= 0:
        raise WebCommandValidationError("validation_failed", "target.chapter_number 必须是正整数。")
    return {"project_id": project_id, "chapter_number": chapter_number}


def _validate_review_issue_payload(payload: dict[str, object]) -> None:
    allowed = {"reason", "reviewer_result_id", "reviewer_result_hash", "expected_version"}
    if set(payload) not in (allowed, allowed | {"status"}):
        raise WebCommandValidationError("validation_failed", "审阅问题命令载荷字段不符合契约。")
    _required_string(payload["reason"], "payload.reason")
    _required_string(payload["reviewer_result_id"], "payload.reviewer_result_id")
    reviewer_result_hash = payload["reviewer_result_hash"]
    if not isinstance(reviewer_result_hash, str) or len(reviewer_result_hash) != 64 or any(char not in "0123456789abcdef" for char in reviewer_result_hash):
        raise WebCommandValidationError("validation_failed", "payload.reviewer_result_hash 必须是小写 sha256。")
    expected_version = payload["expected_version"]
    if type(expected_version) is not int or expected_version < 1:
        raise WebCommandValidationError("validation_failed", "payload.expected_version 必须是正整数。")
    if "status" in payload and type(payload["status"]) is not str:
        raise WebCommandValidationError("validation_failed", "payload.status 必须是字符串。")
