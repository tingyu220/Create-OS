"""两本既有作品的受控迁移脚本：临时目录验证先备份再移动。"""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from test_project_directory_identity import seed, snapshot

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/migrate_named_projects.ps1"


def prepare(tmp_path):
    projects = tmp_path / "projects"
    roots = [seed(projects, "validation_novel", "novel-validation-001"),
             seed(projects, "novel_domain_validation", "novel-domain-validation")]
    (roots[0] / "空目录").mkdir()
    return projects, roots, tmp_path / "backup"


def run(projects, backup):
    powershell = os.environ.get("TASK_PWSH") or shutil.which("pwsh.exe") or shutil.which("pwsh")
    assert powershell, "需要动态解析的PowerShell 7+"
    return subprocess.run([powershell, "-NoProfile", "-File", str(SCRIPT), "-ProjectsRoot", str(projects), "-BackupRoot", str(backup)],
                          capture_output=True, text=True, encoding="utf-8", timeout=30)


def test_verified_backup_and_whole_directory_move_preserve_all_files(tmp_path):
    projects, roots, backup = prepare(tmp_path)
    before = [snapshot(root) for root in roots]
    result = run(projects, backup)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["Status"] == "verified" and len(report["Projects"]) == 2
    for index, (old, new) in enumerate(zip(roots, (projects / "雾城回声", projects / "末班钟表店"))):
        assert not old.exists() and snapshot(new) == before[index]
        saved = backup / old.name
        assert {name: data[1] for name, data in snapshot(saved).items()} == {name: data[1] for name, data in before[index].items()}
        assert (backup / (old.name + ".manifest.json")).is_file()


@pytest.mark.parametrize("case", ["occupied", "active", "identity"])
def test_unsafe_migration_is_rejected_before_backup_or_move(tmp_path, case):
    projects, roots, backup = prepare(tmp_path)
    if case == "occupied":
        (projects / "末班钟表店").mkdir()
    elif case == "active":
        path = roots[1] / ".creative_os/agent/conversations/chapter_001.json"
        path.parent.mkdir(parents=True); path.write_text(json.dumps({"jobs": {"active": {"status": "running"}}}), encoding="utf-8")
    else:
        (roots[1] / "project.json").write_text('{"id":"foreign"}', encoding="utf-8")
    before = snapshot(projects)
    result = run(projects, backup)
    assert result.returncode != 0
    assert snapshot(projects) == before and not backup.exists()
