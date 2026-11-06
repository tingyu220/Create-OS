import json

import pytest

from creative_os.project_migration_command import ProjectMigrationCommand
from creative_os.web_command_dto import WebCommandValidationError, decode_web_command


@pytest.fixture
def local_project(tmp_path):
    project = tmp_path / "旧名"
    project.mkdir()
    (project / "project.json").write_text(json.dumps({"id": "book-1", "name": "新名"}), encoding="utf-8")
    return project


def test_reserve_is_idempotent_and_preserves_operation_identity(tmp_path, local_project):
    command = ProjectMigrationCommand(tmp_path)
    request = {"operation_id": "op-1", "project_id": "book-1", "plan_fingerprint": "f" * 64,
               "source_directory": "旧名", "target_directory": "新名"}
    first = command.reserve(request, actor="作者")
    duplicate = command.reserve(request, actor="作者")
    assert duplicate["operation_id"] == first["operation_id"]
    assert duplicate == first
    with pytest.raises(ValueError, match="migration_idempotency_conflict"):
        command.reserve({**request, "target_directory": "另一个"}, actor="作者")


def test_continuation_requires_next_number_and_never_reuses_old_number(tmp_path, local_project):
    command = ProjectMigrationCommand(tmp_path)
    command.reserve({"operation_id": "op-1", "project_id": "book-1", "plan_fingerprint": "f" * 64,
                    "source_directory": "旧名", "target_directory": "新名"}, actor="作者")
    assert command.continue_operation("op-1", 1)["continuation_no"] == 1
    with pytest.raises(ValueError, match="continuation_no_invalid"):
        command.continue_operation("op-1", 1)


def test_dto_allows_only_migration_commands_with_strict_targets():
    base = {"command_id": "migrate_project_directory", "request_id": "r1", "actor": "作者",
            "target": {"project_id": "book-1"}, "payload": {"operation_id": "12345678-1234-4234-8234-123456789abc", "plan_fingerprint": "f" * 64, "preview_token": "signed", "confirmed": True},
            "expected_version": None, "idempotency_key": "k1"}
    assert decode_web_command(base).command_id == "migrate_project_directory"
    with pytest.raises(WebCommandValidationError) as error:
        decode_web_command({**base, "target": {"project_id": "book-1", "path": "C:\\outside"}})
    assert error.value.code == "validation_failed"


@pytest.mark.parametrize("project_id,source_directory,error_code", [
    ("foreign-project", "旧名", "project_not_found"),
    ("book-1", "其他作品", "project_scope_mismatch"),
])
def test_reserve_rejects_project_outside_current_identity_mapping(tmp_path, local_project, project_id, source_directory, error_code):
    command = ProjectMigrationCommand(tmp_path)
    request = {"operation_id": "op-foreign", "project_id": project_id, "plan_fingerprint": "f" * 64,
               "source_directory": source_directory, "target_directory": "新名"}
    with pytest.raises(ValueError, match=error_code):
        command.reserve(request, actor="作者")
    assert not (tmp_path / ".creative_os").exists()


def test_original_reserve_replays_after_directory_rename_without_writing(tmp_path, local_project):
    request = {"operation_id": "op-1", "project_id": "book-1", "plan_fingerprint": "f" * 64,
               "source_directory": "旧名", "target_directory": "新名"}
    command = ProjectMigrationCommand(tmp_path)
    original = command.reserve(request, actor="作者")
    before = command.store.path.read_bytes()
    local_project.rename(tmp_path / "新名")
    restarted = ProjectMigrationCommand(tmp_path)
    assert restarted.reserve(request, actor="作者") == original
    assert restarted.store.path.read_bytes() == before


@pytest.mark.parametrize("field,value", [
    ("actor", "其他作者"), ("project_id", "foreign-project"),
    ("source_directory", "其他源"), ("target_directory", "其他目标"),
    ("plan_fingerprint", "a" * 64),
])
def test_changed_identity_cannot_replay_after_rename(tmp_path, local_project, field, value):
    request = {"operation_id": "op-1", "project_id": "book-1", "plan_fingerprint": "f" * 64,
               "source_directory": "旧名", "target_directory": "新名"}
    command = ProjectMigrationCommand(tmp_path)
    command.reserve(request, actor="作者")
    before = command.store.path.read_bytes()
    local_project.rename(tmp_path / "新名")
    changed = {**request, field: value} if field != "actor" else request
    with pytest.raises(ValueError, match="migration_idempotency_conflict"):
        command.reserve(changed, actor=value if field == "actor" else "作者")
    assert command.store.path.read_bytes() == before


def test_reserve_rejects_corrupt_aggregate_even_for_existing_operation(tmp_path, local_project):
    command = ProjectMigrationCommand(tmp_path)
    request = {"operation_id": "op-1", "project_id": "book-1", "plan_fingerprint": "f" * 64,
               "source_directory": "旧名", "target_directory": "新名"}
    command.reserve(request, actor="作者")
    raw = json.loads(command.store.path.read_text(encoding="utf-8"))
    raw["operations"]["wrong-key"] = raw["operations"].pop("op-1")
    command.store.path.write_text(json.dumps(raw), encoding="utf-8")
    before = command.store.path.read_bytes()
    with pytest.raises(RuntimeError, match="migration_store_corrupt"):
        command.reserve(request, actor="作者")
    assert command.store.path.read_bytes() == before
