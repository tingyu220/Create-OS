from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import ctypes
import errno

from creative_os.domains.contract_record_filesystem import TrustedStoreFilesystem
from creative_os.domains.publication_migration_model import FileHashRecord, SourceFragment


_CHAPTER_NAME = re.compile(r"^chapter_(\d+)\.md$")
_CANONICAL_CHAPTER = "production/final_chapters/chapter_{:03}.md"
_ARCHIVE_PREFIX = Path(".creative_os") / "publication_migration" / "source_editions"
_IO_HOOK = lambda _event, _path: None


class SourceSnapshotError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SourceChapterRecord:
    chapter_number: int
    relative_path: str
    content_hash: str
    paragraph_hashes: tuple[SourceFragment, ...]

    def __post_init__(self) -> None:
        if type(self.chapter_number) is not int or self.chapter_number <= 0:
            raise ValueError("invalid source chapter")
        if self.relative_path != _CANONICAL_CHAPTER.format(self.chapter_number):
            raise ValueError("invalid source relative path")
        FileHashRecord(self.relative_path, self.content_hash)
        if not isinstance(self.paragraph_hashes, tuple) or any(
            fragment.source_chapter != self.chapter_number
            or fragment.paragraph_start != fragment.paragraph_end
            for fragment in self.paragraph_hashes
        ):
            raise ValueError("invalid paragraph hashes")


@dataclass(frozen=True, slots=True)
class SourceEditionSnapshot:
    source_edition_id: str
    project_id: str
    frozen_through_chapter: int
    frozen_records: tuple[SourceChapterRecord, ...]
    migration_records: tuple[SourceChapterRecord, ...]
    snapshot_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_edition_id, str) or not re.fullmatch(
            r"source-edition-[0-9a-f]{16}", self.source_edition_id,
        ):
            raise ValueError("source edition id is required")
        if not _is_project_id(self.project_id):
            raise ValueError("project id is required")
        if type(self.frozen_through_chapter) is not int or self.frozen_through_chapter <= 0:
            raise ValueError("invalid frozen chapter")
        if not all(isinstance(record, SourceChapterRecord) for record in (*self.frozen_records, *self.migration_records)):
            raise ValueError("invalid source records")
        if not _is_hash(self.snapshot_hash):
            raise ValueError("invalid snapshot hash")


@dataclass(frozen=True, slots=True)
class ArchiveReceipt:
    source_edition_id: str
    archive_root: Path
    verified_file_count: int
    source_snapshot_hash: str
    archive_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_edition_id, str) or not re.fullmatch(
            r"source-edition-[0-9a-f]{16}", self.source_edition_id,
        ):
            raise ValueError("source edition id is required")
        if not isinstance(self.archive_root, Path) or not self.archive_root.is_absolute():
            raise ValueError("invalid archive root")
        if type(self.verified_file_count) is not int or self.verified_file_count <= 0:
            raise ValueError("invalid verified file count")
        if not _is_hash(self.source_snapshot_hash) or not _is_hash(self.archive_hash):
            raise ValueError("invalid archive receipt hash")


@dataclass(frozen=True, slots=True)
class VerifiedSourceParagraph:
    chapter_number: int
    paragraph_ordinal: int
    text: str
    paragraph_hash: str
    source_file_hash: str
    snapshot_hash: str
    archive_hash: str


@dataclass(frozen=True, slots=True)
class VerifiedSourceArchiveView:
    source_edition_id: str
    project_id: str
    snapshot_hash: str
    archive_hash: str
    chapter_numbers: tuple[int, ...]
    paragraphs: tuple[VerifiedSourceParagraph, ...]
    _project_root: Path = field(repr=False, compare=False)
    _receipt: ArchiveReceipt = field(repr=False, compare=False)

    def load_paragraph(self, chapter_number: int, paragraph_ordinal: int) -> VerifiedSourceParagraph:
        paragraphs = self.load_paragraphs(chapter_number)
        if type(paragraph_ordinal) is not int or not 1 <= paragraph_ordinal <= len(paragraphs):
            raise SourceSnapshotError("paragraph_ordinal_invalid")
        return paragraphs[paragraph_ordinal - 1]

    def load_paragraphs(self, chapter_number: int) -> tuple[VerifiedSourceParagraph, ...]:
        if type(chapter_number) is not int or chapter_number not in self.chapter_numbers:
            raise SourceSnapshotError("source_chapter_invalid")
        return tuple(item for item in self.paragraphs if item.chapter_number == chapter_number)

    def iter_paragraphs(self) -> tuple[VerifiedSourceParagraph, ...]:
        return self.paragraphs

    def verify_current(self) -> None:
        _load_verified_archive_state(self._receipt, self._project_root)


