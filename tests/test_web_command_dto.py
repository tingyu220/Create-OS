from __future__ import annotations

import pytest

from creative_os.workspace_command import CommandError, CommandRequest, CommandResult, CommandStatus
from creative_os.web_command_dto import WebCommandValidationError, decode_web_command, encode_command_result


def _raw(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "command_id": "refresh_workspace_projection",
        "request_id": "request-1",
        "actor": "local-user",
        "target": "novel-1",
        "payload": {"sections": ["project", "operations"]},
        "expected_version": None,
        "idempotency_key": "refresh-1",
    }
    value.update(overrides)
    return value


def test_decode_refresh_command_requires_exact_fields():
    request = decode_web_command(_raw())

    assert request == CommandRequest(
        "refresh_workspace_projection",
        "request-1",
        "local-user",
        "novel-1",
        {"sections": ["project", "operations"]},
        None,
        "refresh-1",
    )


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"extra": True}, "validation_failed"),
        ({"command_id": "delete_project"}, "command_not_allowed"),
        ({"request_id": ""}, "validation_failed"),
        ({"actor": "   "}, "validation_failed"),
        ({"expected_version": True}, "validation_failed"),
        ({"expected_version": 1}, "validation_failed"),
        ({"payload": []}, "validation_failed"),
        ({"idempotency_key": 1}, "validation_failed"),
    ],
)
def test_decode_rejects_invalid_web_commands(overrides: dict[str, object], code: str):
    with pytest.raises(WebCommandValidationError) as error:
        decode_web_command(_raw(**overrides))

    assert error.value.code == code


def test_encode_command_result_preserves_trace_and_refresh_receipt():
    result = CommandResult(
        CommandStatus.ACCEPTED,
        "refresh_workspace_projection",
        "request-1",
        audit_ref="audit-request-1",
        trace_id="trace-1",
        emitted_event_refs=(),
        projection_refresh_id="refresh-1",
    )

    assert encode_command_result(result) == {
        "status": "accepted",
        "command_id": "refresh_workspace_projection",
        "request_id": "request-1",
        "error": None,
        "audit_ref": "audit-request-1",
        "trace_id": "trace-1",
        "emitted_event_refs": [],
        "projection_refresh_id": "refresh-1",
    }


def test_encode_command_result_preserves_stable_error():
    result = CommandResult(
        CommandStatus.REJECTED,
        "refresh_workspace_projection",
        "request-1",
        error=CommandError("target_not_found", "目标项目不存在。", False),
    )

    assert encode_command_result(result)["error"] == {
        "code": "target_not_found",
        "message": "目标项目不存在。",
        "retryable": False,
    }
