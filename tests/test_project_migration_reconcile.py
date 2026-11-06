"""持久化中断矩阵：只显式核对和再次确认，GET不恢复。"""

from dataclasses import replace
import os

import pytest

from creative_os.project_directory_inventory import build_inventory
from creative_os.project_migration import ProjectMigrationService
from creative_os.project_registry import ProjectRegistry
from creative_os.workspace_command import CommandRequest
from test_project_migration import service_for, start_request, snapshot


class SimulatedCrash(BaseException):
    pass


def reconcile_request(preview, number="check"):
    op = preview["operation_id"]
    return CommandRequest("reconcile_project_directory", number, "作者", {"project_id": "stable-book", "operation_id": op},
                          {"plan_fingerprint": preview["plan_fingerprint"]}, idempotency_key=f"directory-reconcile:{op}:{number}")


def continue_request(preview, no):
    op = preview["operation_id"]
    return CommandRequest("continue_project_directory", "continue", "作者", {"project_id": "stable-book", "operation_id": op},
                          {"plan_fingerprint": preview["plan_fingerprint"], "continuation_no": no, "confirmed": True},
                          idempotency_key=f"directory-continue:{op}:{no}")


WINDOWS = ["before_intent", "after_intent", "before_command_reserve", "after_command_reserve",
           "before_backing_up", "after_backing_up", "before_backup_verified", "after_backup_verified",
           "before_moving", "after_moving", "before_rename", "after_rename",
           "before_verified", "after_verified", "before_command_complete", "after_command_complete"]


@pytest.mark.skipif(os.name != "nt", reason="本首版原子拒绝覆盖移动仅支持Windows")
@pytest.mark.parametrize("window", WINDOWS)
def test_crash_windows_require_explicit_reconcile_and_preserve_files(tmp_path, monkeypatch, window):
    service, source = service_for(tmp_path)
    original = build_inventory(source)
    preview = service.preview("stable-book")
    request = start_request(preview)
    import creative_os.project_migration as migration
    def crash(point, _record):
        if point == window:
            raise SimulatedCrash(point)
    with monkeypatch.context() as fault:
        fault.setattr(migration, "checkpoint", crash)
        with pytest.raises(SimulatedCrash):
            service.commands.execute(request)
    restored = ProjectMigrationService(service.projects_root, service.backup_root, ProjectRegistry(service.projects_root))
    before = snapshot(tmp_path)
    status = restored.status(preview["operation_id"])
    assert snapshot(tmp_path) == before
    if window == "before_intent":
        assert status is None
        assert build_inventory(source) == original
        return
    replay = restored.commands.execute(request)
    assert replay.status in {"accepted", "failed"}
    assert snapshot(tmp_path) == before
    checked = restored.commands.execute(reconcile_request(preview))
    status = restored.status(preview["operation_id"])
    if status["stage"] == "backup_verified":
        assert checked.status != "accepted"
        no = status["continuation_no"]
        result = restored.commands.execute(continue_request(preview, no))
        assert result.status == "accepted", result.error
        assert restored.commands.execute(continue_request(preview, no)) == result
    elif status["stage"] == "failed":
        assert build_inventory(source) == original
        assert not (source.parent / "中文故事").exists()
        return
    else:
        assert status["stage"] == "verified", status
    target = source.parent / "中文故事"
    backup = restored.backup_root / preview["operation_id"] / "project"
    assert build_inventory(target) == build_inventory(backup) == original
    assert not source.exists()
    final = restored.commands.execute(request)
    assert final.status == "accepted"
    assert final.trace_id == restored.operations.read_operation(preview["operation_id"])["trace_id"]
    assert len(list(restored.backup_root.iterdir())) == 1


def interrupted(service, preview, monkeypatch, point="after_moving"):
    import creative_os.project_migration as migration
    def crash(window, _record):
        if window == point:
            raise SimulatedCrash(window)
    with monkeypatch.context() as fault:
        fault.setattr(migration, "checkpoint", crash)
        with pytest.raises(SimulatedCrash):
            service.commands.execute(start_request(preview))


@pytest.mark.parametrize("case", ["both", "neither", "bad_backup", "changed_source", "bad_metadata"])
def test_ambiguous_evidence_is_not_repaired_or_moved(tmp_path, monkeypatch, case):
    service, source = service_for(tmp_path)
    preview = service.preview("stable-book")
    interrupted(service, preview, monkeypatch)
    if case == "both":
        import shutil
        shutil.copytree(source, source.parent / "中文故事")
    elif case == "neither":
        source.rename(source.parent / "parked")
    elif case == "bad_backup":
        (service.backup_root / preview["operation_id"] / "project/chapter.md").write_text("备份变化", encoding="utf-8")
    elif case == "changed_source":
        (source / "chapter.md").write_text("源变化", encoding="utf-8")
    else:
        (source / "project.json").write_text("bad-json", encoding="utf-8")
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
              and ".creative_os/directory-migrations" not in p.as_posix() and "/commands/" not in p.as_posix()}
    result = service.commands.execute(reconcile_request(preview))
    assert result.status != "accepted"
    assert service.status(preview["operation_id"])["stage"] == "needs_reconciliation"
    assert {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
            and ".creative_os/directory-migrations" not in p.as_posix() and "/commands/" not in p.as_posix()} == before


