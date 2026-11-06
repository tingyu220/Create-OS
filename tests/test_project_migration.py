"""目录迁移服务的真实临时文件验证；不创建创作Runtime。"""

import json
import os
from pathlib import Path
from uuid import UUID

import pytest

from creative_os.project_directory_inventory import build_inventory, inventory_hash, rename_no_replace
from creative_os.project_migration import ProjectMigrationService
from creative_os.project_registry import ProjectRegistry
from creative_os.workspace_command import CommandRequest
from creative_os.project_write_gate import migration_lease


def seed(workspace):
    projects = workspace / "projects"
    source = projects / "technical_book"
    source.mkdir(parents=True)
    (source / "project.json").write_text(json.dumps({"id": "stable-book", "name": "中文故事"}, ensure_ascii=False), encoding="utf-8")
    (source / "hidden" / "empty").mkdir(parents=True)
    (source / ".hidden").write_bytes(b"hidden\x00bytes")
    (source / "chapter.md").write_text("不改稿件内容\n", encoding="utf-8")
    return projects, source, workspace / ".backup/project-directory-migrations"


def service_for(workspace, **kwargs):
    projects, source, backup = seed(workspace)
    return ProjectMigrationService(projects, backup, ProjectRegistry(projects), **kwargs), source


def start_request(preview, key=None):
    return CommandRequest("migrate_project_directory", "start", "作者", {"project_id": "stable-book"},
                          {"operation_id": preview["operation_id"], "plan_fingerprint": preview["plan_fingerprint"],
                           "preview_token": preview["preview_token"], "confirmed": True},
                          idempotency_key=key or "directory-migrate:" + preview["operation_id"])


def snapshot(root):
    return {str(p.relative_to(root)): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
            for p in root.rglob("*")}


def test_preview_is_uuid_readonly_and_inventory_is_stable(tmp_path):
    service, source = service_for(tmp_path)
    before = snapshot(tmp_path)
    first, second = service.preview("stable-book"), service.preview("stable-book")
    assert str(UUID(first["operation_id"])) == first["operation_id"]
    assert first["operation_id"] != second["operation_id"]
    assert first["plan_fingerprint"] == second["plan_fingerprint"]
    assert first["file_count"] == 3 and first["directory_count"] == 2
    assert snapshot(tmp_path) == before


@pytest.mark.skipif(os.name != "nt", reason="本首版原子拒绝覆盖移动仅支持Windows")
def test_migrate_full_backup_and_replay_without_second_move(tmp_path):
    service, source = service_for(tmp_path, default_project_id="stable-book", default_root=tmp_path / "projects/technical_book")
    original = build_inventory(source)
    preview = service.preview("stable-book")
    request = start_request(preview)
    result = service.commands.execute(request)
    assert result.status == "accepted", result.error
    target = source.parent / "中文故事"
    backup = service.backup_root / preview["operation_id"] / "project"
    assert not source.exists()
    assert build_inventory(target) == build_inventory(backup) == original
    record = service.operations.read_operation(preview["operation_id"])
    assert record["stage"] == "verified" and record["backup_verified"]
    assert service.status(preview["operation_id"])["reload_required"]
    before = snapshot(tmp_path)
    restored = ProjectMigrationService(service.projects_root, service.backup_root, ProjectRegistry(service.projects_root))
    assert restored.commands.execute(request) == result
    assert snapshot(tmp_path) == before
    assert len(list(service.backup_root.iterdir())) == 1


@pytest.mark.parametrize("change", ["content", "metadata", "source_identity", "target"])
def test_changed_preview_refuses_before_intent_or_backup(tmp_path, change):
    service, source = service_for(tmp_path)
    request = start_request(service.preview("stable-book"))
    if change == "content":
        (source / "chapter.md").write_text("已编辑", encoding="utf-8")
    elif change == "metadata":
        (source / "project.json").write_text(json.dumps({"id": "stable-book", "name": "另一书名"}), encoding="utf-8")
    elif change == "source_identity":
        import shutil
        source.rename(source.parent / "parked")
        shutil.copytree(source.parent / "parked", source)
        (source.parent / "parked/project.json").rename(source.parent / "parked/project.saved")
    else:
        (source.parent / "中文故事").mkdir()
    result = service.commands.execute(request)
    assert result.status == "rejected"
    assert not service.backup_root.exists()
    assert service.operations.read_operations() == {}


