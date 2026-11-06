"""版本2迁移证据契约；纯校验，不依赖命令边界或Runtime。"""

from uuid import UUID

from creative_os.novel_project import sanitize_project_folder_name
from creative_os.project_directory import validate_project_id
from creative_os.project_directory_inventory import inventory_hash
from creative_os.project_migration_activity import _valid_result


def command_fingerprint(raw):
    return inventory_hash({key: value for key, value in raw.items() if key != "request_id"})


def validate_evidence(value):
    extra = {"record_version", "actor", "plan", "original_request", "command_fingerprint", "trace_id", "owner_epoch",
             "result_template", "backup_verified", "move_started", "continuation_ready", "consumed_continuation", "reload_required"}
    basic = {"operation_id", "project_id", "plan_fingerprint", "source_directory", "target_directory", "backup_directory", "stage", "continuation_no", "reason"}
    if set(value) != basic | extra or type(value["record_version"]) is not int or value["record_version"] != 2:
        raise ValueError("migration_evidence_invalid")
    if str(UUID(value["operation_id"])) != value["operation_id"]:
        raise ValueError("migration_evidence_invalid")
    validate_project_id(value["project_id"])
    for key in ("source_directory", "target_directory"):
        if sanitize_project_folder_name(value[key]) != value[key]:
            raise ValueError("migration_path_invalid")
    if value["backup_directory"] != f".backup/project-directory-migrations/{value['operation_id']}/project":
        raise ValueError("migration_path_invalid")
    plan = value["plan"]
    fields = {"project_id", "source_directory", "target_directory", "root_identity", "source_identity", "metadata_hash", "source_inventory_hash", "target_empty"}
    if not isinstance(plan, dict) or set(plan) != fields or plan["target_empty"] is not True or inventory_hash(plan) != value["plan_fingerprint"]:
        raise ValueError("migration_plan_invalid")
    for key in ("project_id", "source_directory", "target_directory"):
        if plan[key] != value[key]:
            raise ValueError("migration_plan_invalid")
    for key in ("root_identity", "source_identity"):
        if not isinstance(plan[key], dict) or set(plan[key]) != {"device", "inode"} or any(type(n) is not int or n < 0 for n in plan[key].values()):
            raise ValueError("migration_plan_invalid")
    for key in ("metadata_hash", "source_inventory_hash"):
        if not isinstance(plan[key], str) or len(plan[key]) != 64 or any(c not in "0123456789abcdef" for c in plan[key]):
            raise ValueError("migration_plan_invalid")
    raw = value["original_request"]
    if not isinstance(raw, dict) or set(raw) != {"command_id", "request_id", "actor", "target", "payload", "expected_version", "idempotency_key"}:
        raise ValueError("migration_request_invalid")
    if (raw["command_id"] != "migrate_project_directory" or raw["target"] != {"project_id": value["project_id"]}
            or raw["actor"] != value["actor"] or not isinstance(value["actor"], str) or not value["actor"].strip()
            or raw["idempotency_key"] != "directory-migrate:" + value["operation_id"] or raw["expected_version"] is not None
            or not isinstance(raw["request_id"], str) or not raw["request_id"].strip()):
        raise ValueError("migration_request_invalid")
    payload = raw["payload"]
    if (not isinstance(payload, dict) or set(payload) != {"operation_id", "plan_fingerprint", "preview_token", "confirmed"}
            or payload["operation_id"] != value["operation_id"] or payload["plan_fingerprint"] != value["plan_fingerprint"]
            or payload["confirmed"] is not True or not isinstance(payload["preview_token"], str)
            or command_fingerprint(raw) != value["command_fingerprint"]):
        raise ValueError("migration_request_invalid")
    for key in ("trace_id", "owner_epoch"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError("migration_evidence_invalid")
    for key in ("backup_verified", "move_started", "continuation_ready", "reload_required"):
        if type(value[key]) is not bool:
            raise ValueError("migration_evidence_invalid")
    if type(value["consumed_continuation"]) is not int or not 0 <= value["consumed_continuation"] <= value["continuation_no"]:
        raise ValueError("migration_evidence_invalid")
    result = value["result_template"]
    if result is not None:
        if not _valid_result(result) or result["trace_id"] != value["trace_id"] or result["request_id"] != raw["request_id"] or result["command_id"] != raw["command_id"]:
            raise ValueError("migration_result_invalid")
    if value["move_started"] and not value["backup_verified"]:
        raise ValueError("migration_checkpoint_invalid")
    if value["stage"] in {"backup_verified", "moving", "verified"} and not value["backup_verified"]:
        raise ValueError("migration_checkpoint_invalid")
    if value["stage"] == "verified" and (not value["move_started"] or result is None or result["status"] != "accepted"):
        raise ValueError("migration_checkpoint_invalid")
    if value["stage"] == "failed" and (value["move_started"] or result is None or result["status"] != "failed"):
        raise ValueError("migration_checkpoint_invalid")
    if result is not None and value["stage"] not in {"verified", "failed"}:
        raise ValueError("migration_checkpoint_invalid")
    if value["continuation_ready"] and (value["stage"] != "backup_verified" or value["continuation_no"] <= value["consumed_continuation"]):
        raise ValueError("migration_checkpoint_invalid")
    if value["reason"] is not None and not isinstance(value["reason"], str):
        raise ValueError("migration_evidence_invalid")
    return value