def build_source_snapshot(
    project_root: Path, frozen_through_chapter: int, source_chapters: range,
) -> SourceEditionSnapshot:
    root, source_directory = _validate_request(project_root, frozen_through_chapter, source_chapters)
    filesystem = _source_filesystem(root, source_directory)
    try:
        records = _read_source_records(filesystem, source_directory, tuple(range(1, 33)))
    finally:
        filesystem.close()
    frozen = tuple(record for record in records if record.chapter_number <= frozen_through_chapter)
    migration = tuple(record for record in records if record.chapter_number > frozen_through_chapter)
    identity = _sha256(_canonical(_records_payload(records)))
    source_edition_id = f"source-edition-{identity[:16]}"
    partial = {
        "source_edition_id": source_edition_id,
        "project_id": root.name,
        "frozen_through_chapter": frozen_through_chapter,
        "frozen_records": _records_payload(frozen),
        "migration_records": _records_payload(migration),
    }
    return SourceEditionSnapshot(
        source_edition_id=source_edition_id,
        project_id=root.name,
        frozen_through_chapter=frozen_through_chapter,
        frozen_records=frozen,
        migration_records=migration,
        snapshot_hash=_sha256(_canonical(partial)),
    )


def verify_snapshot(project_root: Path, snapshot: SourceEditionSnapshot) -> None:
    if not isinstance(snapshot, SourceEditionSnapshot):
        raise SourceSnapshotError("snapshot_invalid")
    root = _absolute_root(project_root)
    _validate_snapshot_shape(root, snapshot)
    source_directory = root / "production" / "final_chapters"
    _require_existing_directory(source_directory, "source_directory_invalid")
    filesystem = _source_filesystem(root, source_directory)
    try:
        expected = (*snapshot.frozen_records, *snapshot.migration_records)
        actual = _read_source_records(filesystem, source_directory, tuple(record.chapter_number for record in expected))
    finally:
        filesystem.close()
    for expected_record, actual_record in zip(expected, actual, strict=True):
        if expected_record.content_hash != actual_record.content_hash:
            raise SourceSnapshotError("source_hash_drift")
        if expected_record.paragraph_hashes != actual_record.paragraph_hashes:
            raise SourceSnapshotError("paragraph_hash_drift")


