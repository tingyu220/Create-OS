import json
from pathlib import Path

import pytest

from creative_os.project_directory_inventory import build_inventory, inventory_hash
from creative_os.project_migration_preview import DirectoryMigrationPreview


def make_project(root, directory="validation_novel", project_id="novel-1", title="中文书"):
    path = Path(root) / directory
    path.mkdir(parents=True)
    (path / "project.json").write_text(json.dumps({"id": project_id, "name": title}, ensure_ascii=False), encoding="utf-8")
    (path / "empty").mkdir()
    (path / "chapter.md").write_text("hello", encoding="utf-8")
    return path


def test_inventory_is_stable_and_includes_empty_directories(tmp_path):
    project = make_project(tmp_path)
    first = build_inventory(project)
    second = build_inventory(project)
    assert "empty" in first["directories"]
    assert inventory_hash(first) == inventory_hash(second)
    (project / "chapter.md").write_text("changed", encoding="utf-8")
    assert inventory_hash(first) != inventory_hash(build_inventory(project))


def test_preview_suggests_safe_target_and_token_validation(tmp_path):
    make_project(tmp_path)
    preview = DirectoryMigrationPreview(tmp_path, tmp_path / ".backup", "secret")
    value = preview.build("novel-1")
    assert value["available"] is True
    assert value["target_directory"] == "中文书"
    assert value["reload_required"] is True
    assert preview.validate(value["preview_token"], value["operation_id"], value["plan_fingerprint"])["available"]
    with pytest.raises(ValueError, match="preview_token_invalid"):
        DirectoryMigrationPreview(tmp_path, tmp_path / ".backup", "different").validate(
            value["preview_token"], value["operation_id"], value["plan_fingerprint"])


def test_preview_rejects_occupied_target_and_links(tmp_path):
    make_project(tmp_path)
    (tmp_path / "中文书").mkdir()
    preview = DirectoryMigrationPreview(tmp_path, tmp_path / ".backup", "secret")
    value = preview.build("novel-1")
    assert value["available"] is False
    assert value["reason_code"] == "target_directory_occupied"
