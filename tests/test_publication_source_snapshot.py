from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from dataclasses import FrozenInstanceError, replace

import pytest

import creative_os.domains.publication_source_snapshot as snapshot_module
from creative_os.domains.publication_source_snapshot import (
    SourceSnapshotError,
    build_source_snapshot,
    copy_verified_source_archive,
    load_verified_archive,
    verify_archive,
    verify_snapshot,
)


def _write_project(root: Path, *, first_text: str = "第一段\n\n第二段\n") -> Path:
    chapters = root / "production" / "final_chapters"
    chapters.mkdir(parents=True, exist_ok=True)
    for number in range(1, 33):
        text = first_text if number == 1 else f"第{number}章第一段\n\n第{number}章第二段\n"
        (chapters / f"chapter_{number:03}.md").write_text(text, encoding="utf-8", newline="")
    return root


def _snapshot(root: Path):
    return build_source_snapshot(root, 4, range(5, 33))


def test_build_freezes_first_four_and_covers_all_source_chapters(tmp_path):
    root = _write_project(tmp_path)

    snapshot = _snapshot(root)

    assert snapshot.project_id == tmp_path.name
    assert snapshot.frozen_through_chapter == 4
    assert [record.chapter_number for record in snapshot.frozen_records] == [1, 2, 3, 4]
    assert [record.chapter_number for record in snapshot.migration_records] == list(range(5, 33))
    assert all(record.relative_path == f"production/final_chapters/chapter_{record.chapter_number:03}.md"
               for record in (*snapshot.frozen_records, *snapshot.migration_records))
    assert all(len(record.paragraph_hashes) == 2
               for record in (*snapshot.frozen_records, *snapshot.migration_records))
    assert len(snapshot.snapshot_hash) == 64
    verify_snapshot(root, snapshot)


@pytest.mark.parametrize(
    ("frozen", "chapters"),
    [(3, range(5, 33)), (4, range(1, 33)), (4, range(5, 32)), (4, range(6, 33))],
)
def test_build_rejects_any_range_other_than_frozen_1_to_4_and_migration_5_to_32(
    tmp_path, frozen, chapters,
):
    root = _write_project(tmp_path)

    with pytest.raises(SourceSnapshotError, match="invalid_snapshot_range"):
        build_source_snapshot(root, frozen, chapters)


def test_snapshot_rejects_missing_or_duplicate_source_chapter(tmp_path):
    root = _write_project(tmp_path)
    (root / "production" / "final_chapters" / "chapter_007.md").unlink()

    with pytest.raises(SourceSnapshotError, match="chapter_missing"):
        _snapshot(root)

    _write_project(root)
    (root / "production" / "final_chapters" / "chapter_07.md").write_text("重复", encoding="utf-8")
    with pytest.raises(SourceSnapshotError, match="chapter_duplicate"):
        _snapshot(root)


def test_snapshot_uses_raw_hash_but_normalizes_crlf_for_paragraph_locators(tmp_path):
    crlf_root = _write_project(tmp_path, first_text="甲\r\n\r\n乙\r\n")
    lf_root = _write_project(tmp_path / "lf", first_text="甲\n\n乙\n")

    crlf = _snapshot(crlf_root).frozen_records[0]
    lf = _snapshot(lf_root).frozen_records[0]

    assert crlf.content_hash == hashlib.sha256(b"\xe7\x94\xb2\r\n\r\n\xe4\xb9\x99\r\n").hexdigest()
    assert crlf.content_hash != lf.content_hash
    assert tuple(fragment.text_hash for fragment in crlf.paragraph_hashes) == (
        hashlib.sha256("甲".encode()).hexdigest(),
        hashlib.sha256("乙\n".encode()).hexdigest(),
    )
    assert tuple(fragment.text_hash for fragment in crlf.paragraph_hashes) == tuple(
        fragment.text_hash for fragment in lf.paragraph_hashes
    )


def test_snapshot_splits_multiple_whitespace_only_blank_lines(tmp_path):
    root = _write_project(tmp_path, first_text="甲\n \n\t\n乙")

    record = _snapshot(root).frozen_records[0]

    assert len(record.paragraph_hashes) == 2
    assert tuple(fragment.text_hash for fragment in record.paragraph_hashes) == (
        hashlib.sha256("甲".encode()).hexdigest(),
        hashlib.sha256("乙".encode()).hexdigest(),
    )


