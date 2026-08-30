import json
import os
from dataclasses import replace

import pytest

import creative_os.runtime.publication_migration_store as migration_store
from creative_os.domains.project_authority_transaction import ProjectAuthorityTransaction
from creative_os.domains.publication_migration_codec import manifest_hash
from creative_os.domains.publication_migration_model import (
    CheckpointPhase,
    ManifestStatus,
    MigrationCheckpoint,
    PublicationChapterEntry,
    PublicationChapterMigrationManifest,
    PublicationLengthPolicy,
    SourceFragment,
)
from creative_os.runtime.publication_migration_store import (
    PublicationMigrationConflictError,
    PublicationMigrationIntegrityError,
    PublicationMigrationStore,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def make_manifest(*, migration_id="migration-1", status=ManifestStatus.VERIFIED,
                  target_edition_id="edition-target"):
    value = PublicationChapterMigrationManifest(
        migration_id=migration_id,
        project_id="project-1",
        source_edition_id="edition-source",
        target_edition_id=target_edition_id,
        source_start=1,
        source_end=2,
        frozen_through_chapter=0,
        entries=(
            PublicationChapterEntry(1, (SourceFragment(1, 1, 2, HASH_A),)),
            PublicationChapterEntry(2, (SourceFragment(2, 1, 2, HASH_B),)),
        ),
        omissions=(),
        length_policy=PublicationLengthPolicy(),
        checkpoints=(),
        status=status,
        approved_by="editor" if status is not ManifestStatus.CANDIDATE else "",
        approved_at="2026-08-28T12:00:00+00:00" if status is not ManifestStatus.CANDIDATE else "",
    )
    return replace(value, manifest_hash=manifest_hash(value))


def make_checkpoint(*, migration_id="migration-1", phase=CheckpointPhase.SNAPSHOT_VERIFIED,
                    batch_id="batch-1", output_fingerprint=""):
    return MigrationCheckpoint(
        migration_id=migration_id,
        phase=phase,
        batch_id=batch_id,
        input_fingerprint=HASH_C,
        output_fingerprint=output_fingerprint,
    )


def test_append_reopen_load_exact_and_recover_are_append_only(tmp_path):
    store = PublicationMigrationStore(tmp_path)
    manifest = make_manifest()
    checkpoint = make_checkpoint()

    assert store.append_manifest(manifest) == manifest.manifest_hash
    assert len(store.append_checkpoint(checkpoint)) == 64

    reopened = PublicationMigrationStore(tmp_path)
    assert reopened.load_exact("migration-1", manifest.manifest_hash) == manifest
    recovery = reopened.recover("migration-1")
    assert recovery.manifests == (manifest,)
    assert recovery.checkpoints == (checkpoint,)


def test_exact_repeat_is_idempotent_but_changed_checkpoint_conflicts(tmp_path):
    store = PublicationMigrationStore(tmp_path)
    manifest = make_manifest()
    checkpoint = make_checkpoint()

    assert store.append_manifest(manifest) == store.append_manifest(manifest)
    assert store.append_checkpoint(checkpoint) == store.append_checkpoint(checkpoint)
    with pytest.raises(PublicationMigrationConflictError):
        store.append_checkpoint(replace(checkpoint, output_fingerprint=HASH_D))


@pytest.mark.parametrize("tamper", ["payload", "envelope", "head"])
def test_load_exact_rejects_tampered_payload_envelope_and_head(tmp_path, tamper):
    store = PublicationMigrationStore(tmp_path)
    manifest = make_manifest()
    store.append_manifest(manifest)

    if tamper == "head":
        head = json.loads(store.head_path.read_text(encoding="utf-8"))
        head["head_hash"] = HASH_D
        store.head_path.write_text(json.dumps(head) + "\n", encoding="utf-8")
    else:
        envelope = json.loads(store.records_path.read_text(encoding="utf-8"))
        if tamper == "payload":
            envelope["payload"]["migration_id"] = "tampered-migration"
        else:
            envelope["envelope_hash"] = HASH_D
        store.records_path.write_text(json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(PublicationMigrationIntegrityError):
        PublicationMigrationStore(tmp_path).load_exact("migration-1", manifest.manifest_hash)


def test_recover_rejects_truncated_jsonl(tmp_path):
    store = PublicationMigrationStore(tmp_path)
    store.append_manifest(make_manifest())
    store.records_path.write_bytes(store.records_path.read_bytes().rstrip(b"\n"))

    with pytest.raises(PublicationMigrationIntegrityError):
        PublicationMigrationStore(tmp_path).recover("migration-1")


def test_prepared_journal_recovers_the_pending_append(tmp_path, monkeypatch):
    store = PublicationMigrationStore(tmp_path)
    manifest = make_manifest()

    def fail_once(event, _path):
        if event == "before_records_replace":
            raise OSError("injected append interruption")

    monkeypatch.setattr(migration_store, "_IO_HOOK", fail_once)
    with pytest.raises(OSError, match="interruption"):
        store.append_manifest(manifest)
    monkeypatch.setattr(migration_store, "_IO_HOOK", lambda *_args: None)

    assert PublicationMigrationStore(tmp_path).load_exact("migration-1", manifest.manifest_hash) == manifest


@pytest.mark.parametrize("failure_event", [
    "before_replace:journal.json",
    "before_records_replace",
    "before_replace:head.json",
    "before_journal_unlink",
])
def test_manifest_append_crash_points_are_recoverable(tmp_path, monkeypatch, failure_event):
    store = PublicationMigrationStore(tmp_path)
    manifest = make_manifest()

    def fail_once(event, _path):
        if event == failure_event:
            raise OSError("injected manifest interruption")

    monkeypatch.setattr(migration_store, "_IO_HOOK", fail_once)
    with pytest.raises(OSError, match="manifest interruption"):
        store.append_manifest(manifest)
    monkeypatch.setattr(migration_store, "_IO_HOOK", lambda *_args: None)

    recovered = PublicationMigrationStore(tmp_path).recover("migration-1")
    if failure_event == "before_replace:journal.json":
        assert recovered.manifests == ()
    else:
        assert recovered.manifests == (manifest,)


def test_load_exact_rejects_wrong_migration_or_hash(tmp_path):
    store = PublicationMigrationStore(tmp_path)
    manifest = make_manifest()
    store.append_manifest(manifest)

    with pytest.raises(PublicationMigrationIntegrityError):
        store.load_exact("other-migration", manifest.manifest_hash)
    with pytest.raises(PublicationMigrationIntegrityError):
        store.load_exact("migration-1", HASH_D)


def test_activation_requires_verified_manifest_and_real_lock_context(tmp_path):
    store = PublicationMigrationStore(tmp_path)
    candidate = make_manifest(status=ManifestStatus.CANDIDATE)
    store.append_manifest(candidate)

    with pytest.raises(PublicationMigrationIntegrityError):
        store.activate_verified_manifest(candidate.manifest_hash, object())

    tx = ProjectAuthorityTransaction(tmp_path)
    with tx.acquire() as context:
        with pytest.raises(PublicationMigrationIntegrityError):
            store.activate_verified_manifest(candidate.manifest_hash, context)


@pytest.mark.parametrize("failure_event", [
    "before_replace:pointer_journal.json",
    "before_replace:active_edition.json",
    "before_pointer_journal_unlink",
])
def test_activation_crash_points_recover_to_one_complete_pointer(tmp_path, monkeypatch, failure_event):
    store = PublicationMigrationStore(tmp_path)
    manifest = make_manifest()
    store.append_manifest(manifest)
    tx = ProjectAuthorityTransaction(tmp_path)

    def fail_once(event, _path):
        if event == failure_event:
            raise OSError("injected pointer interruption")

    monkeypatch.setattr(migration_store, "_IO_HOOK", fail_once)
    with tx.acquire() as context:
        with pytest.raises(OSError, match="pointer interruption"):
            store.activate_verified_manifest(manifest.manifest_hash, context)
    monkeypatch.setattr(migration_store, "_IO_HOOK", lambda *_args: None)

    active = PublicationMigrationStore(tmp_path).load_active_edition()
    if failure_event == "before_replace:pointer_journal.json":
        assert active is None
        assert not store.active_edition_path.exists()
    else:
        assert active.manifest_hash == manifest.manifest_hash
        assert active.target_edition_id == "edition-target"
        assert list(store.root.glob("active_edition*.json")) == [store.active_edition_path]


def test_activation_switches_the_single_active_pointer(tmp_path):
    store = PublicationMigrationStore(tmp_path)
    first = make_manifest(migration_id="migration-1", target_edition_id="edition-one")
    second = make_manifest(migration_id="migration-2", target_edition_id="edition-two")
    store.append_manifest(first)
    store.append_manifest(second)
    tx = ProjectAuthorityTransaction(tmp_path)

    with tx.acquire() as context:
        store.activate_verified_manifest(first.manifest_hash, context)
        active = store.activate_verified_manifest(second.manifest_hash, context)

    assert active.manifest_hash == second.manifest_hash
    assert store.load_active_edition() == active


def test_store_rejects_symlinked_authority_directory_without_writing_outside(tmp_path):
    outside = tmp_path / "outside-authority"
    outside.mkdir()
    metadata = tmp_path / ".creative_os"
    metadata.mkdir()
    store_root = metadata / "publication_migration"
    try:
        store_root.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink unavailable: {error}")

    with pytest.raises(PublicationMigrationIntegrityError):
        PublicationMigrationStore(tmp_path).append_manifest(make_manifest())

    assert tuple(outside.iterdir()) == ()


@pytest.mark.skipif(os.name != "nt", reason="Windows reparse simulation")
def test_store_rejects_reparse_authority_directory_before_any_write(tmp_path, monkeypatch):
    import creative_os.domains.contract_record_filesystem as filesystem_module

    store = PublicationMigrationStore(tmp_path)
    handle = store._filesystem._directory_handles[store.root]
    original = filesystem_module._win_handle_information
    info = original(handle)
    identity = (info.dwVolumeSerialNumber, (info.nFileIndexHigh << 32) | info.nFileIndexLow)

    def report_reparse(candidate_handle):
        candidate = original(candidate_handle)
        candidate_identity = (
            candidate.dwVolumeSerialNumber,
            (candidate.nFileIndexHigh << 32) | candidate.nFileIndexLow,
        )
        if candidate_identity == identity:
            candidate.dwFileAttributes |= 0x400
        return candidate

    monkeypatch.setattr(filesystem_module, "_win_handle_information", report_reparse)
    with pytest.raises(PublicationMigrationIntegrityError):
        store.append_manifest(make_manifest())


def test_directory_replacement_at_write_boundary_never_redirects_authority_store(tmp_path, monkeypatch):
    store = PublicationMigrationStore(tmp_path)
    store.append_manifest(make_manifest())
    backup = tmp_path / "publication-migration-backup"
    outside = tmp_path / "outside-replacement"
    outside.mkdir()
    redirected = False
    protected = False

    def replace_store_directory(event, _path):
        nonlocal protected, redirected
        if event != "before_records_replace":
            return
        try:
            store.root.replace(backup)
        except PermissionError:
            protected = True
            return
        try:
            store.root.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            pytest.skip(f"symlink unavailable: {error}")
        redirected = True

    monkeypatch.setattr(migration_store, "_IO_HOOK", replace_store_directory)
    try:
        store.append_checkpoint(make_checkpoint())
    except PublicationMigrationIntegrityError:
        pass

    assert protected or redirected
    assert tuple(outside.iterdir()) == ()


@pytest.mark.skipif(os.name != "nt", reason="Windows durability adapter")
def test_windows_publication_flushes_persistent_directory_and_published_file(tmp_path, monkeypatch):
    calls = []

    def capture_flush(handle):
        calls.append(handle)
        if len(calls) % 2 == 1:
            raise PermissionError(13, "directory flush denied")

    monkeypatch.setattr(migration_store, "_win_flush", capture_flush, raising=False)
    PublicationMigrationStore(tmp_path).append_manifest(make_manifest())

    assert len(calls) >= 2


@pytest.mark.skipif(os.name != "nt", reason="Windows durability adapter")
def test_windows_publication_opens_the_published_file_with_flush_capability(tmp_path, monkeypatch):
    store = PublicationMigrationStore(tmp_path)
    opened_for_write = []
    original_open = store._filesystem._open_regular_file

    def capture_open(path, *, write):
        if path.parent == store.root:
            opened_for_write.append(write)
        return original_open(path, write=write)

    monkeypatch.setattr(store._filesystem, "_open_regular_file", capture_open)
    monkeypatch.setattr(migration_store, "_win_flush", lambda _handle: None, raising=False)
    store.append_manifest(make_manifest())
    opened_for_write.clear()
    store._flush_published_file(store.head_path)

    assert opened_for_write == [True]


@pytest.mark.skipif(os.name != "nt", reason="Windows durability adapter")
def test_windows_access_denied_directory_flush_falls_back_to_published_file(monkeypatch):
    calls = []

    def flush(handle):
        calls.append(handle)
        if handle == 11:
            raise PermissionError(13, "access denied")

    monkeypatch.setattr(migration_store, "_win_flush", flush)
    migration_store._flush_windows_publication(11, 22)

    assert calls == [11, 22]


@pytest.mark.skipif(os.name != "nt", reason="Windows durability adapter")
def test_windows_unknown_directory_flush_error_is_not_downgraded(monkeypatch):
    def flush(handle):
        if handle == 11:
            raise OSError(1117, "device I/O error")

    monkeypatch.setattr(migration_store, "_win_flush", flush)
    with pytest.raises(OSError, match="device I/O error"):
        migration_store._flush_windows_publication(11, 22)


@pytest.mark.skipif(os.name != "nt", reason="Windows durability adapter")
def test_windows_published_file_flush_error_is_not_downgraded(monkeypatch):
    def flush(handle):
        if handle == 11:
            raise PermissionError(13, "access denied")
        raise OSError(1117, "published file I/O error")

    monkeypatch.setattr(migration_store, "_win_flush", flush)
    with pytest.raises(OSError, match="published file I/O error"):
        migration_store._flush_windows_publication(11, 22)


@pytest.mark.parametrize("failure_event", [
    "before_replace:pointer_journal.json",
    "before_replace:active_edition.json",
    "before_pointer_journal_unlink",
])
def test_existing_pointer_cas_crash_recovers_only_complete_old_or_new_pointer(
    tmp_path, monkeypatch, failure_event,
):
    store = PublicationMigrationStore(tmp_path)
    first = make_manifest(migration_id="migration-a", target_edition_id="edition-a")
    second = make_manifest(migration_id="migration-b", target_edition_id="edition-b")
    store.append_manifest(first)
    store.append_manifest(second)
    tx = ProjectAuthorityTransaction(tmp_path)
    with tx.acquire() as context:
        old = store.activate_verified_manifest(first.manifest_hash, context)

    def fail_once(event, _path):
        if event == failure_event:
            raise OSError("injected existing-pointer interruption")

    monkeypatch.setattr(migration_store, "_IO_HOOK", fail_once)
    with tx.acquire() as context:
        with pytest.raises(OSError, match="existing-pointer interruption"):
            store.activate_verified_manifest(second.manifest_hash, context)
    monkeypatch.setattr(migration_store, "_IO_HOOK", lambda *_args: None)

    reopened = PublicationMigrationStore(tmp_path)
    first_read = reopened.load_active_edition()
    second_read = reopened.load_active_edition()
    expected_new = type(old)("migration-b", second.manifest_hash, "edition-b")
    assert first_read in (old, expected_new)
    assert second_read == first_read
    assert list(store.root.glob("active_edition*.json")) == [store.active_edition_path]