def test_atomic_move_refuses_target_created_before_call(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "original").write_text("source", encoding="utf-8")
    (target / "sentinel").write_text("target", encoding="utf-8")
    with pytest.raises((OSError, ValueError)):
        rename_no_replace(source, target)
    assert (source / "original").read_text() == "source"
    assert (target / "sentinel").read_text() == "target"
    assert not (target / "source").exists()


def test_hardlinked_file_is_rejected(tmp_path):
    service, source = service_for(tmp_path)
    os.link(source / "chapter.md", source / "alias.md")
    with pytest.raises(ValueError, match="project_link_unsafe"):
        service.preview("stable-book")


def test_unsafe_confirmation_and_client_paths_are_rejected(tmp_path):
    service, source = service_for(tmp_path)
    from dataclasses import replace
    request = start_request(service.preview("stable-book"))
    for payload in ({**request.payload, "confirmed": 1}, {**request.payload, "source_directory": "elsewhere"}):
        result = service.commands.execute(replace(request, payload=payload))
        assert result.status == "rejected"
    assert service.operations.read_operations() == {}
    assert not service.backup_root.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows原子拒绝覆盖原语")
def test_target_appearing_at_last_moment_is_never_overwritten(tmp_path, monkeypatch):
    service, source = service_for(tmp_path)
    original = build_inventory(source)
    preview = service.preview("stable-book")
    target = source.parent / "中文故事"
    import creative_os.project_migration as migration
    def competitor(point, _record):
        if point == "before_rename":
            target.mkdir()
            (target / "sentinel").write_text("竞争目标", encoding="utf-8")
    monkeypatch.setattr(migration, "checkpoint", competitor)
    result = service.commands.execute(start_request(preview))
    assert result.error.code == "command_outcome_unknown"
    assert build_inventory(source) == original
    assert (target / "sentinel").read_text(encoding="utf-8") == "竞争目标"
    assert not (target / source.name).exists()
    assert service.status(preview["operation_id"])["stage"] == "needs_reconciliation"


@pytest.mark.parametrize("failure", ["copy", "verification", "rename"])
def test_io_failures_preserve_source_and_partial_backup(tmp_path, monkeypatch, failure):
    service, source = service_for(tmp_path)
    preview = service.preview("stable-book")
    original = build_inventory(source)
    import creative_os.project_migration as migration
    if failure == "copy":
        def copy_failure(_source, backup, _inventory):
            backup.mkdir()
            (backup / "partial").write_bytes(b"partial")
            raise OSError("copy failed")
        monkeypatch.setattr(migration, "copy_verified", copy_failure)
    elif failure == "verification":
        monkeypatch.setattr(migration, "verified_backup", lambda *_a: (_ for _ in ()).throw(ValueError("mismatch")))
    else:
        monkeypatch.setattr(migration, "rename_no_replace", lambda *_a: (_ for _ in ()).throw(PermissionError("Windows handle busy")))
    result = service.commands.execute(start_request(preview))
    assert result.error.code == "command_outcome_unknown"
    assert build_inventory(source) == original
    assert not (source.parent / "中文故事").exists()
    backup = service.backup_root / preview["operation_id"] / "project"
    assert backup.exists()
    assert service.status(preview["operation_id"])["stage"] == "needs_reconciliation"


