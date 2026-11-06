"""固定根内的迁移清单证据；不执行移动，也不创建Runtime。"""

import json
import os
from pathlib import Path

from creative_os.project_directory import read_project_metadata
from creative_os.project_directory_inventory import (build_inventory, inventory_hash, directory_identity,
                                                       safe_path)


def validate_record_scope(service, record):
    if record.get("record_version") != 2:
        raise ValueError("migration_legacy_evidence_required")
    if directory_identity(service.projects_root) != record["plan"]["root_identity"]:
        raise ValueError("migration_workspace_changed")
    # 路径恒由服务端固定根和操作身份派生；持久相对路径不能改变配置。
    expected = service.backup_root / record["operation_id"] / "project"
    if expected != service.workspace / record["backup_directory"]:
        raise ValueError("migration_backup_scope_mismatch")
    return (safe_path(service.projects_root / record["source_directory"]),
            safe_path(service.projects_root / record["target_directory"]), safe_path(expected))


def matches(record, root, projects_root):
    if not root.is_dir():
        return False
    return (read_project_metadata(projects_root, root)["id"] == record["project_id"]
            and directory_identity(root) == record["plan"]["source_identity"]
            and inventory_hash(build_inventory(root)) == record["plan"]["source_inventory_hash"])


def write_manifest(record, backup, inventory):
    path = safe_path(backup.parent / "manifest.json")
    data = {"schema_version": 1, "operation_id": record["operation_id"], "project_id": record["project_id"],
            "plan_fingerprint": record["plan_fingerprint"], "inventory": inventory}
    # 独占创建，不覆盖旧证据；部分写入失败也保留现场。
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def verified_backup(record, backup):
    path = safe_path(backup.parent / "manifest.json")
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or set(data) != {"schema_version", "operation_id", "project_id", "plan_fingerprint", "inventory"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or any(data[key] != record[key] for key in ("operation_id", "project_id", "plan_fingerprint"))
            or inventory_hash(data["inventory"]) != record["plan"]["source_inventory_hash"]
            or build_inventory(backup) != data["inventory"]):
        raise ValueError("migration_backup_mismatch")
    return data["inventory"]


def command_record_guard(service, record):
    """核对前验证原reservation；缺失只允许显式核对后按原意图补齐。"""
    stored = service.commands._store.read(record["original_request"]["idempotency_key"])
    if stored is not None and stored.fingerprint != record["command_fingerprint"]:
        raise ValueError("migration_command_evidence_conflict")
    if stored is not None and stored.result is not None:
        from creative_os.workspace_command import _encode_result
        if record["result_template"] != _encode_result(stored.result):
            raise ValueError("migration_command_evidence_conflict")
