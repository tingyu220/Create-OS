"""迁移前的只读活动证据检查；未知状态按不可迁移处理。"""

import json

from creative_os.project_directory import read_project_metadata


def _read(path):
    if path.is_symlink() or path.resolve() != path.absolute():
        raise ValueError("project_migration_state_unknown")
    return json.loads(path.read_text(encoding="utf-8"))


def _valid_result(value):
    fields = {"status", "command_id", "request_id", "error", "audit_ref", "trace_id", "emitted_event_refs", "projection_refresh_id"}
    if not isinstance(value, dict) or set(value) != fields or value["status"] not in {"accepted", "rejected", "failed"}:
        return False
    if any(not isinstance(value[key], str) or not value[key].strip() for key in ("command_id", "request_id")):
        return False
    if any(value[key] is not None and not isinstance(value[key], str) for key in ("audit_ref", "trace_id", "projection_refresh_id")):
        return False
    if not isinstance(value["emitted_event_refs"], list) or any(not isinstance(ref, str) for ref in value["emitted_event_refs"]):
        return False
    error = value["error"]
    if value["status"] == "accepted":
        return error is None
    return (isinstance(error, dict) and set(error) == {"code", "message", "retryable"}
            and isinstance(error["code"], str) and isinstance(error["message"], str) and type(error["retryable"]) is bool)


def assert_persistent_idle(projects_root, source, project_id):
    try:
        if read_project_metadata(projects_root, source)["id"] != project_id:
            raise ValueError("project_migration_state_unknown")
        conversations = source / ".creative_os/agent/conversations"
        if conversations.exists() and (not conversations.is_dir() or conversations.resolve() != conversations.absolute()):
            raise ValueError("project_migration_state_unknown")
        for path in conversations.glob("*.json"):
            value = _read(path)
            if not isinstance(value, dict) or value.get("project_id") != project_id or not isinstance(value.get("jobs"), dict):
                raise ValueError("project_migration_state_unknown")
            for key, job in value["jobs"].items():
                if not isinstance(job, dict) or job.get("job_id") != key or not isinstance(job.get("status"), str):
                    raise ValueError("project_migration_state_unknown")
                if job["status"] not in {"completed", "failed"}:
                    raise ValueError("project_migration_active")
        receipt = source / ".creative_os/commands/results.json"
        if receipt.exists():
            value = _read(receipt)
            if not isinstance(value, dict) or set(value) != {"schema_version", "records"} or type(value["schema_version"]) is not int or value["schema_version"] != 1 or not isinstance(value["records"], dict):
                raise ValueError("project_migration_state_unknown")
            for item in value["records"].values():
                if not isinstance(item, dict) or set(item) != {"fingerprint", "state", "result"} or not isinstance(item["fingerprint"], str):
                    raise ValueError("project_migration_state_unknown")
                if item["state"] == "reserved":
                    raise ValueError("project_migration_active")
                if item["state"] != "completed" or not _valid_result(item["result"]):
                    raise ValueError("project_migration_state_unknown")
        creation = projects_root / ".creative_os/new-books.json"
        if creation.exists():
            value = _read(creation)
            if not isinstance(value, dict):
                raise ValueError("project_migration_state_unknown")
            for item in value.values():
                if not isinstance(item, dict) or not isinstance(item.get("folder"), str) or item.get("status") not in {"initializing", "completed"}:
                    raise ValueError("project_migration_state_unknown")
                if item["folder"].casefold() == source.name.casefold() and item["status"] == "initializing":
                    raise ValueError("project_migration_active")
    except (OSError, TypeError, KeyError, ValueError) as error:
        if isinstance(error, ValueError) and str(error) in {"project_migration_active", "project_migration_state_unknown"}:
            raise
        raise ValueError("project_migration_state_unknown") from error
