from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path

from creative_os.domains.project_authority import project_authority_lock
from creative_os.domains.contract_record_filesystem import TrustedStoreFilesystem
from creative_os.domains.project_authority_transaction import (
    LockContext,
    ProjectAuthorityLockError,
    ProjectAuthorityTransaction,
)
from creative_os.domains.publication_migration_codec import (
    decode_manifest,
    encode_manifest,
    manifest_hash,
)
from creative_os.domains.publication_migration_model import (
    CheckpointPhase,
    ManifestStatus,
    MigrationCheckpoint,
    PublicationChapterMigrationManifest,
)

if os.name == "nt":
    from creative_os.domains.contract_record_win32 import flush as _win_flush
    from creative_os.domains.contract_record_win32 import mark_delete as _win_mark_delete


class PublicationMigrationIntegrityError(ValueError):
    pass


class PublicationMigrationConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ActiveEditionPointer:
    migration_id: str
    manifest_hash: str
    target_edition_id: str


@dataclass(frozen=True, slots=True)
class MigrationRecoveryState:
    migration_id: str
    manifests: tuple[PublicationChapterMigrationManifest, ...]
    checkpoints: tuple[MigrationCheckpoint, ...]
    active_edition: ActiveEditionPointer | None


@dataclass(frozen=True, slots=True)
class _StoredRecord:
    kind: str
    key: tuple[str, ...]
    payload: dict[str, object]
    content_hash: str
    manifest: PublicationChapterMigrationManifest | None = None
    checkpoint: MigrationCheckpoint | None = None


def _no_io_hook(_event: str, _path: Path) -> None:
    return None


_IO_HOOK = _no_io_hook
_ZERO_HASH = "0" * 64