def copy_verified_source_archive(snapshot: SourceEditionSnapshot, project_root: Path) -> ArchiveReceipt:
    verify_snapshot(project_root, snapshot)
    root = _absolute_root(project_root)
    source_directory = root / "production" / "final_chapters"
    archive_base = root / _ARCHIVE_PREFIX
    archive_root = archive_base / snapshot.source_edition_id
    _require_safe_archive_target(root, archive_root)
    filesystem = TrustedStoreFilesystem(
        root,
        (source_directory, archive_base),
        archive_base / ".source-snapshot.lock",
        error_type=SourceSnapshotError,
        conflict_type=SourceSnapshotError,
        hook=_IO_HOOK,
    )
    try:
        with filesystem.exclusive_lock():
            filesystem.validate_all()
            if _entry_exists(archive_root):
                return _existing_archive_receipt(snapshot, root, archive_root)
            temporary_root = Path(tempfile.mkdtemp(prefix=".source-edition-", dir=archive_base))
            temporary_chapters = temporary_root / "final_chapters"
            temporary_chapters.mkdir()
            temporary_filesystem = TrustedStoreFilesystem(
                root,
                (archive_base, temporary_root, temporary_chapters),
                archive_base / ".source-snapshot.lock",
                error_type=SourceSnapshotError,
                conflict_type=SourceSnapshotError,
                hook=_IO_HOOK,
            )
            try:
                for record in snapshot.migration_records:
                    source_path = source_directory / Path(record.relative_path).name
                    destination = temporary_chapters / source_path.name
                    _IO_HOOK(f"before_archive_copy:{source_path.name}", destination)
                    source_bytes = filesystem.read_bytes(source_path)
                    temporary_filesystem.atomic_write_bytes(destination, source_bytes, expected=None)
                    if _sha256(temporary_filesystem.read_bytes(destination)) != record.content_hash:
                        raise SourceSnapshotError("archive_copy_hash_mismatch")
                snapshot_path = temporary_root / "snapshot.json"
                snapshot_bytes = _snapshot_file_bytes(snapshot)
                temporary_filesystem.atomic_write_bytes(snapshot_path, snapshot_bytes, expected=None)
                if temporary_filesystem.read_bytes(snapshot_path) != snapshot_bytes:
                    raise SourceSnapshotError("archive_snapshot_write_mismatch")
                _require_exact_archive_tree(temporary_filesystem, temporary_root, snapshot)
                _IO_HOOK("before_archive_publish", archive_root)
                filesystem.validate_all()
                temporary_filesystem.validate_all()
                _require_exact_archive_tree(temporary_filesystem, temporary_root, snapshot)
                temporary_identity = temporary_filesystem._directory_identities[temporary_root]
                if os.name == "nt":
                    temporary_filesystem.close()
                try:
                    _publish_directory_noreplace(
                        filesystem, temporary_root, archive_root, temporary_identity,
                    )
                except (FileExistsError, OSError) as error:
                    if _entry_exists(archive_root):
                        temporary_filesystem.close()
                        return _existing_archive_receipt(snapshot, root, archive_root)
                    raise SourceSnapshotError("archive_publish_failed") from error
                try:
                    _IO_HOOK("after_archive_publish", archive_root)
                    receipt = _archive_receipt(snapshot, root, archive_root)
                except Exception:
                    _retract_own_archive(archive_root, temporary_root, temporary_identity)
                    raise
            finally:
                temporary_filesystem.close()
            filesystem.validate_all()
            return receipt
    finally:
        filesystem.close()


def verify_archive(receipt: ArchiveReceipt, snapshot: SourceEditionSnapshot, project_root: Path) -> None:
    if not isinstance(receipt, ArchiveReceipt) or not isinstance(snapshot, SourceEditionSnapshot):
        raise SourceSnapshotError("archive_receipt_invalid")
    root = _absolute_root(project_root)
    _validate_snapshot_shape(root, snapshot)
    expected_root = root / _ARCHIVE_PREFIX / snapshot.source_edition_id
    if receipt.source_edition_id != snapshot.source_edition_id or receipt.archive_root != expected_root:
        raise SourceSnapshotError("archive_receipt_binding_invalid")
    if receipt.source_snapshot_hash != snapshot.snapshot_hash:
        raise SourceSnapshotError("archive_receipt_snapshot_invalid")
    _require_existing_directory(expected_root, "archive_root_invalid")
    chapters = expected_root / "final_chapters"
    _require_existing_directory(chapters, "archive_directory_invalid")
    files = _read_archive_files(root, expected_root, snapshot)
    archive_hash = _archive_hash(files)
    if receipt.verified_file_count != len(files) - 1 or receipt.archive_hash != archive_hash:
        raise SourceSnapshotError("archive_hash_drift")


def load_verified_archive(
    receipt: ArchiveReceipt, project_root: Path,
) -> VerifiedSourceArchiveView:
    root = _absolute_root(project_root)
    snapshot, chapter_texts = _load_verified_archive_state(receipt, root)
    paragraphs = tuple(
        VerifiedSourceParagraph(
            chapter_number=record.chapter_number,
            paragraph_ordinal=index,
            text=text,
            paragraph_hash=record.paragraph_hashes[index - 1].text_hash,
            source_file_hash=record.content_hash,
            snapshot_hash=snapshot.snapshot_hash,
            archive_hash=receipt.archive_hash,
        )
        for record in snapshot.migration_records
        for index, text in enumerate(chapter_texts[record.chapter_number], start=1)
    )
    return VerifiedSourceArchiveView(
        source_edition_id=snapshot.source_edition_id,
        project_id=snapshot.project_id,
        snapshot_hash=snapshot.snapshot_hash,
        archive_hash=receipt.archive_hash,
        chapter_numbers=tuple(range(5, 33)),
        paragraphs=paragraphs,
        _project_root=root,
        _receipt=receipt,
    )


