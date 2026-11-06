"""工作区级目录迁移操作聚合，原子读写且不执行迁移动作。"""

import json
import os
from pathlib import Path
from uuid import uuid4


SCHEMA_VERSION = 2
STAGES = {"reserved", "backing_up", "backup_verified", "moving", "verified", "failed", "needs_reconciliation"}


class ProjectMigrationStore:
    def __init__(self, root, *, lock_attempts=100):
        self.root = Path(root).resolve()
        self.path = self.root / ".creative_os" / "directory-migrations.json"
        self.lock_path = self.path.with_suffix(".lock")
        self.lock_attempts = lock_attempts

    def read_operation(self, operation_id):
        return self._read().get(operation_id)

    def read_operations(self):
        """只读完整聚合，供写门禁核对旧路径和活动操作。"""
        return self._read()

    def write_operation(self, record):
        value = _validate_record(record)
        handle = self._lock()
        try:
            operations = self._read()
            existing = operations.get(value["operation_id"])
            immutable = ("project_id", "plan_fingerprint", "source_directory", "target_directory", "backup_directory")
            if existing is not None and existing.get("record_version") == 2:
                immutable += ("record_version", "actor", "plan", "original_request", "command_fingerprint", "trace_id")
                if value.get("record_version") != 2 or (existing["result_template"] is not None and existing["result_template"] != value.get("result_template")):
                    raise ValueError("migration_operation_conflict")
            if existing is not None and any(existing.get(key) != value[key] for key in immutable):
                raise ValueError("migration_operation_conflict")
            operations[value["operation_id"]] = value
            self._write(operations)
        finally:
            self._unlock(handle)

    def _read(self):
        if self.path.is_symlink() or self.path.resolve() != self.path.absolute():
            raise RuntimeError("migration_store_corrupt")
        if self.path.exists() and not self.path.is_file():
            raise RuntimeError("migration_store_corrupt")
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or set(raw) != {"schema_version", "operations"} or type(raw["schema_version"]) is not int or raw["schema_version"] not in {1, SCHEMA_VERSION} or not isinstance(raw.get("operations"), dict):
                raise ValueError
            operations = {}
            for key, value in raw["operations"].items():
                record = _validate_record(value)
                if key != record["operation_id"]:
                    raise ValueError("migration_operation_identity_mismatch")
                operations[key] = record
            return operations
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise RuntimeError("migration_store_corrupt") from error

    def _write(self, operations):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(f".{uuid4().hex}.tmp")
        with temp.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump({"schema_version": SCHEMA_VERSION, "operations": operations}, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.path)

    def _lock(self):
        from creative_os.project_write_gate import acquire_record_lease
        try:
            return acquire_record_lease(self.lock_path, self.lock_attempts)
        except ValueError as error:
            if str(error) == "record_store_busy":
                raise RuntimeError("migration_store_busy") from error
            raise

    def _unlock(self, handle):
        handle.__exit__(None, None, None)


def _validate_record(value):
    if not isinstance(value, dict):
        raise ValueError("migration_record_invalid")
    required = {"operation_id", "project_id", "plan_fingerprint", "source_directory", "target_directory", "backup_directory", "stage", "continuation_no", "reason"}
    allowed = required | {"actor"}
    if value.get("record_version") == 2:
        from creative_os.project_migration_schema import validate_evidence
        validate_evidence(value)
        allowed = set(value)
    if set(value) - allowed or not required.issubset(value):
        raise ValueError("migration_record_invalid")
    for key in ("operation_id", "project_id", "plan_fingerprint", "stage"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError("migration_record_invalid")
    if len(value["plan_fingerprint"]) != 64:
        raise ValueError("migration_record_invalid")
    if value["stage"] not in STAGES or type(value["continuation_no"]) is not int or value["continuation_no"] < 0:
        raise ValueError("migration_stage_invalid")
    for key in ("source_directory", "target_directory", "backup_directory"):
        _relative_path(value[key])
    return dict(value)


def _relative_path(value):
    if not isinstance(value, str) or not value.strip() or Path(value).is_absolute() or ":" in value:
        raise ValueError("migration_path_invalid")
    parts = value.replace("\\", "/").split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("migration_path_invalid")
    return value