def test_verify_snapshot_detects_raw_and_paragraph_drift(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    source = root / "production" / "final_chapters" / "chapter_003.md"
    source.write_text("修改后\n\n第二段\n", encoding="utf-8")

    with pytest.raises(SourceSnapshotError, match="source_hash_drift"):
        verify_snapshot(root, snapshot)


def test_verify_snapshot_independently_detects_paragraph_locator_drift(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    first = snapshot.frozen_records[0]
    changed_fragment = replace(first.paragraph_hashes[0], text_hash="0" * 64)
    changed_record = replace(first, paragraph_hashes=(changed_fragment, *first.paragraph_hashes[1:]))
    records = (changed_record, *snapshot.frozen_records[1:], *snapshot.migration_records)
    identity = snapshot_module._sha256(snapshot_module._canonical(snapshot_module._records_payload(records)))
    partial = {
        "source_edition_id": f"source-edition-{identity[:16]}",
        "project_id": snapshot.project_id,
        "frozen_through_chapter": 4,
        "frozen_records": snapshot_module._records_payload(records[:4]),
        "migration_records": snapshot_module._records_payload(records[4:]),
    }
    tampered = replace(
        snapshot,
        source_edition_id=partial["source_edition_id"],
        frozen_records=records[:4],
        snapshot_hash=snapshot_module._sha256(snapshot_module._canonical(partial)),
    )

    with pytest.raises(SourceSnapshotError, match="paragraph_hash_drift"):
        verify_snapshot(root, tampered)


def test_verify_snapshot_rejects_wrong_project_edition_and_snapshot_hash(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)

    with pytest.raises(SourceSnapshotError, match="snapshot_binding_invalid"):
        verify_snapshot(root, replace(snapshot, project_id="other-project"))
    with pytest.raises(SourceSnapshotError, match="snapshot_edition_invalid"):
        verify_snapshot(root, replace(snapshot, source_edition_id="source-edition-0000000000000000"))
    with pytest.raises(SourceSnapshotError, match="snapshot_hash_invalid"):
        verify_snapshot(root, replace(snapshot, snapshot_hash="0" * 64))


def test_snapshot_file_is_canonical_and_hash_is_deterministic(tmp_path):
    root = _write_project(tmp_path)
    first = _snapshot(root)
    second = _snapshot(root)

    assert first == second
    encoded = snapshot_module._snapshot_file_bytes(first)
    assert encoded.endswith(b"\n")
    assert encoded[:-1] == json.dumps(
        json.loads(encoded), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def test_copy_archive_preserves_all_hashes_and_reopens_for_verification(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ctime_ns)
        for path in (root / "production" / "final_chapters").glob("*.md")
    }

    receipt = copy_verified_source_archive(snapshot, root)

    archive = root / ".creative_os" / "publication_migration" / "source_editions" / snapshot.source_edition_id
    assert receipt.archive_root == archive
    assert receipt.verified_file_count == 28
    assert receipt.source_snapshot_hash == snapshot.snapshot_hash
    assert receipt.archive_hash != snapshot.snapshot_hash
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ctime_ns)
        for path in before
    } == before
    assert not (archive / "final_chapters" / "chapter_004.md").exists()
    assert [hashlib.sha256((archive / record.relative_path.split("/", 1)[1]).read_bytes()).hexdigest()
            for record in snapshot.migration_records] == [
                record.content_hash for record in snapshot.migration_records
            ]
    verify_archive(receipt, snapshot, root)


