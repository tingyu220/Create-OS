"""初始化意图的目录别名检查，仅使用临时文件，不创建Runtime。"""

import hashlib
import json
import os

import pytest

from creative_os.project_registry import ProjectRegistry
from creative_os.project_write_gate import migration_lease


def seed_initializing(root, folder):
    source = root / "old"
    source.mkdir()
    (source / "project.json").write_text(json.dumps({"id": "stable", "name": "old"}), encoding="utf-8")
    directory = source if folder.casefold() == "old" else root / folder
    if directory != source:
        directory.mkdir()
    stat = directory.stat()
    identity = {"title": folder, "idea": "", "author": "", "genre": "", "story_mode": False}
    fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    record = {"fingerprint": fingerprint, "folder": folder, "status": "initializing", "identity": identity,
              "directory_identity": {"device": stat.st_dev, "inode": stat.st_ino}}
    path = root / ".creative_os/new-books.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"create-op": record}), encoding="utf-8")
    return source, path


@pytest.mark.parametrize("folder", ["old", "OLD", "Old"])
@pytest.mark.parametrize("entry", ["lease", "registry"])
def test_initializing_source_case_alias_refuses_migration(tmp_path, folder, entry):
    source, path = seed_initializing(tmp_path, folder)
    if os.name == "nt":
        assert (tmp_path / folder).samefile(source)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="project_migration_active"):
        if entry == "lease":
            with migration_lease(tmp_path, "stable"):
                pytest.fail("源对应的initializing意图不得放行")
        else:
            ProjectRegistry(tmp_path).assert_migration_idle("stable")
    assert path.read_bytes() == before


@pytest.mark.parametrize("entry", ["lease", "registry"])
def test_unrelated_initializing_directory_does_not_block_source(tmp_path, entry):
    source, path = seed_initializing(tmp_path, "OTHER")
    before = path.read_bytes()
    if entry == "lease":
        with migration_lease(tmp_path, "stable") as selected:
            assert selected == source
    else:
        ProjectRegistry(tmp_path).assert_migration_idle("stable")
    assert path.read_bytes() == before
