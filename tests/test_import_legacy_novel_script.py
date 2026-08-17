import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "import_legacy_novel.py"


def _run(*args: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_materialize_refuses_unresolved_high_conflicts(tmp_path):
    source = tmp_path / "source"
    _write(source / "04_Chapters/第1章.md", "# 第1章：开端\n正文")
    _write(source / "核心框架.md", "全书规划4卷。")
    _write(source / "02_Plot/第一卷.md", "重构为5卷。")
    projects = tmp_path / "projects"

    assert _run("scan", "--source", str(source), "--projects-root", str(projects), "--title", "文明升阶").returncode == 0
    project = projects / "文明升阶"
    assert _run("report", "--project-root", str(project)).returncode == 0

    result = _run("materialize", "--project-root", str(project))

    assert result.returncode != 0
    assert not (project / "production/final_chapters/chapter_001.md").exists()


def test_materialize_copies_approved_canon_and_keeps_source_unchanged(tmp_path):
    source = tmp_path / "source"
    _write(source / "04_Chapters/第1章.md", "# 第1章：开端\n正文")
    before = _snapshot(source)
    projects = tmp_path / "projects"

    assert _run("scan", "--source", str(source), "--projects-root", str(projects), "--title", "文明升阶").returncode == 0
    project = projects / "文明升阶"
    assert _run("report", "--project-root", str(project)).returncode == 0
    decisions = project / ".creative_os/import/decisions.json"
    decisions.write_text(json.dumps({"accepted_canon_paths": ["04_Chapters/第1章.md"], "resolutions": {}}, ensure_ascii=False), encoding="utf-8")
    assert _run("approve", "--project-root", str(project), "--actor", "tingyu", "--decisions", str(decisions)).returncode == 0

    result = _run("materialize", "--project-root", str(project))

    assert result.returncode == 0
    assert (project / "production/final_chapters/chapter_001.md").exists()
    assert (project / ".creative_os/knowledge/imported_active.json").exists()
    assert _snapshot(source) == before