def _existing_archive_receipt(snapshot: SourceEditionSnapshot, root: Path, archive_root: Path) -> ArchiveReceipt:
    try:
        receipt = _archive_receipt(snapshot, root, archive_root)
    except SourceSnapshotError as error:
        raise SourceSnapshotError("archive_conflict") from error
    return receipt


def _archive_receipt(snapshot: SourceEditionSnapshot, root: Path, archive_root: Path) -> ArchiveReceipt:
    files = _read_archive_files(root, archive_root, snapshot, lock_held=True)
    return ArchiveReceipt(
        source_edition_id=snapshot.source_edition_id,
        archive_root=archive_root,
        verified_file_count=len(files) - 1,
        source_snapshot_hash=snapshot.snapshot_hash,
        archive_hash=_archive_hash(files),
    )


def _read_archive_files(
    root: Path,
    archive_root: Path,
    snapshot: SourceEditionSnapshot,
    *,
    lock_held: bool = False,
) -> list[tuple[str, bytes]]:
    chapters = archive_root / "final_chapters"
    _require_existing_directory(archive_root, "archive_root_invalid")
    _require_existing_directory(chapters, "archive_directory_invalid")
    filesystem = TrustedStoreFilesystem(
        root,
        (root / _ARCHIVE_PREFIX, archive_root, chapters),
        root / _ARCHIVE_PREFIX / ".source-snapshot.lock",
        error_type=SourceSnapshotError,
        conflict_type=SourceSnapshotError,
        hook=_IO_HOOK,
    )
    try:
        if lock_held:
            return _read_archive_files_from_filesystem(filesystem, archive_root, snapshot)[0]
        with filesystem.exclusive_lock():
            return _read_archive_files_from_filesystem(filesystem, archive_root, snapshot)[0]
    finally:
        filesystem.close()


def _load_verified_archive_state(
    receipt: ArchiveReceipt, root: Path,
) -> tuple[SourceEditionSnapshot, dict[int, tuple[str, ...]]]:
    if not isinstance(receipt, ArchiveReceipt):
        raise SourceSnapshotError("archive_receipt_invalid")
    expected_root = root / _ARCHIVE_PREFIX / receipt.source_edition_id
    if receipt.archive_root != expected_root:
        raise SourceSnapshotError("archive_receipt_binding_invalid")
    try:
        expected_root.resolve(strict=False).relative_to((root / _ARCHIVE_PREFIX).resolve(strict=False))
    except (OSError, ValueError) as error:
        raise SourceSnapshotError("archive_receipt_binding_invalid") from error
    chapters = expected_root / "final_chapters"
    source_directory = root / "production" / "final_chapters"
    _require_existing_directory(expected_root, "archive_root_invalid")
    _require_existing_directory(chapters, "archive_directory_invalid")
    filesystem = TrustedStoreFilesystem(
        root,
        (source_directory, root / _ARCHIVE_PREFIX, expected_root, chapters),
        root / _ARCHIVE_PREFIX / ".source-snapshot.lock",
        error_type=SourceSnapshotError,
        conflict_type=SourceSnapshotError,
        hook=_IO_HOOK,
    )
    try:
        with filesystem.exclusive_lock():
            raw_snapshot = filesystem.read_bytes(expected_root / "snapshot.json")
            snapshot = _decode_snapshot_file(raw_snapshot)
            _validate_snapshot_shape(root, snapshot)
            if snapshot.source_edition_id != receipt.source_edition_id:
                raise SourceSnapshotError("archive_receipt_binding_invalid")
            if snapshot.snapshot_hash != receipt.source_snapshot_hash:
                raise SourceSnapshotError("archive_receipt_snapshot_invalid")
            source_records = _read_source_records(
                filesystem, source_directory, tuple(range(1, 33)),
            )
            if source_records[:4] != snapshot.frozen_records:
                raise SourceSnapshotError("frozen_source_drift")
            files, chapter_texts = _read_archive_files_from_filesystem(
                filesystem, expected_root, snapshot,
            )
            if len(files) - 1 != receipt.verified_file_count or _archive_hash(files) != receipt.archive_hash:
                raise SourceSnapshotError("archive_hash_drift")
            return snapshot, chapter_texts
    finally:
        filesystem.close()


