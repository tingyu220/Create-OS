"""迁移证据的原子写入不得借旧临时文件改写其他数据。"""

import os
import pytest

from creative_os.project_migration_store import ProjectMigrationStore
from creative_os.workspace_command import FileCommandResultStore
from test_project_migration_store import record


@pytest.mark.parametrize("kind", ["operation", "command"])
def test_preexisting_temp_hardlink_is_never_truncated(tmp_path, kind):
    root = tmp_path / "projects"
    root.mkdir()
    store = ProjectMigrationStore(root) if kind == "operation" else FileCommandResultStore(root)
    store.path.parent.mkdir(parents=True)
    sentinel = tmp_path / "outside-evidence"
    sentinel.write_bytes(b"must-stay-unchanged")
    trap = store.path.with_suffix(".tmp")
    os.link(sentinel, trap)
    if kind == "operation":
        store.write_operation(record())
    else:
        store.reserve("key", "fingerprint")
    assert sentinel.read_bytes() == b"must-stay-unchanged"
    assert trap.read_bytes() == b"must-stay-unchanged"


@pytest.mark.parametrize("kind", ["operation", "command"])
@pytest.mark.parametrize("window", ["before", "after"])
def test_process_exit_during_atomic_replace_does_not_leave_a_phantom_owner(tmp_path, kind, window):
    import subprocess
    import sys
    root = tmp_path / "projects"
    root.mkdir()
    script = '''
import os, sys
from pathlib import Path
from scripts.fake_validation_guard import fake_validation_guard
with fake_validation_guard():
    from creative_os.project_migration_store import ProjectMigrationStore
    from creative_os.workspace_command import FileCommandResultStore
    store = ProjectMigrationStore(sys.argv[1]) if sys.argv[2] == "operation" else FileCommandResultStore(sys.argv[1])
    replace = os.replace
    def crash(src, dst):
        if Path(dst) == store.path and sys.argv[3] == "before":
            os._exit(74)
        replace(src, dst)
        if Path(dst) == store.path and sys.argv[3] == "after":
            os._exit(74)
    os.replace = crash
    if sys.argv[2] == "operation":
        store.write_operation({"operation_id":"first", "project_id":"p", "plan_fingerprint":"f"*64,
            "source_directory":"old", "target_directory":"new", "backup_directory":".backup/first/project",
            "stage":"reserved", "continuation_no":0, "reason":None})
    else:
        store.reserve("first", "f")
'''
    result = subprocess.run([sys.executable, "-c", script, str(root), kind, window], capture_output=True, text=True, timeout=20)
    assert result.returncode == 74, result.stderr
    if kind == "operation":
        store = ProjectMigrationStore(root)
        assert (store.read_operation("first") is None) == (window == "before")
        store.write_operation(record("second"))
        assert store.read_operation("second") is not None
    else:
        store = FileCommandResultStore(root)
        assert (store.read("first") is None) == (window == "before")
        assert store.reserve("second", "s").status == "acquired"