def test_exact_archive_is_idempotent_but_conflicting_archive_is_rejected(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    first = copy_verified_source_archive(snapshot, root)

    assert copy_verified_source_archive(snapshot, root) == first
    archive_file = first.archive_root / "final_chapters" / "chapter_005.md"
    archive_file.write_text("篡改", encoding="utf-8")
    with pytest.raises(SourceSnapshotError, match="archive_conflict"):
        copy_verified_source_archive(snapshot, root)


@pytest.mark.parametrize("extra", ["extra.txt", "extra_dir"])
def test_exact_archive_rejects_any_extra_entry(tmp_path, extra):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    path = receipt.archive_root / extra
    path.mkdir() if extra.endswith("dir") else path.write_text("unexpected", encoding="utf-8")

    with pytest.raises(SourceSnapshotError, match="archive_(tree|hash)_drift"):
        verify_archive(receipt, snapshot, root)


def test_exact_archive_rejects_extra_symlink_entry_when_supported(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    outside = tmp_path / "outside-extra.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        (receipt.archive_root / "extra-link").symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlink unavailable: {error}")

    with pytest.raises(SourceSnapshotError, match="archive_tree_drift"):
        verify_archive(receipt, snapshot, root)


def test_copy_interruption_never_publishes_a_trusted_partial_archive(tmp_path, monkeypatch):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)

    def interrupt(event: str, _path: Path) -> None:
        if event == "before_archive_copy:chapter_010.md":
            raise OSError("injected archive interruption")

    monkeypatch.setattr(snapshot_module, "_IO_HOOK", interrupt)
    with pytest.raises(OSError, match="interruption"):
        copy_verified_source_archive(snapshot, root)
    monkeypatch.setattr(snapshot_module, "_IO_HOOK", lambda *_args: None)

    archive = root / ".creative_os" / "publication_migration" / "source_editions" / snapshot.source_edition_id
    assert not archive.exists()


def test_copy_rejects_replaced_temporary_tree_without_outside_write_or_publish(tmp_path, monkeypatch):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    outside = tmp_path / "outside-temp"
    outside.mkdir()

    replacement_blocked = False

    def replace_temp(event: str, path: Path) -> None:
        nonlocal replacement_blocked
        if event != "before_archive_copy:chapter_010.md":
            return
        temp_root = path.parent.parent
        moved = temp_root.with_name(temp_root.name + "-moved")
        try:
            temp_root.replace(moved)
        except PermissionError:
            replacement_blocked = True
            return
        try:
            temp_root.symlink_to(outside, target_is_directory=True)
        except OSError:
            temp_root.mkdir()

    monkeypatch.setattr(snapshot_module, "_IO_HOOK", replace_temp)
    try:
        receipt = copy_verified_source_archive(snapshot, root)
    except SourceSnapshotError:
        receipt = None

    archive = root / ".creative_os" / "publication_migration" / "source_editions" / snapshot.source_edition_id
    assert replacement_blocked or not archive.exists()
    if receipt is not None:
        verify_archive(receipt, snapshot, root)
    assert tuple(outside.iterdir()) == ()


def test_final_archive_race_is_noreplace_and_conflicting_tree_is_not_overwritten(tmp_path, monkeypatch):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    final_root = root / ".creative_os" / "publication_migration" / "source_editions" / snapshot.source_edition_id

    def publish_conflict(event: str, _path: Path) -> None:
        if event == "before_archive_publish":
            final_root.mkdir()
            (final_root / "competitor.txt").write_text("keep", encoding="utf-8")

    monkeypatch.setattr(snapshot_module, "_IO_HOOK", publish_conflict)
    with pytest.raises(SourceSnapshotError, match="archive_conflict"):
        copy_verified_source_archive(snapshot, root)
    assert (final_root / "competitor.txt").read_text(encoding="utf-8") == "keep"


def test_final_archive_race_with_identical_tree_is_idempotent(tmp_path, monkeypatch):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    final_root = root / ".creative_os" / "publication_migration" / "source_editions" / snapshot.source_edition_id

    def publish_same(event: str, _path: Path) -> None:
        if event != "before_archive_publish":
            return
        archive_base = final_root.parent
        temporary = next(path for path in archive_base.iterdir() if path.name.startswith(".source-edition-"))
        shutil.copytree(temporary, final_root)

    monkeypatch.setattr(snapshot_module, "_IO_HOOK", publish_same)
    receipt = copy_verified_source_archive(snapshot, root)
    verify_archive(receipt, snapshot, root)


def test_rogue_entry_before_publish_never_reaches_final_archive(tmp_path, monkeypatch):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    final_root = root / ".creative_os" / "publication_migration" / "source_editions" / snapshot.source_edition_id

    def inject(event: str, path: Path) -> None:
        if event == "before_archive_publish":
            temporary = next(
                item for item in final_root.parent.iterdir()
                if item.name.startswith(".source-edition-") and item.is_dir()
            )
            (temporary / "rogue.txt").write_text("rogue", encoding="utf-8")

    monkeypatch.setattr(snapshot_module, "_IO_HOOK", inject)
    with pytest.raises(SourceSnapshotError, match="archive_tree_drift"):
        copy_verified_source_archive(snapshot, root)
    assert not final_root.exists()


