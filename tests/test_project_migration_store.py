import json

import pytest

from creative_os.project_migration_store import ProjectMigrationStore


def record(operation_id="op-1", stage="reserved"):
    return {"operation_id": operation_id, "project_id": "book-1", "plan_fingerprint": "f" * 64,
            "source_directory": "旧名", "target_directory": "新名",
            "backup_directory": ".backup/project-directory-migrations/op-1/project",
            "stage": stage, "continuation_no": 0, "reason": None}


def test_store_round_trip_and_corrupt_aggregate_rejected(tmp_path):
    store = ProjectMigrationStore(tmp_path)
    store.write_operation(record())
    assert store.read_operation("op-1")["stage"] == "reserved"
    aggregate = tmp_path / ".creative_os" / "directory-migrations.json"
    aggregate.write_text(json.dumps({"schema_version": 1, "operations": {"op-1": {"stage": "unknown"}}}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="migration_store_corrupt"):
        store.read_operation("op-1")


def test_store_rejects_absolute_or_outside_paths(tmp_path):
    store = ProjectMigrationStore(tmp_path)
    value = record()
    value["source_directory"] = "..\\outside"
    with pytest.raises(ValueError, match="migration_path_invalid"):
        store.write_operation(value)


def test_store_updates_are_read_modify_write_without_losing_operations(tmp_path):
    store = ProjectMigrationStore(tmp_path)
    store.write_operation(record("a"))
    store.write_operation(record("b"))
    assert store.read_operation("a") is not None
    assert store.read_operation("b") is not None


def test_store_rejects_aggregate_key_different_from_operation_id(tmp_path):
    store = ProjectMigrationStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text(json.dumps({"schema_version": 1, "operations": {"wrong-key": record("op-real")}}), encoding="utf-8")
    before = store.path.read_bytes()
    with pytest.raises(RuntimeError, match="migration_store_corrupt"):
        store.read_operation("wrong-key")
    with pytest.raises(RuntimeError, match="migration_store_corrupt"):
        store.write_operation(record("new-operation"))
    assert store.path.read_bytes() == before
