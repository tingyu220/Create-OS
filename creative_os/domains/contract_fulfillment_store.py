from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from creative_os.domains.contract_fulfillment import ContractFulfillmentEvidenceRecord
from creative_os.domains.narrative_evidence import EvidenceLocator, EvidenceRef, EvidenceRole
from creative_os.domains.project_authority import project_authority_lock


class ContractFulfillmentStoreError(ValueError):
    pass


def _no_io_hook(_event: str, _path: Path) -> None:
    return None


_IO_HOOK = _no_io_hook


class ContractFulfillmentStore:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        self.root = self.project_root / ".creative_os" / "memory" / "contract_fulfillment"
        self.records_path = self.root / "records.jsonl"
        self.journal_path = self.root / "journal.json"
        self.head_path = self.root / "head.json"

    def append(self, record: ContractFulfillmentEvidenceRecord) -> ContractFulfillmentEvidenceRecord:
        if not isinstance(record, ContractFulfillmentEvidenceRecord):
            raise TypeError("append requires ContractFulfillmentEvidenceRecord")
        with project_authority_lock(self.project_root):
            records = self._recover_locked()
            existing = next((item for item in records if item.record_id == record.record_id), None)
            if existing is not None:
                if existing == record:
                    return existing
                raise ContractFulfillmentStoreError("record_id_conflict")
            self._validate_supersedes(record, records)
            _, envelopes = self._read_records()
            envelope = _envelope(record, len(envelopes) + 1,
                                 envelopes[-1]["entry_hash"] if envelopes else "0" * 64)
            self._atomic_json(self.journal_path, {"state": "prepared", "envelope": envelope})
            self._append_envelope(envelope)
            self._atomic_json(self.head_path, _head(envelope))
            _IO_HOOK("before_journal_unlink", self.journal_path)
            self.journal_path.unlink(missing_ok=True)
            _fsync_directory(self.root)
            return record

    def records_for(self, contract_id: str, contract_version: int,
                    contract_content_hash: str) -> tuple[ContractFulfillmentEvidenceRecord, ...]:
        return tuple(record for record in self.recover() if (
            record.contract_id == contract_id
            and record.contract_version == contract_version
            and record.contract_content_hash == contract_content_hash
        ))

    def active_records(self, contract_id: str, contract_version: int,
                       contract_content_hash: str) -> tuple[ContractFulfillmentEvidenceRecord, ...]:
        records = self.records_for(contract_id, contract_version, contract_content_hash)
        superseded = {record.supersedes_record_id for record in records if record.supersedes_record_id}
        return tuple(record for record in records if record.record_id not in superseded)

    def recover(self) -> tuple[ContractFulfillmentEvidenceRecord, ...]:
        with project_authority_lock(self.project_root):
            return self._recover_locked()

    def _recover_locked(self) -> tuple[ContractFulfillmentEvidenceRecord, ...]:
        records, envelopes = self._read_records()
        actual = _actual_head(envelopes)
        persisted = self._read_head()
        if self.journal_path.exists():
            try:
                journal = _load_canonical_json(self.journal_path.read_bytes())
                if set(journal) != {"state", "envelope"} or journal["state"] != "prepared":
                    raise ValueError("invalid journal")
                pending = _record_from_envelope(journal["envelope"])
            except Exception as error:
                raise ContractFulfillmentStoreError("tampered_journal") from error
            existing = next((item for item in records if item.record_id == pending.record_id), None)
            if existing is not None and existing != pending:
                raise ContractFulfillmentStoreError("record_id_conflict")
            if existing is None:
                expected = persisted or {"count": 0, "head_hash": "0" * 64}
                envelope = journal["envelope"]
                if (envelope["sequence"] != expected["count"] + 1
                        or envelope["previous_hash"] != expected["head_hash"]
                        or actual != expected):
                    raise ContractFulfillmentStoreError("tampered_journal")
                self._validate_supersedes(pending, records)
                self._append_envelope(envelope)
                records = (*records, pending)
                envelopes = (*envelopes, envelope)
                actual = _actual_head(envelopes)
            elif _head(journal["envelope"]) != actual:
                raise ContractFulfillmentStoreError("tampered_journal")
            self._atomic_json(self.head_path, actual)
            _IO_HOOK("before_journal_unlink", self.journal_path)
            self.journal_path.unlink(missing_ok=True)
            _fsync_directory(self.root)
        elif persisted != actual and not (persisted is None and actual["count"] == 0):
            raise ContractFulfillmentStoreError("tampered_head_or_records")
        return tuple(records)

    def _read_records(self) -> tuple[tuple[ContractFulfillmentEvidenceRecord, ...], tuple[dict[str, object], ...]]:
        if not self.records_path.exists():
            return (), ()
        records = []
        envelopes = []
        seen = set()
        try:
            raw_file = self.records_path.read_bytes()
            if not raw_file or not raw_file.endswith(b"\n"):
                raise ValueError("records must end with one canonical newline")
            for raw in raw_file.splitlines(keepends=True):
                envelope = _load_canonical_json(raw)
                record = _record_from_envelope(envelope)
                expected_sequence = len(envelopes) + 1
                expected_previous = envelopes[-1]["entry_hash"] if envelopes else "0" * 64
                if envelope["sequence"] != expected_sequence or envelope["previous_hash"] != expected_previous:
                    raise ValueError("record chain mismatch")
                if record.record_id in seen:
                    raise ValueError("duplicate record")
                self._validate_supersedes(record, tuple(records))
                seen.add(record.record_id)
                records.append(record)
                envelopes.append(envelope)
        except ContractFulfillmentStoreError:
            raise
        except Exception as error:
            raise ContractFulfillmentStoreError("tampered_records") from error
        return tuple(records), tuple(envelopes)

    def _read_head(self) -> dict[str, object] | None:
        if not self.head_path.exists():
            return None
        try:
            value = _load_canonical_json(self.head_path.read_bytes())
            if (not isinstance(value, dict) or set(value) != {"count", "head_hash"}
                    or type(value["count"]) is not int or value["count"] < 0):
                raise ValueError("invalid head")
            _require_hash(value["head_hash"])
            return value
        except Exception as error:
            raise ContractFulfillmentStoreError("tampered_head") from error

    @staticmethod
    def _validate_supersedes(record, records) -> None:
        if record.supersedes_record_id is None:
            return
        target = next((item for item in records if item.record_id == record.supersedes_record_id), None)
        if target is None:
            raise ContractFulfillmentStoreError("supersedes_missing")
        if (target.contract_id, target.contract_version, target.contract_content_hash) != (
            record.contract_id, record.contract_version, record.contract_content_hash
        ):
            raise ContractFulfillmentStoreError("supersedes_binding_mismatch")

    def _append_envelope(self, envelope: dict[str, object]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        prior = self.records_path.read_bytes() if self.records_path.exists() else b""
        line = _canonical(envelope) + b"\n"
        temporary = self.root / f".records-{uuid.uuid4().hex}.tmp"
        with temporary.open("wb") as handle:
            handle.write(prior)
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        _IO_HOOK("before_records_replace", self.records_path)
        os.replace(temporary, self.records_path)
        _fsync_directory(self.root)

    def _atomic_json(self, path: Path, payload: object) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / f".{path.name}-{uuid.uuid4().hex}.tmp"
        with temporary.open("wb") as handle:
            handle.write(_canonical(payload) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        _IO_HOOK(f"before_replace:{path.name}", path)
        os.replace(temporary, path)
        _fsync_directory(self.root)

    def _write_prepared_for_test(self, record: ContractFulfillmentEvidenceRecord) -> None:
        with project_authority_lock(self.project_root):
            records = self._recover_locked()
            self._validate_supersedes(record, records)
            _, envelopes = self._read_records()
            envelope = _envelope(record, len(envelopes) + 1,
                                 envelopes[-1]["entry_hash"] if envelopes else "0" * 64)
            self._atomic_json(self.journal_path, {"state": "prepared", "envelope": envelope})


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _envelope(record: ContractFulfillmentEvidenceRecord, sequence: int, previous_hash: str) -> dict[str, object]:
    payload = _record_to_payload(record)
    base = {"schema_version": 1, "sequence": sequence, "previous_hash": previous_hash,
            "record_hash": hashlib.sha256(_canonical(payload)).hexdigest(), "record": payload}
    return {**base, "entry_hash": hashlib.sha256(_canonical(base)).hexdigest()}


def _record_from_envelope(value: object) -> ContractFulfillmentEvidenceRecord:
    fields = {"schema_version", "sequence", "previous_hash", "record_hash", "record", "entry_hash"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("invalid envelope")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("invalid schema version")
    if type(value["sequence"]) is not int or value["sequence"] < 1:
        raise ValueError("invalid sequence")
    _require_hash(value["previous_hash"])
    _require_hash(value["record_hash"])
    _require_hash(value["entry_hash"])
    base = {key: value[key] for key in fields if key != "entry_hash"}
    if (value["record_hash"] != hashlib.sha256(_canonical(value["record"])).hexdigest()
            or value["entry_hash"] != hashlib.sha256(_canonical(base)).hexdigest()):
        raise ValueError("record hash mismatch")
    return _record_from_payload(value["record"])


def _record_to_payload(record: ContractFulfillmentEvidenceRecord) -> dict[str, object]:
    evidence = record.evidence
    return {
        "record_id": record.record_id, "contract_id": record.contract_id,
        "contract_version": record.contract_version, "contract_content_hash": record.contract_content_hash,
        "field_path": record.field_path, "recorded_at": record.recorded_at,
        "supersedes_record_id": record.supersedes_record_id,
        "evidence": {
            "evidence_id": evidence.evidence_id, "contract_id": evidence.contract_id,
            "contract_version": evidence.contract_version, "field_path": evidence.field_path,
            "role": evidence.role.value, "source_id": evidence.source_id,
            "source_version": evidence.source_version, "source_content_hash": evidence.source_content_hash,
            "locator": {"kind": evidence.locator.kind, "value": evidence.locator.value},
            "excerpt": evidence.excerpt, "assertion": evidence.assertion,
            "asserted_value": evidence.asserted_value,
        },
    }


def _record_from_payload(value: object) -> ContractFulfillmentEvidenceRecord:
    if not isinstance(value, dict):
        raise ValueError("invalid record payload")
    expected = {"record_id", "contract_id", "contract_version", "contract_content_hash", "field_path",
                "recorded_at", "supersedes_record_id", "evidence"}
    if set(value) != expected or not isinstance(value["evidence"], dict):
        raise ValueError("invalid record fields")
    evidence_value = value["evidence"]
    evidence_fields = {"evidence_id", "contract_id", "contract_version", "field_path", "role",
                       "source_id", "source_version", "source_content_hash", "locator", "excerpt",
                       "assertion", "asserted_value"}
    if set(evidence_value) != evidence_fields:
        raise ValueError("invalid evidence fields")
    locator = evidence_value.get("locator")
    if not isinstance(locator, dict) or set(locator) != {"kind", "value"}:
        raise ValueError("invalid locator")
    evidence = EvidenceRef(
        evidence_id=evidence_value.get("evidence_id"), contract_id=evidence_value.get("contract_id"),
        contract_version=evidence_value.get("contract_version"), field_path=evidence_value.get("field_path"),
        role=EvidenceRole(evidence_value.get("role")), source_id=evidence_value.get("source_id"),
        source_version=evidence_value.get("source_version"),
        source_content_hash=evidence_value.get("source_content_hash"),
        locator=EvidenceLocator(locator["kind"], locator["value"]), excerpt=evidence_value.get("excerpt"),
        assertion=evidence_value.get("assertion"), asserted_value=evidence_value.get("asserted_value"),
    )
    return ContractFulfillmentEvidenceRecord(
        record_id=value["record_id"], contract_id=value["contract_id"],
        contract_version=value["contract_version"], contract_content_hash=value["contract_content_hash"],
        field_path=value["field_path"], evidence=evidence, recorded_at=value["recorded_at"],
        supersedes_record_id=value["supersedes_record_id"],
    )


def _head(envelope: dict[str, object]) -> dict[str, object]:
    return {"count": envelope["sequence"], "head_hash": envelope["entry_hash"]}


def _actual_head(envelopes: tuple[dict[str, object], ...]) -> dict[str, object]:
    return _head(envelopes[-1]) if envelopes else {"count": 0, "head_hash": "0" * 64}


def _require_hash(value: object) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid hash")


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
    stripped = raw[:-1]
    value = json.loads(stripped.decode("utf-8"), object_pairs_hook=unique)
    if raw != _canonical(value) + b"\n":
        raise ValueError("non-canonical JSON")
    return value


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
