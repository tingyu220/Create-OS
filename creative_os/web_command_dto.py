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


@dataclass(frozen=True, slots=True)
class WebCommandValidationError(ValueError):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def decode_web_command(raw: object) -> CommandRequest:
    if not isinstance(raw, dict) or frozenset(raw) != _REQUEST_FIELDS:
        raise WebCommandValidationError("validation_failed", "命令请求字段必须严格匹配契约。")

    command_id = _required_string(raw["command_id"], "command_id")
    if command_id != "refresh_workspace_projection":
        raise WebCommandValidationError("command_not_allowed", "当前只允许刷新工作区投影命令。")
    request_id = _required_string(raw["request_id"], "request_id")
    actor = _required_string(raw["actor"], "actor")
    target = _required_string(raw["target"], "target")
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise WebCommandValidationError("validation_failed", "命令载荷必须是 JSON 对象。")
    try:
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise WebCommandValidationError("validation_failed", "命令载荷必须是有效 JSON。") from error

    expected_version = raw["expected_version"]
    if expected_version is not None:
        raise WebCommandValidationError("validation_failed", "刷新投影命令不支持 expected_version。")
    idempotency_key = _required_string(raw["idempotency_key"], "idempotency_key")
    return CommandRequest(command_id, request_id, actor, target, payload, expected_version, idempotency_key)


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