def _read_archive_files_from_filesystem(
    filesystem: TrustedStoreFilesystem,
    archive_root: Path,
    snapshot: SourceEditionSnapshot,
) -> tuple[list[tuple[str, bytes]], dict[int, tuple[str, ...]]]:
    _require_exact_archive_tree(filesystem, archive_root, snapshot)
    snapshot_bytes = filesystem.read_bytes(archive_root / "snapshot.json")
    if snapshot_bytes != _snapshot_file_bytes(snapshot):
        raise SourceSnapshotError("archive_hash_drift")
    files = [("snapshot.json", snapshot_bytes)]
    chapter_texts: dict[int, tuple[str, ...]] = {}
    for record in snapshot.migration_records:
        path = archive_root / "final_chapters" / Path(record.relative_path).name
        payload = filesystem.read_bytes(path)
        if _sha256(payload) != record.content_hash:
            raise SourceSnapshotError("archive_hash_drift")
        try:
            paragraphs = _paragraphs(payload.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise SourceSnapshotError("archive_utf8_invalid") from error
        actual_fragments = tuple(
            SourceFragment(
                record.chapter_number,
                index,
                index,
                _sha256(text.encode("utf-8")),
            )
            for index, text in enumerate(paragraphs, start=1)
        )
        actual_record = SourceChapterRecord(
            record.chapter_number,
            record.relative_path,
            _sha256(payload),
            actual_fragments,
        )
        if actual_record != record:
            if tuple(fragment.text_hash for fragment in actual_fragments) != tuple(
                fragment.text_hash for fragment in record.paragraph_hashes
            ):
                raise SourceSnapshotError("archive_paragraph_hash_drift")
            raise SourceSnapshotError("archive_paragraph_locator_drift")
        chapter_texts[record.chapter_number] = paragraphs
        files.append((f"final_chapters/{path.name}", payload))
    _IO_HOOK("before_archive_verify_return", archive_root)
    _require_exact_archive_tree(filesystem, archive_root, snapshot)
    for relative_path, expected_payload in files:
        path = archive_root / relative_path
        if filesystem.read_bytes(path) != expected_payload:
            raise SourceSnapshotError("archive_hash_drift")
    _require_exact_archive_tree(filesystem, archive_root, snapshot)
    _IO_HOOK("after_archive_final_scan", archive_root)
    _require_exact_archive_tree(filesystem, archive_root, snapshot)
    return files, chapter_texts


def _validate_request(project_root: Path, frozen_through_chapter: int, source_chapters: range) -> tuple[Path, Path]:
    if frozen_through_chapter != 4 or source_chapters != range(5, 33):
        raise SourceSnapshotError("invalid_snapshot_range")
    root = _absolute_root(project_root)
    source_directory = root / "production" / "final_chapters"
    _require_existing_directory(source_directory, "source_directory_invalid")
    return root, source_directory


def _validate_snapshot_shape(root: Path, snapshot: SourceEditionSnapshot) -> None:
    records = (*snapshot.frozen_records, *snapshot.migration_records)
    if snapshot.project_id != root.name or snapshot.frozen_through_chapter != 4:
        raise SourceSnapshotError("snapshot_binding_invalid")
    if tuple(record.chapter_number for record in snapshot.frozen_records) != tuple(range(1, 5)):
        raise SourceSnapshotError("snapshot_records_invalid")
    if tuple(record.chapter_number for record in snapshot.migration_records) != tuple(range(5, 33)):
        raise SourceSnapshotError("snapshot_records_invalid")
    identity = _sha256(_canonical(_records_payload(records)))
    if snapshot.source_edition_id != f"source-edition-{identity[:16]}":
        raise SourceSnapshotError("snapshot_edition_invalid")
    payload = _snapshot_payload(snapshot, include_hash=False)
    if _sha256(_canonical(payload)) != snapshot.snapshot_hash:
        raise SourceSnapshotError("snapshot_hash_invalid")


def _read_source_records(
    filesystem: TrustedStoreFilesystem, source_directory: Path, expected_numbers: tuple[int, ...],
) -> tuple[SourceChapterRecord, ...]:
    found: dict[int, str] = {}
    for name in filesystem.list_names(source_directory):
        match = _CHAPTER_NAME.fullmatch(name)
        if match is None:
            continue
        number = int(match.group(1))
        canonical = f"chapter_{number:03}.md"
        if number in found:
            raise SourceSnapshotError("chapter_duplicate")
        if name != canonical:
            if number in expected_numbers:
                raise SourceSnapshotError("chapter_duplicate")
            raise SourceSnapshotError("chapter_path_invalid")
        found[number] = name
    expected = set(expected_numbers)
    if expected - set(found):
        raise SourceSnapshotError("chapter_missing")
    if set(found) - expected:
        raise SourceSnapshotError("chapter_out_of_range")
    records = []
    for number in expected_numbers:
        path = source_directory / found[number]
        raw = filesystem.read_bytes(path)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SourceSnapshotError("source_utf8_invalid") from error
        fragments = tuple(
            SourceFragment(number, index, index, _sha256(paragraph.encode("utf-8")))
            for index, paragraph in enumerate(_paragraphs(text), start=1)
        )
        records.append(SourceChapterRecord(
            number, _CANONICAL_CHAPTER.format(number), _sha256(raw), fragments,
        ))
    return tuple(records)


def _paragraphs(text: str) -> tuple[str, ...]:
    # 连续的空白行（包括混合空格/制表符）统一作为段落边界，同时保留段落正文末尾换行。
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return tuple(
        part for part in re.split(r"\n[ \t]*(?:\n[ \t]*)+", normalized)
        if part.strip(" \t\n")
    )


def _require_exact_archive_tree(
    filesystem: TrustedStoreFilesystem,
    archive_root: Path,
    snapshot: SourceEditionSnapshot,
) -> None:
    expected_chapters = {
        Path(record.relative_path).name
        for record in snapshot.migration_records
    }
    root_names = set(filesystem.list_names(archive_root))
    if root_names != {"final_chapters", "snapshot.json"}:
        raise SourceSnapshotError("archive_tree_drift")
    _IO_HOOK("between_archive_tree_scans", archive_root)
    chapter_names = set(filesystem.list_names(archive_root / "final_chapters"))
    if chapter_names != expected_chapters:
        raise SourceSnapshotError("archive_tree_drift")
    for name in chapter_names:
        filesystem.require_regular_entry(archive_root / "final_chapters" / name, "archive chapter")
    filesystem.require_regular_entry(archive_root / "snapshot.json", "archive snapshot")
    if set(filesystem.list_names(archive_root)) != root_names:
        raise SourceSnapshotError("archive_tree_drift")
    if set(filesystem.list_names(archive_root / "final_chapters")) != chapter_names:
        raise SourceSnapshotError("archive_tree_drift")


def _publish_directory_noreplace(
    filesystem: TrustedStoreFilesystem,
    source: Path,
    target: Path,
    expected_identity: tuple[int, int],
) -> None:
    parent_handle = filesystem._directory_handle(source.parent)
    if os.name == "nt":
        import creative_os.domains.contract_record_win32 as win32

        handle = win32.open_file(
            source,
            win32._DELETE | win32._GENERIC_READ,
            win32._FILE_SHARE_READ | win32._FILE_SHARE_WRITE | win32._FILE_SHARE_DELETE,
            win32._OPEN_EXISTING,
            win32._FILE_FLAG_BACKUP_SEMANTICS | win32._FILE_FLAG_OPEN_REPARSE_POINT,
        )
        try:
            info = win32.information(handle)
            identity = (
                info.dwVolumeSerialNumber,
                (info.nFileIndexHigh << 32) | info.nFileIndexLow,
            )
            if identity != expected_identity:
                raise SourceSnapshotError("temporary_archive_identity_changed")
            if not info.dwFileAttributes & win32.FILE_ATTRIBUTE_DIRECTORY:
                raise SourceSnapshotError("temporary_archive_invalid")
            if info.dwFileAttributes & win32.FILE_ATTRIBUTE_REPARSE_POINT:
                raise SourceSnapshotError("temporary_archive_invalid")
            win32.rename_handle(handle, target, replace=False)
        finally:
            win32.close_handle(handle)
        return
    if not __import__("sys").platform.startswith("linux"):
        raise SourceSnapshotError("archive_publish_noreplace_unsupported")
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise SourceSnapshotError("archive_publish_noreplace_unsupported")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(parent_handle, os.fsencode(source.name), parent_handle, os.fsencode(target.name), 1)
    if result == 0:
        return
    code = ctypes.get_errno()
    if code == errno.EEXIST:
        raise FileExistsError(code, os.strerror(code), target.name)
    raise OSError(code, os.strerror(code), target.name)


def _retract_own_archive(
    archive_root: Path,
    recovery_root: Path,
    expected_identity: tuple[int, int],
) -> None:
    if os.name == "nt":
        import creative_os.domains.contract_record_win32 as win32

        handle = win32.open_file(
            archive_root,
            win32._DELETE | win32._GENERIC_READ,
            win32._FILE_SHARE_READ | win32._FILE_SHARE_WRITE | win32._FILE_SHARE_DELETE,
            win32._OPEN_EXISTING,
            win32._FILE_FLAG_BACKUP_SEMANTICS | win32._FILE_FLAG_OPEN_REPARSE_POINT,
        )
        try:
            info = win32.information(handle)
            identity = (
                info.dwVolumeSerialNumber,
                (info.nFileIndexHigh << 32) | info.nFileIndexLow,
            )
            if identity != expected_identity:
                raise SourceSnapshotError("archive_rollback_identity_changed")
            win32.rename_handle(handle, recovery_root, replace=False)
        finally:
            win32.close_handle(handle)
        return
    info = os.lstat(archive_root)
    if (info.st_dev, info.st_ino) != expected_identity or not stat.S_ISDIR(info.st_mode):
        raise SourceSnapshotError("archive_rollback_identity_changed")
    os.rename(archive_root, recovery_root)


def _source_filesystem(root: Path, source_directory: Path) -> TrustedStoreFilesystem:
    return TrustedStoreFilesystem(
        root,
        (source_directory,),
        source_directory / ".source-snapshot.lock",
        error_type=SourceSnapshotError,
        conflict_type=SourceSnapshotError,
        hook=_IO_HOOK,
    )


def _absolute_root(project_root: Path) -> Path:
    root = Path(project_root).absolute()
    _require_existing_directory(root, "project_root_invalid")
    return root


def _require_existing_directory(path: Path, error: str) -> None:
    try:
        info = os.lstat(path)
    except OSError as cause:
        raise SourceSnapshotError(error) from cause
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise SourceSnapshotError(error)


def _require_safe_archive_target(root: Path, archive_root: Path) -> None:
    try:
        archive_root.relative_to(root / _ARCHIVE_PREFIX)
    except ValueError as cause:
        raise SourceSnapshotError("archive_path_escape") from cause
    if _entry_exists(archive_root):
        info = os.lstat(archive_root)
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise SourceSnapshotError("archive_root_invalid")


def _entry_exists(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _snapshot_file_bytes(snapshot: SourceEditionSnapshot) -> bytes:
    return _canonical(_snapshot_payload(snapshot, include_hash=True)) + b"\n"


def _decode_snapshot_file(payload: bytes) -> SourceEditionSnapshot:
    try:
        text = payload.decode("utf-8")
        raw = json.loads(text, object_pairs_hook=_strict_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError, SourceSnapshotError) as error:
        raise SourceSnapshotError("snapshot_json_invalid") from error
    if not isinstance(raw, dict) or set(raw) != {
        "source_edition_id",
        "project_id",
        "frozen_through_chapter",
        "frozen_records",
        "migration_records",
        "snapshot_hash",
    }:
        raise SourceSnapshotError("snapshot_json_invalid")
    try:
        snapshot = SourceEditionSnapshot(
            source_edition_id=_strict_str(raw["source_edition_id"]),
            project_id=_strict_str(raw["project_id"]),
            frozen_through_chapter=_strict_int(raw["frozen_through_chapter"]),
            frozen_records=_decode_records(raw["frozen_records"]),
            migration_records=_decode_records(raw["migration_records"]),
            snapshot_hash=_strict_str(raw["snapshot_hash"]),
        )
    except (KeyError, TypeError, ValueError, SourceSnapshotError) as error:
        raise SourceSnapshotError("snapshot_json_invalid") from error
    if payload != _snapshot_file_bytes(snapshot):
        raise SourceSnapshotError("snapshot_json_invalid")
    return snapshot


def _decode_records(value: object) -> tuple[SourceChapterRecord, ...]:
    if not isinstance(value, list):
        raise SourceSnapshotError("snapshot_json_invalid")
    result = []
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != {
            "chapter_number", "relative_path", "content_hash", "paragraph_hashes",
        }:
            raise SourceSnapshotError("snapshot_json_invalid")
        fragments_raw = raw["paragraph_hashes"]
        if not isinstance(fragments_raw, list):
            raise SourceSnapshotError("snapshot_json_invalid")
        fragments = []
        for fragment in fragments_raw:
            if not isinstance(fragment, dict) or set(fragment) != {
                "source_chapter", "paragraph_start", "paragraph_end", "text_hash",
            }:
                raise SourceSnapshotError("snapshot_json_invalid")
            fragments.append(SourceFragment(
                _strict_int(fragment["source_chapter"]),
                _strict_int(fragment["paragraph_start"]),
                _strict_int(fragment["paragraph_end"]),
                _strict_str(fragment["text_hash"]),
            ))
        result.append(SourceChapterRecord(
            _strict_int(raw["chapter_number"]),
            _strict_str(raw["relative_path"]),
            _strict_str(raw["content_hash"]),
            tuple(fragments),
        ))
    return tuple(result)


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SourceSnapshotError("duplicate_json_key")
        result[key] = value
    return result


def _strict_str(value: object) -> str:
    if not isinstance(value, str):
        raise SourceSnapshotError("snapshot_json_invalid")
    return value


def _strict_int(value: object) -> int:
    if type(value) is not int:
        raise SourceSnapshotError("snapshot_json_invalid")
    return value


def _record_by_number(snapshot: SourceEditionSnapshot, chapter_number: int) -> SourceChapterRecord:
    for record in (*snapshot.frozen_records, *snapshot.migration_records):
        if record.chapter_number == chapter_number:
            return record
    raise SourceSnapshotError("source_chapter_invalid")


def _snapshot_payload(snapshot: SourceEditionSnapshot, *, include_hash: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_edition_id": snapshot.source_edition_id,
        "project_id": snapshot.project_id,
        "frozen_through_chapter": snapshot.frozen_through_chapter,
        "frozen_records": _records_payload(snapshot.frozen_records),
        "migration_records": _records_payload(snapshot.migration_records),
    }
    if include_hash:
        payload["snapshot_hash"] = snapshot.snapshot_hash
    return payload


def _records_payload(records: tuple[SourceChapterRecord, ...]) -> list[dict[str, object]]:
    return [
        {
            "chapter_number": record.chapter_number,
            "relative_path": record.relative_path,
            "content_hash": record.content_hash,
            "paragraph_hashes": [
                {
                    "source_chapter": fragment.source_chapter,
                    "paragraph_start": fragment.paragraph_start,
                    "paragraph_end": fragment.paragraph_end,
                    "text_hash": fragment.text_hash,
                }
                for fragment in record.paragraph_hashes
            ],
        }
        for record in records
    ]


def _archive_hash(files: list[tuple[str, bytes]]) -> str:
    return _sha256(_canonical([
        {"path": path, "content_hash": _sha256(payload)}
        for path, payload in sorted(files)
    ]))


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_hash(value: str) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _is_project_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value not in {".", ".."}
        and not Path(value).is_absolute()
        and "/" not in value
        and "\\" not in value
    )