def test_rogue_entry_immediately_after_publish_is_retracted_from_final_path(tmp_path, monkeypatch):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    final_root = root / ".creative_os" / "publication_migration" / "source_editions" / snapshot.source_edition_id

    def inject(event: str, path: Path) -> None:
        if event == "after_archive_publish":
            (path / "rogue.txt").write_text("rogue", encoding="utf-8")

    monkeypatch.setattr(snapshot_module, "_IO_HOOK", inject)
    with pytest.raises(SourceSnapshotError, match="archive_tree_drift"):
        copy_verified_source_archive(snapshot, root)
    assert not final_root.exists()


@pytest.mark.parametrize("event", ["between_archive_tree_scans", "before_archive_verify_return"])
def test_verify_archive_never_succeeds_when_rogue_arrives_at_last_scan_boundaries(
    tmp_path, monkeypatch, event,
):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    injected = False

    def inject(current: str, _path: Path) -> None:
        nonlocal injected
        if current == event and not injected:
            injected = True
            (receipt.archive_root / "rogue.txt").write_text("rogue", encoding="utf-8")

    monkeypatch.setattr(snapshot_module, "_IO_HOOK", inject)
    with pytest.raises(SourceSnapshotError, match="archive_tree_drift"):
        verify_archive(receipt, snapshot, root)
    assert injected


def test_snapshot_rejects_symlinked_source_boundary(tmp_path):
    root = _write_project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    source = root / "production" / "final_chapters"
    replacement = root / "production" / "replacement"
    source.replace(replacement)
    try:
        source.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink unavailable: {error}")
    with pytest.raises(SourceSnapshotError):
        _snapshot(root)


