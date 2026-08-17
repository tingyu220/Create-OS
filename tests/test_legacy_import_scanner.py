from pathlib import Path

from creative_os.importing.scanner import scan_source


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_scanner_records_relative_paths_hashes_and_never_writes_source(tmp_path):
    source = tmp_path / "legacy"
    (source / "chapters").mkdir(parents=True)
    (source / "chapters" / "chapter-001.md").write_text("# 第一章", encoding="utf-8")
    (source / "world.json").write_text('{"rule":"physics"}', encoding="utf-8")
    (source / "ignored.txt").write_text("ignore", encoding="utf-8")
    before = _snapshot_tree(source)

    manifest = scan_source(source)

    assert [document.relative_path for document in manifest.documents] == ["chapters/chapter-001.md", "world.json"]
    assert all(document.sha256 for document in manifest.documents)
    assert all(not Path(document.relative_path).is_absolute() for document in manifest.documents)
    assert _snapshot_tree(source) == before


def test_scanner_ignores_hidden_system_paths(tmp_path):
    source = tmp_path / "legacy"
    (source / ".git").mkdir(parents=True)
    (source / ".git" / "config").write_text("ignored", encoding="utf-8")
    (source / "book.md").write_text("正文", encoding="utf-8")

    manifest = scan_source(source)

    assert [document.relative_path for document in manifest.documents] == ["book.md"]