def test_continue_without_reconcile_or_changed_identity_cannot_move(tmp_path, monkeypatch):
    service, source = service_for(tmp_path)
    preview = service.preview("stable-book")
    interrupted(service, preview, monkeypatch)
    assert service.commands.execute(continue_request(preview, 1)).status != "accepted"
    assert source.exists()
    assert not (source.parent / "中文故事").exists()
    for request in [replace(reconcile_request(preview, "actor"), actor="其他作者"),
                    replace(reconcile_request(preview, "project"), target={"project_id": "foreign", "operation_id": preview["operation_id"]}),
                    replace(reconcile_request(preview, "hash"), payload={"plan_fingerprint": "a" * 64})]:
        before = snapshot(tmp_path)
        assert service.commands.execute(request).status == "rejected"
        assert snapshot(tmp_path) == before


@pytest.mark.skipif(os.name != "nt", reason="Windows真实进程中断")
@pytest.mark.parametrize("window", ["after_moving", "after_rename"])
def test_process_exit_releases_external_locks_but_does_not_auto_resume(tmp_path, window):
    import json
    import subprocess
    import sys
    service, source = service_for(tmp_path)
    original = build_inventory(source)
    script = '''
import json, os, sys
from scripts.fake_validation_guard import fake_validation_guard
with fake_validation_guard():
    from creative_os.project_migration import ProjectMigrationService
    from creative_os.project_registry import ProjectRegistry
    from creative_os.workspace_command import CommandRequest
    import creative_os.project_migration as migration
    service = ProjectMigrationService(sys.argv[1], sys.argv[2], ProjectRegistry(sys.argv[1]))
    preview = service.preview("stable-book")
    print(json.dumps(preview), flush=True)
    def stop(point, record):
        if point == sys.argv[3]:
            os._exit(73)
    migration.checkpoint = stop
    service.commands.execute(CommandRequest("migrate_project_directory", "start", "作者", {"project_id":"stable-book"},
        {"operation_id":preview["operation_id"], "plan_fingerprint":preview["plan_fingerprint"],
         "preview_token":preview["preview_token"], "confirmed":True}, idempotency_key="directory-migrate:"+preview["operation_id"]))
'''
    process = subprocess.run([sys.executable, "-c", script, str(service.projects_root), str(service.backup_root), window],
                             capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert process.returncode == 73, process.stderr
    preview = json.loads(process.stdout)
    restored = ProjectMigrationService(service.projects_root, service.backup_root, ProjectRegistry(service.projects_root))
    before = snapshot(tmp_path)
    assert restored.status(preview["operation_id"])["needs_reconciliation"]
    assert restored.commands.execute(start_request(preview)).error.code == "command_outcome_unknown"
    assert snapshot(tmp_path) == before
    restored.commands.execute(reconcile_request(preview))
    status = restored.status(preview["operation_id"])
    if status["stage"] == "backup_verified":
        assert restored.commands.execute(continue_request(preview, status["continuation_no"])).status == "accepted"
    assert build_inventory(source.parent / "中文故事") == original
    assert not source.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows继续移动中断")
@pytest.mark.parametrize("window", ["after_command_reserve", "after_moving", "after_rename", "before_command_complete", "after_command_complete"])
def test_continuation_crash_requires_another_explicit_reconcile(tmp_path, monkeypatch, window):
    service, source = service_for(tmp_path)
    original = build_inventory(source)
    preview = service.preview("stable-book")
    interrupted(service, preview, monkeypatch)
    service.commands.execute(reconcile_request(preview))
    first_no = service.status(preview["operation_id"])["continuation_no"]
    import creative_os.project_migration as migration
    def crash(point, _record):
        if point == window:
            raise SimulatedCrash(point)
    with monkeypatch.context() as fault:
        fault.setattr(migration, "checkpoint", crash)
        with pytest.raises(SimulatedCrash):
            service.commands.execute(continue_request(preview, first_no))
    restored = ProjectMigrationService(service.projects_root, service.backup_root, ProjectRegistry(service.projects_root))
    before = snapshot(tmp_path)
    restored.commands.execute(continue_request(preview, first_no))
    assert snapshot(tmp_path) == before
    restored.commands.execute(reconcile_request(preview, "check-again"))
    status = restored.status(preview["operation_id"])
    if status["stage"] == "backup_verified":
        no = status["continuation_no"]
        # reserve之后、消费编号之前中断，明确再核对可复用同一未消费编号，
        # 但其旧命令仍RESERVED，必须发出新的继续编号才能执行。
        assert no > first_no
        assert restored.commands.execute(continue_request(preview, no)).status == "accepted"
    assert build_inventory(source.parent / "中文故事") == original


@pytest.mark.parametrize("window", ["after_command_reserve", "before_backup_verified", "after_backup_verified"])
def test_reconcile_crash_does_not_automatically_replay_handler(tmp_path, monkeypatch, window):
    service, source = service_for(tmp_path)
    preview = service.preview("stable-book")
    interrupted(service, preview, monkeypatch)
    import creative_os.project_migration as migration
    def crash(point, _record):
        if point == window:
            raise SimulatedCrash(point)
    with monkeypatch.context() as fault:
        fault.setattr(migration, "checkpoint", crash)
        with pytest.raises(SimulatedCrash):
            service.commands.execute(reconcile_request(preview))
    restored = ProjectMigrationService(service.projects_root, service.backup_root, ProjectRegistry(service.projects_root))
    before = snapshot(tmp_path)
    assert restored.commands.execute(reconcile_request(preview)).error.code == "command_outcome_unknown"
    assert snapshot(tmp_path) == before
    restored.commands.execute(reconcile_request(preview, "new-explicit-check"))
    assert "continue" in restored.status(preview["operation_id"])["actions"]
    assert source.exists()


@pytest.mark.parametrize("window", ["before_failed", "after_failed"])
def test_failed_record_checkpoint_recovery_preserves_partial_evidence(tmp_path, monkeypatch, window):
    service, source = service_for(tmp_path)
    preview = service.preview("stable-book")
    original = build_inventory(source)
    interrupted(service, preview, monkeypatch, "after_backing_up")
    import creative_os.project_migration as migration
    def crash(point, _record):
        if point == window:
            raise SimulatedCrash(point)
    with monkeypatch.context() as fault:
        fault.setattr(migration, "checkpoint", crash)
        with pytest.raises(SimulatedCrash):
            service.commands.execute(reconcile_request(preview))
    restored = ProjectMigrationService(service.projects_root, service.backup_root, ProjectRegistry(service.projects_root))
    restored.commands.execute(reconcile_request(preview, "explicit-again"))
    assert restored.status(preview["operation_id"])["stage"] == "failed"
    assert restored.commands.execute(start_request(preview)).error.code == "migration_failed"
    assert build_inventory(source) == original


@pytest.mark.skipif(os.name != "nt", reason="Windows目录竞争")
@pytest.mark.parametrize("window", ["before_needs_reconciliation", "after_needs_reconciliation"])
def test_unknown_record_checkpoint_never_overwrites_competing_target(tmp_path, monkeypatch, window):
    service, source = service_for(tmp_path)
    preview = service.preview("stable-book")
    original = build_inventory(source)
    target = source.parent / "中文故事"
    import creative_os.project_migration as migration
    def crash(point, _record):
        if point == "before_rename":
            target.mkdir()
            (target / "sentinel").write_bytes(b"competitor")
        if point == window:
            raise SimulatedCrash(point)
    with monkeypatch.context() as fault:
        fault.setattr(migration, "checkpoint", crash)
        with pytest.raises(SimulatedCrash):
            service.commands.execute(start_request(preview))
    restored = ProjectMigrationService(service.projects_root, service.backup_root, ProjectRegistry(service.projects_root))
    restored.commands.execute(reconcile_request(preview))
    assert restored.status(preview["operation_id"])["stage"] == "needs_reconciliation"
    assert build_inventory(source) == original
    assert (target / "sentinel").read_bytes() == b"competitor"


@pytest.mark.skipif(os.name != "nt", reason="Windows失败后重新预览")
def test_partial_backup_is_preserved_when_explicitly_failed_then_new_operation_runs(tmp_path, monkeypatch):
    service, source = service_for(tmp_path)
    preview = service.preview("stable-book")
    import creative_os.project_migration as migration
    def fail_copy(_source, backup, _inventory):
        backup.mkdir()
        (backup / "partial").write_bytes(b"preserve-me")
        raise OSError("interrupted copy")
    with monkeypatch.context() as fault:
        fault.setattr(migration, "copy_verified", fail_copy)
        assert service.commands.execute(start_request(preview)).error.code == "command_outcome_unknown"
    service.commands.execute(reconcile_request(preview))
    assert service.status(preview["operation_id"])["stage"] == "failed"
    old_backup = service.backup_root / preview["operation_id"] / "project/partial"
    assert old_backup.read_bytes() == b"preserve-me"
    fresh = service.preview("stable-book")
    assert fresh["operation_id"] != preview["operation_id"]
    assert service.commands.execute(start_request(fresh)).status == "accepted"
    assert old_backup.read_bytes() == b"preserve-me"
    assert len(list(service.backup_root.iterdir())) == 2