def test_archive_rejects_replaced_boundary_even_without_symlink_privilege(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()

    root = _write_project(tmp_path / "safe")
    snapshot = _snapshot(root)

    replacement_blocked = False

    def replace_archive_base(event: str, _path: Path) -> None:
        nonlocal replacement_blocked
        if event != "before_archive_publish":
            return
        archive_base = root / ".creative_os" / "publication_migration" / "source_editions"
        moved = root / "moved-source-editions"
        try:
            archive_base.replace(moved)
            archive_base.symlink_to(outside, target_is_directory=True)
        except (OSError, PermissionError):
            replacement_blocked = True
            return

    monkeypatch.setattr(snapshot_module, "_IO_HOOK", replace_archive_base)
    try:
        receipt = copy_verified_source_archive(snapshot, root)
    except SourceSnapshotError:
        receipt = None
    assert replacement_blocked or receipt is None
    if receipt is not None:
        verify_archive(receipt, snapshot, root)
    assert tuple(outside.iterdir()) == ()


def test_archive_rejects_reparse_probe_for_temporary_entry(tmp_path, monkeypatch):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    original = snapshot_module._is_reparse

    def probe(info):
        return original(info) or getattr(info, "st_ino", None) in marked

    marked: set[int] = set()

    def mark_temp(event: str, path: Path) -> None:
        if event == "before_archive_copy:chapter_010.md":
            marked.add(os.lstat(path.parent).st_ino)

    monkeypatch.setattr(snapshot_module, "_is_reparse", probe)
    monkeypatch.setattr(snapshot_module, "_IO_HOOK", mark_temp)
    with pytest.raises(SourceSnapshotError):
        copy_verified_source_archive(snapshot, root)


def test_verify_archive_rejects_reparse_probe_for_final_entry(tmp_path, monkeypatch):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    original = snapshot_module._is_reparse
    marked = os.lstat(receipt.archive_root).st_ino

    monkeypatch.setattr(
        snapshot_module,
        "_is_reparse",
        lambda info: original(info) or getattr(info, "st_ino", None) == marked,
    )
    with pytest.raises(SourceSnapshotError, match="archive_root_invalid"):
        verify_archive(receipt, snapshot, root)


def test_verify_archive_reopens_files_and_rejects_tampering(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    (receipt.archive_root / "snapshot.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(SourceSnapshotError, match="archive_hash_drift"):
        verify_archive(receipt, snapshot, root)


def test_load_verified_archive_needs_only_receipt_and_returns_frozen_paragraphs(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)

    view = load_verified_archive(receipt, root)
    paragraph = view.load_paragraph(5, 1)

    assert view.snapshot_hash == snapshot.snapshot_hash
    assert view.archive_hash == receipt.archive_hash
    assert paragraph.chapter_number == 5
    assert paragraph.paragraph_ordinal == 1
    assert paragraph.text == "第5章第一段"
    assert paragraph.paragraph_hash == hashlib.sha256("第5章第一段".encode()).hexdigest()
    assert paragraph.source_file_hash == snapshot.migration_records[0].content_hash
    assert paragraph.archive_hash == receipt.archive_hash
    assert isinstance(view.load_paragraphs(5), tuple)
    assert isinstance(view.iter_paragraphs(), tuple)
    with pytest.raises(FrozenInstanceError):
        paragraph.text = "篡改"


def test_load_verified_archive_rejects_strict_snapshot_shape_and_binding_mismatch(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    other_root = _write_project(tmp_path / "other")
    with pytest.raises(SourceSnapshotError, match="archive_receipt_binding_invalid"):
        load_verified_archive(receipt, other_root)
    with pytest.raises(SourceSnapshotError, match="archive_receipt_binding_invalid"):
        load_verified_archive(replace(receipt, source_edition_id="source-edition-0000000000000000"), root)
    with pytest.raises(SourceSnapshotError, match="archive_(receipt|hash)"):
        load_verified_archive(replace(receipt, archive_hash="0" * 64), root)
    with pytest.raises(SourceSnapshotError, match="archive_hash_drift"):
        load_verified_archive(replace(receipt, verified_file_count=29), root)

    snapshot_path = receipt.archive_root / "snapshot.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload["unknown"] = True
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SourceSnapshotError, match="snapshot_json_invalid"):
        load_verified_archive(receipt, root)


@pytest.mark.parametrize("mutation", ["missing", "wrong_type", "duplicate_key", "reordered"])
def test_load_verified_archive_strictly_rejects_malformed_snapshot_records(tmp_path, mutation):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    path = receipt.archive_root / "snapshot.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "missing":
        del payload["frozen_records"][0]["content_hash"]
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    elif mutation == "wrong_type":
        payload["frozen_records"][0]["chapter_number"] = True
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    elif mutation == "reordered":
        payload["frozen_records"][0], payload["frozen_records"][1] = (
            payload["frozen_records"][1], payload["frozen_records"][0],
        )
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    else:
        raw = path.read_text(encoding="utf-8").replace(
            '"project_id":', '"project_id":"duplicate","project_id":', 1,
        )
    path.write_text(raw, encoding="utf-8", newline="")

    with pytest.raises(SourceSnapshotError):
        load_verified_archive(receipt, root)


def test_load_verified_archive_rejects_self_hashed_paragraph_locator_drift(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    old_root = receipt.archive_root
    payload = json.loads((old_root / "snapshot.json").read_text(encoding="utf-8"))
    payload["migration_records"][0]["paragraph_hashes"][0]["text_hash"] = "0" * 64
    records = payload["frozen_records"] + payload["migration_records"]
    identity = hashlib.sha256(snapshot_module._canonical(records)).hexdigest()
    payload["source_edition_id"] = f"source-edition-{identity[:16]}"
    partial = {key: value for key, value in payload.items() if key != "snapshot_hash"}
    payload["snapshot_hash"] = hashlib.sha256(snapshot_module._canonical(partial)).hexdigest()
    encoded = snapshot_module._canonical(payload) + b"\n"
    (old_root / "snapshot.json").write_bytes(encoded)
    new_root = old_root.with_name(payload["source_edition_id"])
    old_root.rename(new_root)
    files = [("snapshot.json", encoded)] + [
        (f"final_chapters/{path.name}", path.read_bytes())
        for path in sorted((new_root / "final_chapters").iterdir())
    ]
    forged = replace(
        receipt,
        source_edition_id=payload["source_edition_id"],
        archive_root=new_root,
        source_snapshot_hash=payload["snapshot_hash"],
        archive_hash=snapshot_module._archive_hash(files),
    )

    with pytest.raises(SourceSnapshotError, match="archive_paragraph_hash_drift"):
        load_verified_archive(forged, root)


@pytest.mark.parametrize("mutation", ["chapter", "extra", "snapshot_hash"])
def test_load_verified_archive_rejects_content_and_tree_tampering(tmp_path, mutation):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    if mutation == "chapter":
        (receipt.archive_root / "final_chapters" / "chapter_005.md").write_text("篡改", encoding="utf-8")
    elif mutation == "extra":
        (receipt.archive_root / "rogue.txt").write_text("rogue", encoding="utf-8")
    else:
        payload = json.loads((receipt.archive_root / "snapshot.json").read_text(encoding="utf-8"))
        payload["snapshot_hash"] = "0" * 64
        (receipt.archive_root / "snapshot.json").write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    with pytest.raises(SourceSnapshotError):
        load_verified_archive(receipt, root)


def test_verified_view_is_materialized_and_refresh_revalidates_current_archive(tmp_path, monkeypatch):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    view = load_verified_archive(receipt, root)

    with pytest.raises(SourceSnapshotError, match="paragraph_ordinal_invalid"):
        view.load_paragraph(5, 0)
    with pytest.raises(SourceSnapshotError, match="paragraph_ordinal_invalid"):
        view.load_paragraph(5, 3)

    injected = False

    def replace_during_read(event: str, path: Path) -> None:
        nonlocal injected
        if event == "before_archive_verify_return" and not injected:
            injected = True
            (receipt.archive_root / "rogue.txt").write_text("rogue", encoding="utf-8")

    monkeypatch.setattr(snapshot_module, "_IO_HOOK", replace_during_read)
    assert view.load_paragraph(5, 1).text == "第5章第一段"
    with pytest.raises(SourceSnapshotError):
        view.verify_current()
    assert injected


def test_load_recomputes_frozen_chapters_from_project_not_archive(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    (root / "production" / "final_chapters" / "chapter_001.md").write_text("冻结章漂移", encoding="utf-8")

    with pytest.raises(SourceSnapshotError, match="frozen_source_drift"):
        load_verified_archive(receipt, root)


def test_self_hashed_fake_migration_locator_is_rejected(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    old_root = receipt.archive_root
    payload = json.loads((old_root / "snapshot.json").read_text(encoding="utf-8"))
    payload["migration_records"][0]["paragraph_hashes"][0]["paragraph_start"] = 2
    payload["migration_records"][0]["paragraph_hashes"][0]["paragraph_end"] = 2
    records = payload["frozen_records"] + payload["migration_records"]
    identity = hashlib.sha256(snapshot_module._canonical(records)).hexdigest()
    payload["source_edition_id"] = f"source-edition-{identity[:16]}"
    partial = {key: value for key, value in payload.items() if key != "snapshot_hash"}
    payload["snapshot_hash"] = hashlib.sha256(snapshot_module._canonical(partial)).hexdigest()
    encoded = snapshot_module._canonical(payload) + b"\n"
    (old_root / "snapshot.json").write_bytes(encoded)
    new_root = old_root.with_name(payload["source_edition_id"])
    old_root.rename(new_root)
    files = [("snapshot.json", encoded)] + [
        (f"final_chapters/{path.name}", path.read_bytes())
        for path in sorted((new_root / "final_chapters").iterdir())
    ]
    forged = replace(
        receipt,
        source_edition_id=payload["source_edition_id"],
        archive_root=new_root,
        source_snapshot_hash=payload["snapshot_hash"],
        archive_hash=snapshot_module._archive_hash(files),
    )

    with pytest.raises(SourceSnapshotError, match="archive_paragraph_locator_drift"):
        load_verified_archive(forged, root)


def test_load_rejects_receipt_locator_traversal_absolute_and_foreign_paths(tmp_path):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)

    for edition in ("../escape", str((tmp_path / "absolute").absolute())):
        with pytest.raises((ValueError, SourceSnapshotError)):
            load_verified_archive(replace(receipt, source_edition_id=edition), root)
    with pytest.raises(SourceSnapshotError, match="archive_receipt_binding_invalid"):
        load_verified_archive(replace(receipt, archive_root=tmp_path / "foreign"), root)


def test_load_catches_extra_entry_injected_after_final_scan(tmp_path, monkeypatch):
    root = _write_project(tmp_path)
    snapshot = _snapshot(root)
    receipt = copy_verified_source_archive(snapshot, root)
    injected = False

    def inject(event: str, path: Path) -> None:
        nonlocal injected
        if event == "after_archive_final_scan" and not injected:
            injected = True
            (path / "rogue.txt").write_text("rogue", encoding="utf-8")

    monkeypatch.setattr(snapshot_module, "_IO_HOOK", inject)
    with pytest.raises(SourceSnapshotError, match="archive_tree_drift"):
        load_verified_archive(receipt, root)
    assert injected