class PublicationMigrationStore:
    def __init__(self, root: Path) -> None:
        self.project_root = Path(root).absolute()
        self.root = self.project_root / ".creative_os" / "publication_migration"
        self.records_path = self.root / "records.jsonl"
        self.head_path = self.root / "head.json"
        self.journal_path = self.root / "journal.json"
        self.active_edition_path = self.root / "active_edition.json"
        self.pointer_journal_path = self.root / "pointer_journal.json"
        self._transaction = ProjectAuthorityTransaction(self.project_root)
        self._filesystem = TrustedStoreFilesystem(
            self.project_root,
            (self.root,),
            self.root / ".publication-migration.lock",
            error_type=PublicationMigrationIntegrityError,
            conflict_type=PublicationMigrationConflictError,
            hook=lambda event, path: _IO_HOOK(event, path),
        )

    def append_manifest(self, manifest: PublicationChapterMigrationManifest) -> str:
        if not isinstance(manifest, PublicationChapterMigrationManifest):
            raise TypeError("append_manifest requires PublicationChapterMigrationManifest")
        expected_hash = manifest_hash(manifest)
        if manifest.manifest_hash != expected_hash:
            raise PublicationMigrationIntegrityError("manifest_hash_invalid")
        payload = {
            "kind": "manifest",
            "migration_id": manifest.migration_id,
            "manifest_hash": manifest.manifest_hash,
            "manifest": json.loads(encode_manifest(manifest)),
        }
        record = self._manifest_record(payload)
        with project_authority_lock(self.project_root):
            self._append_record_locked(record)
        return manifest.manifest_hash

    def load_exact(self, migration_id: str, manifest_hash_value: str) -> PublicationChapterMigrationManifest:
        _require_nonempty_string(migration_id, "migration_id")
        _require_hash(manifest_hash_value)
        with project_authority_lock(self.project_root):
            records = self._recover_records_locked()
            self._recover_pointer_locked(records)
            for record in records:
                if (record.kind == "manifest" and record.manifest is not None
                        and record.manifest.migration_id == migration_id
                        and record.manifest.manifest_hash == manifest_hash_value):
                    return record.manifest
        raise PublicationMigrationIntegrityError("manifest_exact_not_found")

    def append_checkpoint(self, checkpoint: MigrationCheckpoint) -> str:
        if not isinstance(checkpoint, MigrationCheckpoint):
            raise TypeError("append_checkpoint requires MigrationCheckpoint")
        payload = {
            "kind": "checkpoint",
            "migration_id": checkpoint.migration_id,
            "checkpoint": {
                "batch_id": checkpoint.batch_id,
                "error": checkpoint.error,
                "input_fingerprint": checkpoint.input_fingerprint,
                "migration_id": checkpoint.migration_id,
                "output_fingerprint": checkpoint.output_fingerprint,
                "phase": checkpoint.phase.value,
            },
        }
        record = self._checkpoint_record(payload)
        with project_authority_lock(self.project_root):
            self._append_record_locked(record)
        return record.content_hash

    def recover(self, migration_id: str) -> MigrationRecoveryState:
        _require_nonempty_string(migration_id, "migration_id")
        with project_authority_lock(self.project_root):
            records = self._recover_records_locked()
            active = self._recover_pointer_locked(records)
            manifests = tuple(record.manifest for record in records if (
                record.kind == "manifest" and record.manifest is not None
                and record.manifest.migration_id == migration_id
            ))
            checkpoints = tuple(record.checkpoint for record in records if (
                record.kind == "checkpoint" and record.checkpoint is not None
                and record.checkpoint.migration_id == migration_id
            ))
            return MigrationRecoveryState(migration_id, manifests, checkpoints, active)

    def load_active_edition(self) -> ActiveEditionPointer | None:
        with project_authority_lock(self.project_root):
            return self._recover_pointer_locked(self._recover_records_locked())

    def activate_verified_manifest(self, manifest_hash_value: str, lock_context: object) -> ActiveEditionPointer:
        _require_hash(manifest_hash_value)
        self._assert_real_lock_context(lock_context)
        records = self._recover_records_locked()
        active = self._recover_pointer_locked(records)
        manifest = next((record.manifest for record in records if (
            record.kind == "manifest" and record.manifest is not None
            and record.manifest.manifest_hash == manifest_hash_value
        )), None)
        if manifest is None:
            raise PublicationMigrationIntegrityError("manifest_exact_not_found")
        if manifest.status is not ManifestStatus.VERIFIED:
            raise PublicationMigrationIntegrityError("manifest_not_verified")
        pointer = ActiveEditionPointer(
            migration_id=manifest.migration_id,
            manifest_hash=manifest.manifest_hash,
            target_edition_id=manifest.target_edition_id,
        )
        if active == pointer:
            return pointer
        self._switch_pointer_locked(active, pointer, records)
        return pointer

    def _assert_real_lock_context(self, lock_context: object) -> None:
        if type(lock_context) is not LockContext:
            raise PublicationMigrationIntegrityError("lock_context_invalid")
        try:
            self._transaction.assert_context(lock_context)
        except ProjectAuthorityLockError as error:
            raise PublicationMigrationIntegrityError("lock_context_invalid") from error

    def _append_record_locked(self, candidate: _StoredRecord) -> None:
        records = self._recover_records_locked()
        self._recover_pointer_locked(records)
        existing = next((record for record in records if record.key == candidate.key), None)
        if existing is not None:
            if existing.content_hash == candidate.content_hash:
                return
            raise PublicationMigrationConflictError("logical_append_conflict")
        envelopes = self._read_envelopes_only()
        envelope = _record_envelope(candidate.payload, len(envelopes) + 1,
                                    envelopes[-1]["envelope_hash"] if envelopes else _ZERO_HASH)
        self._atomic_json(self.journal_path, {"state": "prepared", "envelope": envelope})
        self._replace_records(envelope)
        self._atomic_json(self.head_path, _head(envelope))
        _IO_HOOK("before_journal_unlink", self.journal_path)
        self._unlink_file(self.journal_path)

    def _recover_records_locked(self) -> tuple[_StoredRecord, ...]:
        self._filesystem.validate_all()
        records, envelopes = self._read_records()
        actual = _actual_head(envelopes)
        persisted = self._read_head()
        if self._filesystem.exists_regular(self.journal_path):
            try:
                journal = _load_canonical_json(self._filesystem.read_bytes(self.journal_path))
                if not isinstance(journal, dict) or set(journal) != {"state", "envelope"} or journal["state"] != "prepared":
                    raise ValueError("invalid journal")
                pending = _record_from_envelope(journal["envelope"])
                envelope = journal["envelope"]
            except Exception as error:
                raise PublicationMigrationIntegrityError("tampered_journal") from error
            prior = {"count": envelope["sequence"] - 1, "head_hash": envelope["previous_hash"]}
            existing = next((record for record in records if record.key == pending.key), None)
            if existing is not None:
                if existing.content_hash != pending.content_hash or actual != _head(envelope):
                    raise PublicationMigrationIntegrityError("tampered_journal")
                if persisted not in (actual, prior) and not (
                        persisted is None and prior["count"] == 0):
                    raise PublicationMigrationIntegrityError("tampered_head")
            else:
                if persisted is None:
                    persisted = {"count": 0, "head_hash": _ZERO_HASH}
                if persisted != actual or envelope["sequence"] != actual["count"] + 1 or envelope["previous_hash"] != actual["head_hash"]:
                    raise PublicationMigrationIntegrityError("tampered_journal")
                self._replace_records(envelope)
                records = (*records, pending)
                envelopes = (*envelopes, envelope)
                actual = _actual_head(envelopes)
            self._atomic_json(self.head_path, actual)
            _IO_HOOK("before_journal_unlink", self.journal_path)
            self._unlink_file(self.journal_path)
        elif persisted != actual and not (persisted is None and actual["count"] == 0):
            raise PublicationMigrationIntegrityError("tampered_head_or_records")
        return records

    def _read_records(self) -> tuple[tuple[_StoredRecord, ...], tuple[dict[str, object], ...]]:
        if not self._filesystem.exists_regular(self.records_path):
            return (), ()
        try:
            raw = self._filesystem.read_bytes(self.records_path)
            if not raw or not raw.endswith(b"\n"):
                raise ValueError("truncated records")
            records: list[_StoredRecord] = []
            envelopes: list[dict[str, object]] = []
            keys: set[tuple[str, ...]] = set()
            for line in raw.splitlines(keepends=True):
                envelope_value = _load_canonical_json(line)
                record = _record_from_envelope(envelope_value)
                if not isinstance(envelope_value, dict):
                    raise ValueError("invalid envelope")
                expected_previous = envelopes[-1]["envelope_hash"] if envelopes else _ZERO_HASH
                if (envelope_value["sequence"] != len(envelopes) + 1
                        or envelope_value["previous_hash"] != expected_previous
                        or record.key in keys):
                    raise ValueError("record chain mismatch")
                keys.add(record.key)
                records.append(record)
                envelopes.append(envelope_value)
            return tuple(records), tuple(envelopes)
        except PublicationMigrationConflictError:
            raise
        except Exception as error:
            raise PublicationMigrationIntegrityError("tampered_records") from error

    def _read_envelopes_only(self) -> tuple[dict[str, object], ...]:
        return self._read_records()[1]

    def _read_head(self) -> dict[str, object] | None:
        if not self._filesystem.exists_regular(self.head_path):
            return None
        try:
            value = _load_canonical_json(self._filesystem.read_bytes(self.head_path))
            if (not isinstance(value, dict) or set(value) != {"count", "head_hash"}
                    or type(value["count"]) is not int or value["count"] < 0):
                raise ValueError("invalid head")
            _require_hash(value["head_hash"])
            return value
        except Exception as error:
            raise PublicationMigrationIntegrityError("tampered_head") from error

    def _recover_pointer_locked(self, records: tuple[_StoredRecord, ...]) -> ActiveEditionPointer | None:
        self._filesystem.validate_all()
        active = self._read_pointer()
        active_hash = _pointer_hash(active) if active is not None else _ZERO_HASH
        if self._filesystem.exists_regular(self.pointer_journal_path):
            try:
                journal = _load_canonical_json(self._filesystem.read_bytes(self.pointer_journal_path))
                candidate, expected_hash = _pointer_from_journal(journal)
            except Exception as error:
                raise PublicationMigrationIntegrityError("tampered_pointer_journal") from error
            candidate_hash = _pointer_hash(candidate)
            if active_hash == candidate_hash:
                active = candidate
            elif active_hash == expected_hash:
                self._validate_pointer(candidate, records)
                self._write_pointer(candidate)
                active = candidate
            else:
                raise PublicationMigrationIntegrityError("pointer_compare_and_swap_conflict")
            self._validate_pointer(active, records)
            _IO_HOOK("before_pointer_journal_unlink", self.pointer_journal_path)
            self._unlink_file(self.pointer_journal_path)
        if active is not None:
            self._validate_pointer(active, records)
        return active

    def _switch_pointer_locked(self, active: ActiveEditionPointer | None,
                               candidate: ActiveEditionPointer,
                               records: tuple[_StoredRecord, ...]) -> None:
        self._validate_pointer(candidate, records)
        expected_hash = _pointer_hash(active) if active is not None else _ZERO_HASH
        journal = _pointer_journal(expected_hash, candidate)
        self._atomic_json(self.pointer_journal_path, journal)
        self._write_pointer(candidate)
        _IO_HOOK("before_pointer_journal_unlink", self.pointer_journal_path)
        self._unlink_file(self.pointer_journal_path)

    def _read_pointer(self) -> ActiveEditionPointer | None:
        if not self._filesystem.exists_regular(self.active_edition_path):
            return None
        try:
            value = _load_canonical_json(self._filesystem.read_bytes(self.active_edition_path))
            if not isinstance(value, dict) or set(value) != {"pointer", "pointer_hash"}:
                raise ValueError("invalid pointer")
            pointer = _pointer_from_payload(value["pointer"])
            if value["pointer_hash"] != _pointer_hash(pointer):
                raise ValueError("pointer hash mismatch")
            return pointer
        except Exception as error:
            raise PublicationMigrationIntegrityError("tampered_active_pointer") from error

    def _write_pointer(self, pointer: ActiveEditionPointer) -> None:
        self._atomic_json(self.active_edition_path, {
            "pointer": _pointer_payload(pointer),
            "pointer_hash": _pointer_hash(pointer),
        })

    @staticmethod
    def _validate_pointer(pointer: ActiveEditionPointer,
                          records: tuple[_StoredRecord, ...]) -> None:
        manifest = next((record.manifest for record in records if (
            record.kind == "manifest" and record.manifest is not None
            and record.manifest.migration_id == pointer.migration_id
            and record.manifest.manifest_hash == pointer.manifest_hash
        )), None)
        if manifest is None or manifest.status is not ManifestStatus.VERIFIED:
            raise PublicationMigrationIntegrityError("active_pointer_not_verified")
        if manifest.target_edition_id != pointer.target_edition_id:
            raise PublicationMigrationIntegrityError("active_pointer_binding_invalid")

    def _replace_records(self, envelope: dict[str, object]) -> None:
        self._filesystem.validate_all()
        prior = (self._filesystem.read_bytes(self.records_path)
                 if self._filesystem.exists_regular(self.records_path) else None)
        payload = (prior or b"") + _canonical(envelope) + b"\n"
        _IO_HOOK("before_records_replace", self.records_path)
        self._filesystem.atomic_write_bytes(self.records_path, payload, expected=prior)
        self._flush_published_file(self.records_path)

    def _atomic_json(self, path: Path, payload: object) -> None:
        self._filesystem.validate_all()
        expected = (self._filesystem.read_bytes(path)
                    if self._filesystem.exists_regular(path) else None)
        _IO_HOOK(f"before_replace:{path.name}", path)
        self._filesystem.atomic_write_bytes(path, _canonical(payload) + b"\n", expected=expected)
        self._flush_published_file(path)

    def _unlink_file(self, path: Path) -> None:
        self._filesystem.validate_all()
        if not self._filesystem.exists_regular(path):
            return
        handle = self._filesystem._open_regular_file(path, write=True)
        try:
            identity = self._filesystem._handle_identity(handle)
            self._filesystem._validate_named_file(path, identity)
            if os.name == "nt":
                _win_mark_delete(handle)
            else:
                os.unlink(path.name, dir_fd=self._filesystem._directory_handle(path.parent))
        finally:
            self._filesystem._close_handle(handle)
        self._filesystem.validate_all()

    def _flush_published_file(self, path: Path) -> None:
        self._filesystem.validate_all()
        handle = self._filesystem._open_regular_file(path, write=True)
        try:
            identity = self._filesystem._handle_identity(handle)
            directory_handle = self._filesystem._directory_handle(path.parent)
            if os.name == "nt":
                _flush_windows_publication(directory_handle, handle)
            else:
                os.fsync(directory_handle)
            self._filesystem._validate_named_file(path, identity)
        finally:
            self._filesystem._close_handle(handle)
        self._filesystem.validate_all()

    @staticmethod
    def _manifest_record(payload: dict[str, object]) -> _StoredRecord:
        if set(payload) != {"kind", "migration_id", "manifest_hash", "manifest"} or payload["kind"] != "manifest":
            raise ValueError("invalid manifest payload")
        migration_id = payload["migration_id"]
        manifest_hash_value = payload["manifest_hash"]
        _require_nonempty_string(migration_id, "migration_id")
        _require_hash(manifest_hash_value)
        manifest = decode_manifest(_canonical_text(payload["manifest"]))
        if (manifest.migration_id != migration_id or manifest.manifest_hash != manifest_hash_value
                or manifest_hash(manifest) != manifest_hash_value):
            raise ValueError("manifest binding invalid")
        return _StoredRecord(
            "manifest", ("manifest", migration_id, manifest_hash_value), payload,
            _hash_payload(payload), manifest=manifest,
        )

    @staticmethod
    def _checkpoint_record(payload: dict[str, object]) -> _StoredRecord:
        if set(payload) != {"kind", "migration_id", "checkpoint"} or payload["kind"] != "checkpoint":
            raise ValueError("invalid checkpoint payload")
        migration_id = payload["migration_id"]
        _require_nonempty_string(migration_id, "migration_id")
        value = payload["checkpoint"]
        if not isinstance(value, dict) or set(value) != {
            "batch_id", "error", "input_fingerprint", "migration_id", "output_fingerprint", "phase",
        } or value["migration_id"] != migration_id:
            raise ValueError("invalid checkpoint binding")
        checkpoint = MigrationCheckpoint(
            migration_id=value["migration_id"],
            phase=CheckpointPhase(value["phase"]),
            batch_id=value["batch_id"],
            input_fingerprint=value["input_fingerprint"],
            output_fingerprint=value["output_fingerprint"],
            error=value["error"],
        )
        return _StoredRecord(
            "checkpoint", ("checkpoint", checkpoint.migration_id, checkpoint.phase.value, checkpoint.batch_id),
            payload, _hash_payload(payload), checkpoint=checkpoint,
        )


