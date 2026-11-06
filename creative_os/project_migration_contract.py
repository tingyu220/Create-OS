"""三个迁移命令的唯一契约；路径只由服务端计划生成。"""

from uuid import UUID
from creative_os.project_directory import validate_project_id

COMMANDS = {"migrate_project_directory", "reconcile_project_directory", "continue_project_directory"}


def validate_directory_command(command_id, target, payload, expected_version):
    if command_id not in COMMANDS or expected_version is not None or not isinstance(target, dict) or not isinstance(payload, dict):
        raise ValueError("migration_request_invalid")
    begin = command_id == "migrate_project_directory"
    if set(target) != ({"project_id"} if begin else {"project_id", "operation_id"}):
        raise ValueError("migration_request_invalid")
    validate_project_id(target["project_id"])
    fields = ({"operation_id", "plan_fingerprint", "preview_token", "confirmed"} if begin else
              {"plan_fingerprint", "continuation_no", "confirmed"} if command_id == "continue_project_directory" else {"plan_fingerprint"})
    if set(payload) != fields:
        raise ValueError("migration_request_invalid")
    op = payload["operation_id"] if begin else target["operation_id"]
    try:
        valid_op = isinstance(op, str) and str(UUID(op)) == op
    except (ValueError, AttributeError):
        valid_op = False
    if not valid_op:
        raise ValueError("migration_operation_id_invalid")
    digest = payload["plan_fingerprint"]
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("migration_fingerprint_invalid")
    if "confirmed" in fields and payload["confirmed"] is not True:
        raise ValueError("migration_confirmation_required")
    if begin and (not isinstance(payload["preview_token"], str) or not payload["preview_token"].strip() or len(payload["preview_token"]) > 4096):
        raise ValueError("preview_token_invalid")
    if "continuation_no" in fields and (type(payload["continuation_no"]) is not int or payload["continuation_no"] <= 0):
        raise ValueError("continuation_no_invalid")
    return op


def expected_key(request, operation_id):
    if request.command_id == "migrate_project_directory":
        return f"directory-migrate:{operation_id}"
    if request.command_id == "reconcile_project_directory":
        return f"directory-reconcile:{operation_id}:{request.request_id}"
    return f"directory-continue:{operation_id}:{request.payload['continuation_no']}"


def request_data(request):
    return {"command_id": request.command_id, "request_id": request.request_id, "actor": request.actor,
            "target": dict(request.target), "payload": dict(request.payload), "expected_version": request.expected_version,
            "idempotency_key": request.idempotency_key}