def test_version_one_records_survive_version_two_writes_without_get_changes(tmp_path):
    from test_project_migration_store import record
    service, source = service_for(tmp_path)
    legacy = record()
    service.operations.path.parent.mkdir(parents=True)
    service.operations.path.write_text(json.dumps({"schema_version": 1, "operations": {"op-1": legacy}}), encoding="utf-8")
    before = service.operations.path.read_bytes()
    assert service.operations.read_operation("op-1") == legacy
    assert service.operations.path.read_bytes() == before
    value = service.preview("stable-book")
    request = start_request(value)
    with migration_lease(service.projects_root, "stable-book"):
        service.prepare(request)
    raw = json.loads(service.operations.path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 2
    assert raw["operations"]["op-1"] == legacy


@pytest.mark.parametrize("field", ["backup_directory", "source_directory", "plan", "result_template", "backup_verified"])
def test_tampered_evidence_cannot_authorize_writes(tmp_path, field):
    service, source = service_for(tmp_path)
    preview = service.preview("stable-book")
    request = start_request(preview)
    with migration_lease(service.projects_root, "stable-book"):
        service.prepare(request)
    raw = json.loads(service.operations.path.read_text(encoding="utf-8"))
    value = raw["operations"][preview["operation_id"]]
    if field == "backup_directory":
        value[field] = ".backup/project-directory-migrations/elsewhere/project"
    elif field == "source_directory":
        value[field] = "../outside"
    elif field == "plan":
        value[field]["source_inventory_hash"] = "a" * 64
    elif field == "result_template":
        value[field] = {}
    else:
        value["stage"] = "moving"
        value["backup_verified"] = False
    service.operations.path.write_text(json.dumps(raw), encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(RuntimeError, match="migration_store_corrupt"):
        service.status(preview["operation_id"])
    assert service.commands.execute(request).status != "accepted"
    assert snapshot(tmp_path) == before


def test_direct_handler_cannot_bypass_command_boundary(tmp_path):
    service, source = service_for(tmp_path)
    request = start_request(service.preview("stable-book"))
    with migration_lease(service.projects_root, "stable-book"):
        service.prepare(request)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="migration_command_ownership_required"):
        service.execute(request, "client-trace")
    assert snapshot(tmp_path) == before


@pytest.mark.skipif(os.name != "nt", reason="Windows完整移动验证")
def test_cached_future_and_invalidation_are_checked_inside_same_lease(tmp_path):
    from concurrent.futures import Future
    from threading import Lock
    from types import SimpleNamespace, MethodType
    from creative_os.agent_runtime import WriterAgentRuntime
    from creative_os.project_write_gate import assert_operation_lease
    service, source = service_for(tmp_path, default_project_id="stable-book", default_root=tmp_path / "projects/technical_book")
    future = Future()
    class FakePool:
        closed = False
        def shutdown(self, *, wait):
            assert wait is False
            assert_operation_lease(service.projects_root, "stable-book")
            self.closed = True
    cached = SimpleNamespace(root=source, project_id="stable-book", _jobs={}, _futures={"job": future}, _lock=Lock(), _pool=FakePool())
    cached.assert_migration_idle = MethodType(WriterAgentRuntime.assert_migration_idle, cached)
    service.registry.register("stable-book", {"agent_runtime": cached})
    preview = service.preview("stable-book")
    request = start_request(preview)
    assert service.commands.execute(request).error.code == "project_migration_active"
    assert service.operations.read_operations() == {}
    assert not service.backup_root.exists()
    assert not cached._pool.closed
    future.set_result(None)
    assert service.commands.execute(request).status == "accepted"
    assert cached._pool.closed and not service.registry._entries
    assert service.availability("stable-book", source)["http_status"] == 503
    assert service.availability("stable-book", source, writable=True)["http_status"] == 409
    assert service.availability("stable-book", source.parent / "中文故事")["available"]


def test_preview_expiry_and_service_restart_invalidate_unexecuted_tokens(tmp_path):
    service, source = service_for(tmp_path)
    service.previews.ttl = -1
    request = start_request(service.preview("stable-book"))
    assert service.commands.execute(request).error.code == "preview_token_invalid"
    service.previews.ttl = 600
    request = start_request(service.preview("stable-book"))
    restored = ProjectMigrationService(service.projects_root, service.backup_root, ProjectRegistry(service.projects_root))
    assert restored.commands.execute(request).error.code == "preview_token_invalid"
    assert service.operations.read_operations() == {}


def test_unsupported_chinese_nickname_and_target_name_are_not_executable(tmp_path):
    service, source = service_for(tmp_path)
    source.rename(source.parent / "简称")
    preview = service.preview("stable-book")
    assert not preview["available"]
    assert service.commands.execute(start_request(preview)).status == "rejected"
    assert service.operations.read_operations() == {}


@pytest.mark.skipif(os.name != "nt", reason="Windows junction")
def test_junction_is_rejected_before_preview_or_backup(tmp_path):
    import _winapi
    service, source = service_for(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private").write_bytes(b"not-a-project-file")
    _winapi.CreateJunction(str(outside), str(source / "junction"))
    with pytest.raises(ValueError, match="project_link_unsafe"):
        service.preview("stable-book")
    assert not service.backup_root.exists()
    assert (outside / "private").read_bytes() == b"not-a-project-file"


def test_invalid_operation_uuid_returns_stable_error_without_writes(tmp_path):
    from dataclasses import replace
    service, source = service_for(tmp_path)
    request = start_request(service.preview("stable-book"))
    request = replace(request, payload={**request.payload, "operation_id": "not-a-uuid"}, idempotency_key="directory-migrate:not-a-uuid")
    before = snapshot(tmp_path)
    assert service.commands.execute(request).error.code == "migration_operation_id_invalid"
    assert snapshot(tmp_path) == before