def _record_envelope(payload: dict[str, object], sequence: int,
                     previous_hash: str) -> dict[str, object]:
    base = {
        "schema_version": 1,
        "sequence": sequence,
        "previous_hash": previous_hash,
        "payload_hash": _hash_payload(payload),
        "payload": payload,
    }
    return {**base, "envelope_hash": _hash_payload(base)}


def _record_from_envelope(value: object) -> _StoredRecord:
    fields = {"schema_version", "sequence", "previous_hash", "payload_hash", "payload", "envelope_hash"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("invalid envelope fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("invalid schema version")
    if type(value["sequence"]) is not int or value["sequence"] < 1:
        raise ValueError("invalid sequence")
    _require_hash(value["previous_hash"])
    _require_hash(value["payload_hash"])
    _require_hash(value["envelope_hash"])
    base = {key: value[key] for key in fields if key != "envelope_hash"}
    if value["payload_hash"] != _hash_payload(value["payload"]) or value["envelope_hash"] != _hash_payload(base):
        raise ValueError("envelope hash mismatch")
    payload = value["payload"]
    if not isinstance(payload, dict) or not isinstance(payload.get("kind"), str):
        raise ValueError("invalid payload")
    if payload["kind"] == "manifest":
        return PublicationMigrationStore._manifest_record(payload)
    if payload["kind"] == "checkpoint":
        return PublicationMigrationStore._checkpoint_record(payload)
    raise ValueError("unknown payload kind")


def _head(envelope: dict[str, object]) -> dict[str, object]:
    return {"count": envelope["sequence"], "head_hash": envelope["envelope_hash"]}


def _actual_head(envelopes: tuple[dict[str, object], ...]) -> dict[str, object]:
    return _head(envelopes[-1]) if envelopes else {"count": 0, "head_hash": _ZERO_HASH}


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_text(payload: object) -> str:
    return _canonical(payload).decode("utf-8")


def _hash_payload(payload: object) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _require_hash(value: object) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("invalid hash")


def _require_nonempty_string(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid {name}")


def _load_canonical_json(raw: bytes) -> object:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    if not raw.endswith(b"\n") or raw.endswith(b"\r\n"):
        raise ValueError("non-canonical newline")
    value = json.loads(raw[:-1].decode("utf-8"), object_pairs_hook=unique)
    if raw != _canonical(value) + b"\n":
        raise ValueError("non-canonical JSON")
    return value


def _pointer_payload(pointer: ActiveEditionPointer) -> dict[str, str]:
    return {
        "manifest_hash": pointer.manifest_hash,
        "migration_id": pointer.migration_id,
        "target_edition_id": pointer.target_edition_id,
    }


def _pointer_from_payload(value: object) -> ActiveEditionPointer:
    if not isinstance(value, dict) or set(value) != {"manifest_hash", "migration_id", "target_edition_id"}:
        raise ValueError("invalid pointer payload")
    _require_nonempty_string(value["migration_id"], "migration_id")
    _require_hash(value["manifest_hash"])
    _require_nonempty_string(value["target_edition_id"], "target_edition_id")
    return ActiveEditionPointer(value["migration_id"], value["manifest_hash"], value["target_edition_id"])


def _pointer_hash(pointer: ActiveEditionPointer) -> str:
    return _hash_payload(_pointer_payload(pointer))


def _pointer_journal(expected_hash: str, pointer: ActiveEditionPointer) -> dict[str, object]:
    _require_hash(expected_hash)
    pointer_payload = _pointer_payload(pointer)
    base = {
        "state": "prepared",
        "expected_hash": expected_hash,
        "pointer": pointer_payload,
        "pointer_hash": _hash_payload(pointer_payload),
    }
    return {**base, "journal_hash": _hash_payload(base)}


def _pointer_from_journal(value: object) -> tuple[ActiveEditionPointer, str]:
    fields = {"state", "expected_hash", "pointer", "pointer_hash", "journal_hash"}
    if not isinstance(value, dict) or set(value) != fields or value["state"] != "prepared":
        raise ValueError("invalid pointer journal")
    _require_hash(value["expected_hash"])
    _require_hash(value["pointer_hash"])
    _require_hash(value["journal_hash"])
    base = {key: value[key] for key in fields if key != "journal_hash"}
    pointer = _pointer_from_payload(value["pointer"])
    if value["pointer_hash"] != _pointer_hash(pointer) or value["journal_hash"] != _hash_payload(base):
        raise ValueError("pointer journal hash mismatch")
    return pointer, value["expected_hash"]


def _flush_windows_publication(directory_handle: int, published_file_handle: int) -> None:
    try:
        _win_flush(directory_handle)
    except OSError as error:
        if not _is_windows_directory_flush_capability_denied(error):
            raise
    _win_flush(published_file_handle)


def _is_windows_directory_flush_capability_denied(error: OSError) -> bool:
    return getattr(error, "winerror", None) == 5 or (
        isinstance(error, PermissionError) and error.errno == 13
    )
