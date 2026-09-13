from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from creative_os.domains.contract_approval import (
    APPROVAL_ITEMS,
    ApprovalItem,
    ApprovalStatus,
    ContractApprovalRecord,
)
from creative_os.domains.contract_baseline import BaselineEntry, BaselineManifest
from creative_os.domains.contract_issue import EvidenceCheck
from creative_os.domains.contract_record_filesystem import TrustedStoreFilesystem
from creative_os.domains.project_authority import project_authority_lock
from creative_os.domains.contract_review import (
    PrewriteReviewerResult,
    ReviewIssue,
    ReviewIssueDisposition,
)
from creative_os.domains.narrative_evidence import EvidenceLocator, EvidenceRef, EvidenceRole
from creative_os.domains.contract_revision import (
    RunContinuationStatus, WriterRunContinuationAuthorization,
)


class ContractRecordStoreError(ValueError):
    """A contract record is unsafe, malformed, missing authority, or tampered."""


class ContractRecordConflictError(ContractRecordStoreError):
    """An append-only physical identity already has different authoritative content."""


@dataclass(frozen=True, slots=True)
class ExactContractRecords:
    """Records rebuilt from disk and bound to one exact contract/baseline/ruleset."""

    baseline_record_id: str
    baseline: BaselineManifest
    approval_record_id: str
    approval: ContractApprovalRecord
    reviewer_record_id: str | None = None
    reviewer_result: PrewriteReviewerResult | None = None
    disposition_records: tuple[tuple[str, ReviewIssueDisposition], ...] = ()

    @property
    def dispositions(self) -> tuple[ReviewIssueDisposition, ...]:
        return tuple(record for _, record in self.disposition_records)

    @property
    def record_ids(self) -> tuple[str, ...]:
        result = (self.baseline_record_id, self.approval_record_id)
        if self.reviewer_record_id is not None:
            result += (self.reviewer_record_id,)
        return result + tuple(record_id for record_id, _ in self.disposition_records)


_RECORD_DIRECTORIES = {
    "baseline": "baselines",
    "approval": "approvals",
    "reviewer_result": "reviews",
    "disposition": "dispositions",
    "continuation_authorization": "continuation_authorizations",
}
_ENVELOPE_FIELDS = frozenset({"record_type", "schema_version", "payload_hash", "payload"})
_JOURNAL_FIELDS = frozenset(
    {"journal_version", "state", "record_type", "record_id", "envelope", "entry_hash"}
)
_JOURNAL_STATES = frozenset({"prepared", "committed"})
# Individual slugs are bounded independently; reviewer persistence also
# verifies every future disposition's combined physical-key length.
_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_RECORD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,249}")
_ATOMIC_TEMP_NAME = re.compile(r"\.record-[A-Za-z0-9_-]{8}\.tmp")
_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


def _no_io_test_hook(event: str, path: Path) -> None:
    return None


_IO_TEST_HOOK = _no_io_test_hook


class ContractRecordStore:
    """Append-only authority for approval-time contract records."""

    def __init__(self, project_root: str | Path) -> None:
        requested_root = Path(project_root).absolute()
        try:
            _io_path(requested_root).mkdir(parents=True, exist_ok=True)
            self.project_root = requested_root.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ContractRecordStoreError("trusted project root is unavailable") from error
        self.root = self.project_root / ".creative_os" / "memory" / "contract_records"
        self.journal_dir = self.root / "journal"
        self._command_receipts_path = self.root / "command-receipts.json"
        self._directories = {
            record_type: self.root / directory
            for record_type, directory in _RECORD_DIRECTORIES.items()
        }
        self._lock_path = self.journal_dir / ".contract-records.lock"
        try:
            self._filesystem = TrustedStoreFilesystem(
                self.project_root,
                (*self._directories.values(), self.journal_dir),
                self._lock_path,
                error_type=ContractRecordStoreError,
                conflict_type=ContractRecordConflictError,
                hook=lambda event, path: _IO_TEST_HOOK(event, path),
            )
        except ContractRecordStoreError:
            raise
        except OSError as error:
            raise ContractRecordStoreError("contract record filesystem setup failed") from error
    def save_baseline(
        self,
        contract_id: str,
        contract_version: int,
        manifest: BaselineManifest,
    ) -> str:
        payload = {
            "contract_id": contract_id,
            "contract_version": contract_version,
            "manifest": _manifest_to_payload(manifest),
        }
        return self._save("baseline", payload)

    def save_approval(self, record: ContractApprovalRecord) -> str:
        return self._save("approval", _approval_to_payload(record))

    def save_reviewer_result(self, result: PrewriteReviewerResult) -> str:
        _validate_reviewer_key_space(result)
        return self._save("reviewer_result", _review_to_payload(result))

    def save_disposition(self, disposition: ReviewIssueDisposition) -> str:
        return self._save(
            "disposition",
            _disposition_to_payload(disposition),
            validate_binding=True,
        )

    def load_command_receipt(self, idempotency_key: str) -> tuple[str, dict[str, Any]] | None:
        _require_exact_text(idempotency_key, "idempotency_key")
        with self._authority_lock():
            if not self._filesystem.exists_regular(self._command_receipts_path):
                return None
            payload = self._read_json(self._command_receipts_path)
            records = _command_receipt_records(payload)
            record = records.get(idempotency_key)
            if record is None:
                return None
            return record["fingerprint"], dict(record["receipt"])

    def save_command_receipt(
        self, idempotency_key: str, fingerprint: str, receipt: dict[str, Any],
    ) -> None:
        _require_exact_text(idempotency_key, "idempotency_key")
        _require_sha256(fingerprint, "command fingerprint")
        if type(receipt) is not dict:
            raise ContractRecordStoreError("command receipt must be an object")
        with self._authority_lock():
            records: dict[str, dict[str, Any]] = {}
            if self._filesystem.exists_regular(self._command_receipts_path):
                records = _command_receipt_records(self._read_json(self._command_receipts_path))
            existing = records.get(idempotency_key)
            if existing is not None:
                if existing["fingerprint"] != fingerprint or existing["receipt"] != receipt:
                    raise ContractRecordConflictError("command idempotency conflict")
                return
            records[idempotency_key] = {"fingerprint": fingerprint, "receipt": receipt}
            self._write_json(
                self._command_receipts_path,
                {"schema_version": 1, "records": records},
                expected=None if not self._filesystem.exists_regular(self._command_receipts_path)
                else self._read_json(self._command_receipts_path),
            )

    def save_continuation_authorization(self, authorization: WriterRunContinuationAuthorization) -> str:
        return self._save(
            "continuation_authorization", _continuation_authorization_to_payload(authorization),
            validate_binding=True,
        )

    def load_continuation_authorization(self, record_id: str) -> WriterRunContinuationAuthorization:
        return self._load("continuation_authorization", record_id)

    def find_exact_continuation_authorization(
        self, *, authorization_id: str, run_id: str, contract_id: str,
        contract_version: int, contract_hash: str,
    ) -> tuple[str, WriterRunContinuationAuthorization] | None:
        with self._authority_lock():
            records = [
                (record_id, record)
                for record_id, record in self._scan_locked("continuation_authorization")
                if record.run_id == run_id
                and record.old_contract_id == contract_id
                and record.old_contract_version == contract_version
                and record.old_contract_hash == contract_hash
            ]
            active = [item for item in records if item[1].authorization_id == authorization_id
                      and item[1].status == RunContinuationStatus.ACTIVE]
            revoked = {item[1].supersedes_authorization_id for item in records
                       if item[1].status == RunContinuationStatus.REVOKED}
            active = [item for item in active if item[1].authorization_id not in revoked]
            if len(active) > 1:
                raise ContractRecordStoreError("duplicate continuation authorization")
            return active[0] if active else None

    def load_baseline(self, record_id: str) -> BaselineManifest:
        return self._load("baseline", record_id)

    def load_approval(self, record_id: str) -> ContractApprovalRecord:
        return self._load("approval", record_id)

    def load_reviewer_result(self, record_id: str) -> PrewriteReviewerResult:
        return self._load("reviewer_result", record_id)

    def find_reviewer_result(self, result_id: str) -> PrewriteReviewerResult | None:
        _require_exact_text(result_id, "reviewer_result_id")
        with self._authority_lock():
            matches = tuple(
                record
                for _, record in self._scan_locked("reviewer_result")
                if isinstance(record, PrewriteReviewerResult) and record.result_id == result_id
            )
            if len(matches) > 1:
                raise ContractRecordConflictError("duplicate reviewer result id")
            return matches[0] if matches else None

    def load_disposition(self, record_id: str) -> ReviewIssueDisposition:
        return self._load("disposition", record_id)

    def load(
        self,
        record_id: str,
    ) -> BaselineManifest | ContractApprovalRecord | PrewriteReviewerResult | ReviewIssueDisposition | WriterRunContinuationAuthorization:
        _require_record_id(record_id)
        for prefix, record_type in (
            ("baseline-", "baseline"),
            ("approval-", "approval"),
            ("review-", "reviewer_result"),
            ("disposition-", "disposition"),
            ("continuation-", "continuation_authorization"),
        ):
            if record_id.startswith(prefix):
                return self._load(record_type, record_id)
        raise ContractRecordStoreError("unknown contract record type")

    def find_exact(
        self,
        *,
        contract_id: str,
        contract_version: int,
        contract_hash: str,
        baseline_fingerprint: str,
        ruleset_version: str | None = None,
    ) -> ExactContractRecords | None:
        _require_slug(contract_id, "contract_id")
        _require_version(contract_version)
        _require_sha256(contract_hash, "contract_hash")
        _require_sha256(baseline_fingerprint, "baseline_fingerprint")
        if ruleset_version is not None:
            _require_text(ruleset_version, "ruleset_version")

        baseline_id = f"baseline-{contract_id}-v{contract_version:04d}-{baseline_fingerprint}"
        approval_id = (
            f"approval-{contract_id}-v{contract_version:04d}-{contract_hash}-{baseline_fingerprint}"
        )
        with self._authority_lock():
            self._recover_locked()
            baseline = self._load_if_present_locked("baseline", baseline_id)
            approval = self._load_if_present_locked("approval", approval_id)
            if baseline is None or approval is None:
                return None
            assert isinstance(baseline, BaselineManifest)
            assert isinstance(approval, ContractApprovalRecord)
            if approval.baseline_manifest != baseline:
                raise ContractRecordConflictError("approval baseline binding conflicts with authority")

            if ruleset_version is None:
                return ExactContractRecords(
                    baseline_record_id=baseline_id,
                    baseline=baseline,
                    approval_record_id=approval_id,
                    approval=approval,
                )

            matching_reviews = tuple(
                (record_id, record)
                for record_id, record in self._scan_locked("reviewer_result")
                if isinstance(record, PrewriteReviewerResult)
                and record.contract_id == contract_id
                and record.contract_version == contract_version
                and record.contract_content_hash == contract_hash
                and record.baseline_fingerprint == baseline_fingerprint
                and record.ruleset_version == ruleset_version
            )
            if not matching_reviews:
                return None
            if len(matching_reviews) != 1:
                raise ContractRecordConflictError("ambiguous exact reviewer results")
            reviewer_record_id, reviewer = matching_reviews[0]
            assert isinstance(reviewer, PrewriteReviewerResult)
            issues = {
                (
                    issue.issue_id,
                    issue.canonical_issue_hash,
                    issue.code,
                    issue.field_path,
                    issue.evidence_hash,
                )
                for issue in reviewer.issues
            }
            dispositions = tuple(
                (record_id, record)
                for record_id, record in self._scan_locked("disposition")
                if isinstance(record, ReviewIssueDisposition)
                and record.reviewer_result_id == reviewer.result_id
                and record.reviewer_result_hash == reviewer.result_hash
                and (
                    record.issue_id,
                    record.canonical_issue_hash,
                    record.issue_code,
                    record.field_path,
                    record.evidence_hash,
                )
                in issues
            )
            return ExactContractRecords(
                baseline_record_id=baseline_id,
                baseline=baseline,
                approval_record_id=approval_id,
                approval=approval,
                reviewer_record_id=reviewer_record_id,
                reviewer_result=reviewer,
                disposition_records=dispositions,
            )

    def recover(self) -> None:
        with self._authority_lock():
            try:
                self._recover_locked()
            except ContractRecordStoreError:
                raise
            except OSError as error:
                raise ContractRecordStoreError("contract record recovery failed") from error

    def _save(self, record_type: str, payload: dict[str, Any], *, validate_binding: bool = False) -> str:
        try:
            model = _decode_payload(record_type, payload)
            canonical_payload = _payload_for(record_type, model, payload)
            envelope = _make_envelope(record_type, canonical_payload)
            record_id = _record_id_for(record_type, canonical_payload, model, envelope["payload_hash"])
            with self._authority_lock():
                self._recover_locked()
                if validate_binding:
                    if record_type == "disposition":
                        self._validate_disposition_binding_locked(model)
                    else:
                        self._validate_continuation_binding_locked(model)
                existing = self._load_if_present_locked(record_type, record_id)
                if existing is not None:
                    existing_envelope = self._read_record_file(record_type, record_id)
                    if existing_envelope != envelope:
                        raise ContractRecordConflictError(
                            f"append-only contract record conflict: {record_id}"
                        )
                    return record_id

                journal_path = self._journal_path(record_type, record_id)
                journal_expected: dict[str, Any]
                if self._filesystem.exists_regular(journal_path):
                    journal = self._read_journal(journal_path)
                    if journal["envelope"] != envelope:
                        raise ContractRecordConflictError(
                            f"append-only contract record conflict: {record_id}"
                        )
                    journal_expected = journal
                else:
                    journal_expected = _make_journal(
                        "prepared", record_type, record_id, envelope
                    )
                    self._write_json(
                        journal_path,
                        journal_expected,
                        expected=None,
                    )

                target = self._record_path(record_type, record_id)
                if self._filesystem.exists_regular(target):
                    if self._read_record_file(record_type, record_id) != envelope:
                        raise ContractRecordConflictError(
                            f"append-only contract record conflict: {record_id}"
                        )
                else:
                    self._write_json(target, envelope, expected=None)
                if self._read_record_file(record_type, record_id) != envelope:
                    raise ContractRecordConflictError(
                        f"append-only contract record conflict: {record_id}"
                    )
                self._write_json(
                    journal_path,
                    _make_journal("committed", record_type, record_id, envelope),
                    expected=journal_expected,
                )
                return record_id
        except ContractRecordStoreError:
            raise
        except (OSError, TypeError, ValueError, KeyError, AttributeError) as error:
            raise ContractRecordStoreError("contract record save failed") from error

    def _load(self, record_type: str, record_id: str):
        _require_record_id(record_id)
        try:
            with self._authority_lock():
                self._recover_locked()
                model = self._load_if_present_locked(record_type, record_id)
                if model is None:
                    raise KeyError(record_id)
                return model
        except (ContractRecordStoreError, KeyError):
            raise
        except (OSError, TypeError, ValueError, AttributeError) as error:
            raise ContractRecordStoreError("contract record load failed") from error

    def _load_if_present_locked(self, record_type: str, record_id: str):
        path = self._record_path(record_type, record_id)
        if not self._filesystem.exists_regular(path):
            return None
        envelope = self._read_record_file(record_type, record_id)
        journal_path = self._journal_path(record_type, record_id)
        if not self._filesystem.exists_regular(journal_path):
            raise ContractRecordStoreError("authoritative record has no journal")
        journal = self._read_journal(journal_path)
        if journal["state"] != "committed" or journal["envelope"] != envelope:
            raise ContractRecordConflictError("record and journal authority conflict")
        model = _decode_payload(record_type, envelope["payload"])
        if record_type == "disposition":
            self._validate_disposition_binding_locked(model)
        if (record_type == "continuation_authorization"
                and model.status == RunContinuationStatus.REVOKED):
            self._validate_continuation_binding_locked(model)
        return model

    def _recover_locked(self) -> None:
        journals: dict[tuple[str, str], tuple[Path, dict[str, Any]]] = {}
        for path in self._json_files(self.journal_dir, allow_lock=True):
            journal = self._read_journal(path)
            key = (journal["record_type"], journal["record_id"])
            if key in journals:
                raise ContractRecordStoreError("duplicate contract record journal")
            journals[key] = (path, journal)

        # Reviewer authority must be fully recovered before any disposition
        # is allowed to materialize or commit.
        for disposition_phase in (False, True):
            for key, (path, journal) in tuple(journals.items()):
                record_type, record_id = key
                decoded = _decode_payload(record_type, journal["envelope"]["payload"])
                needs_binding = (
                    record_type == "disposition"
                    or record_type == "continuation_authorization"
                )
                if needs_binding is not disposition_phase:
                    continue
                if record_type == "disposition":
                    self._validate_disposition_binding_locked(decoded)
                elif record_type == "continuation_authorization":
                    self._validate_continuation_binding_locked(decoded)
                target = self._record_path(record_type, record_id)
                if self._filesystem.exists_regular(target):
                    if self._read_record_file(record_type, record_id) != journal["envelope"]:
                        raise ContractRecordConflictError("prepared record conflicts with journal")
                elif journal["state"] == "prepared":
                    self._write_json(target, journal["envelope"], expected=None)
                else:
                    raise ContractRecordStoreError("committed contract record is missing")
                if journal["state"] == "prepared":
                    committed = _make_journal(
                        "committed", record_type, record_id, journal["envelope"]
                    )
                    self._write_json(path, committed, expected=journal)
                    journals[key] = (path, committed)

        for record_type, directory in self._directories.items():
            for path in self._json_files(directory):
                record_id = path.stem
                if (record_type, record_id) not in journals:
                    raise ContractRecordStoreError("orphan contract record has no journal")
                self._load_if_present_locked(record_type, record_id)

    def _scan_locked(self, record_type: str) -> tuple[tuple[str, object], ...]:
        return tuple(
            (path.stem, self._load_if_present_locked(record_type, path.stem))
            for path in self._json_files(self._directories[record_type])
        )

    def _validate_continuation_binding_locked(self, model: object) -> None:
        if not isinstance(model, WriterRunContinuationAuthorization):
            raise ContractRecordStoreError("continuation authorization type mismatch")
        targets = []
        same_ids = []
        for path in self._json_files(self._directories["continuation_authorization"]):
            envelope = self._read_record_file("continuation_authorization", path.stem)
            record = _decode_payload("continuation_authorization", envelope["payload"])
            if record.authorization_id == model.authorization_id:
                same_ids.append(record)
            if (record.authorization_id == model.supersedes_authorization_id
                    and record.status == RunContinuationStatus.ACTIVE):
                targets.append(record)
        if model.status == RunContinuationStatus.ACTIVE:
            if same_ids and any(record != model for record in same_ids):
                raise ContractRecordStoreError("continuation authorization_id conflict")
            return
        if len(targets) != 1:
            raise ContractRecordStoreError("continuation revocation target missing or ambiguous")
        target = targets[0]
        if (
            target.run_id != model.run_id
            or target.old_contract_id != model.old_contract_id
            or target.old_contract_version != model.old_contract_version
            or target.old_contract_hash != model.old_contract_hash
        ):
            raise ContractRecordStoreError("continuation revocation binding mismatch")

    def _validate_disposition_binding_locked(self, model: object) -> None:
        if not isinstance(model, ReviewIssueDisposition):
            raise ContractRecordStoreError("disposition payload did not reconstruct")
        reviews = tuple(
            record
            for _, record in self._scan_locked("reviewer_result")
            if isinstance(record, PrewriteReviewerResult)
            and record.result_id == model.reviewer_result_id
            and record.result_hash == model.reviewer_result_hash
        )
        if len(reviews) != 1:
            raise ContractRecordStoreError("disposition reviewer binding is not authoritative")
        issue_bindings = {
            (
                issue.issue_id,
                issue.canonical_issue_hash,
                issue.code,
                issue.field_path,
                issue.evidence_hash,
            )
            for issue in reviews[0].issues
        }
        binding = (
            model.issue_id,
            model.canonical_issue_hash,
            model.issue_code,
            model.field_path,
            model.evidence_hash,
        )
        if binding not in issue_bindings:
            raise ContractRecordStoreError("disposition issue binding is not authoritative")

    def _read_record_file(self, record_type: str, record_id: str) -> dict[str, Any]:
        path = self._record_path(record_type, record_id)
        envelope = self._read_json(path)
        _validate_envelope(record_type, record_id, envelope)
        return envelope

    def _read_journal(self, path: Path) -> dict[str, Any]:
        journal = self._read_json(path)
        _require_object(journal, _JOURNAL_FIELDS, "journal")
        if type(journal["journal_version"]) is not int or journal["journal_version"] != 1:
            raise ContractRecordStoreError("unsupported journal version")
        if type(journal["state"]) is not str or journal["state"] not in _JOURNAL_STATES:
            raise ContractRecordStoreError("invalid journal state")
        record_type = _require_record_type(journal["record_type"])
        record_id = journal["record_id"]
        _require_record_id(record_id)
        _require_sha256(journal["entry_hash"], "journal entry_hash")
        core = {key: value for key, value in journal.items() if key != "entry_hash"}
        if journal["entry_hash"] != _canonical_hash(core):
            raise ContractRecordStoreError("journal entry hash mismatch")
        if path != self._journal_path(record_type, record_id):
            raise ContractRecordStoreError("journal filename binding mismatch")
        _validate_envelope(record_type, record_id, journal["envelope"])
        return journal

    def _record_path(self, record_type: str, record_id: str) -> Path:
        _require_record_type(record_type)
        _require_record_id(record_id)
        return self._directories[record_type] / f"{record_id}.json"

    def _journal_path(self, record_type: str, record_id: str) -> Path:
        operation_id = _canonical_hash({"record_id": record_id, "record_type": record_type})
        return self.journal_dir / f"{operation_id}.json"

    @contextmanager
    def _authority_lock(self) -> Iterator[None]:
        with project_authority_lock(self.project_root):
            with _local_lock(self._lock_path):
                with self._filesystem.exclusive_lock():
                    yield

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            raw = self._filesystem.read_bytes(path).decode("utf-8")
            return _parse_canonical_json(raw, path.name)
        except ContractRecordStoreError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise ContractRecordStoreError(f"invalid contract record file: {path.name}") from error

    def _write_json(
        self,
        path: Path,
        payload: dict[str, Any],
        *,
        expected: dict[str, Any] | None,
    ) -> None:
        expected_bytes = None if expected is None else _canonical_text(expected).encode("utf-8")
        self._filesystem.atomic_write_bytes(
            path,
            _canonical_text(payload).encode("utf-8"),
            expected=expected_bytes,
        )

    def _json_files(self, directory: Path, *, allow_lock: bool = False) -> tuple[Path, ...]:
        files: list[Path] = []
        for name in self._filesystem.list_names(directory):
            path = directory / name
            self._filesystem.require_regular_entry(path, "contract record path")
            if allow_lock and name == ".contract-records.lock":
                continue
            if _ATOMIC_TEMP_NAME.fullmatch(name):
                continue
            if Path(name).suffix != ".json":
                raise ContractRecordStoreError(f"unexpected contract record path: {name}")
            files.append(path)
        return tuple(files)


def _make_envelope(record_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": record_type,
        "schema_version": 1,
        "payload_hash": _canonical_hash(payload),
        "payload": payload,
    }


def _make_journal(
    state: str,
    record_type: str,
    record_id: str,
    envelope: dict[str, Any],
) -> dict[str, Any]:
    core = {
        "journal_version": 1,
        "state": state,
        "record_type": record_type,
        "record_id": record_id,
        "envelope": envelope,
    }
    return {**core, "entry_hash": _canonical_hash(core)}


def _validate_envelope(record_type: str, record_id: str, envelope: object) -> object:
    _require_object(envelope, _ENVELOPE_FIELDS, "record envelope")
    if type(envelope["record_type"]) is not str or envelope["record_type"] != record_type:
        raise ContractRecordStoreError("record_type binding mismatch")
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1:
        raise ContractRecordStoreError("unsupported record schema_version")
    _require_sha256(envelope["payload_hash"], "payload_hash")
    if type(envelope["payload"]) is not dict:
        raise ContractRecordStoreError("record payload must be an exact object")
    if envelope["payload_hash"] != _canonical_hash(envelope["payload"]):
        raise ContractRecordStoreError("record payload_hash mismatch")
    model = _decode_payload(record_type, envelope["payload"])
    expected_id = _record_id_for(record_type, envelope["payload"], model, envelope["payload_hash"])
    if record_id != expected_id:
        raise ContractRecordStoreError("record filename binding mismatch")
    return model


def _record_id_for(
    record_type: str,
    payload: dict[str, Any],
    model: object,
    payload_hash: str,
) -> str:
    if record_type == "baseline":
        assert isinstance(model, BaselineManifest)
        contract_id = _require_slug(payload["contract_id"], "contract_id")
        version = _require_version(payload["contract_version"])
        result = f"baseline-{contract_id}-v{version:04d}-{model.fingerprint}"
    elif record_type == "approval":
        assert isinstance(model, ContractApprovalRecord)
        contract_id = _require_slug(model.contract_id, "contract_id")
        version = _require_version(model.contract_version)
        result = (
            f"approval-{contract_id}-v{version:04d}-{model.contract_content_hash}-"
            f"{model.baseline_manifest.fingerprint}"
        )
    elif record_type == "reviewer_result":
        assert isinstance(model, PrewriteReviewerResult)
        contract_id = _require_slug(model.contract_id, "contract_id")
        version = _require_version(model.contract_version)
        result = f"review-{contract_id}-v{version:04d}-{model.result_hash}"
    elif record_type == "disposition":
        assert isinstance(model, ReviewIssueDisposition)
        result_id = _require_slug(model.reviewer_result_id, "reviewer_result_id")
        issue_id = _require_slug(model.issue_id, "issue_id")
        result = (
            f"disposition-{result_id}-{issue_id}-{model.canonical_issue_hash}-{payload_hash}"
        )
    else:
        assert isinstance(model, WriterRunContinuationAuthorization)
        result = f"continuation-{_require_slug(model.authorization_id, 'authorization_id')}-{payload_hash}"
    _require_record_id(result)
    return result


def _command_receipt_records(payload: object) -> dict[str, dict[str, Any]]:
    if type(payload) is not dict or set(payload) != {"schema_version", "records"}:
        raise ContractRecordStoreError("command receipt schema invalid")
    if payload["schema_version"] != 1 or type(payload["records"]) is not dict:
        raise ContractRecordStoreError("command receipt schema invalid")
    result: dict[str, dict[str, Any]] = {}
    for key, value in payload["records"].items():
        _require_exact_text(key, "idempotency_key")
        if type(value) is not dict or set(value) != {"fingerprint", "receipt"}:
            raise ContractRecordStoreError("command receipt record invalid")
        _require_sha256(value["fingerprint"], "command fingerprint")
        if type(value["receipt"]) is not dict:
            raise ContractRecordStoreError("command receipt payload invalid")
        result[key] = {"fingerprint": value["fingerprint"], "receipt": dict(value["receipt"])}
    return result


def _validate_reviewer_key_space(result: object) -> None:
    if not isinstance(result, PrewriteReviewerResult):
        raise ContractRecordStoreError("reviewer result type mismatch")
    result_id = _require_slug(result.result_id, "reviewer result_id")
    for issue in result.issues:
        issue_id = _require_slug(issue.issue_id, "review issue_id")
        _require_record_id(
            f"disposition-{result_id}-{issue_id}-{issue.canonical_issue_hash}-{'0' * 64}"
        )


def _payload_for(record_type: str, model: object, original: dict[str, Any]) -> dict[str, Any]:
    if record_type == "baseline":
        assert isinstance(model, BaselineManifest)
        return {
            "contract_id": original["contract_id"],
            "contract_version": original["contract_version"],
            "manifest": _manifest_to_payload(model),
        }
    if record_type == "approval":
        assert isinstance(model, ContractApprovalRecord)
        return _approval_to_payload(model)
    if record_type == "reviewer_result":
        assert isinstance(model, PrewriteReviewerResult)
        return _review_to_payload(model)
    if record_type == "disposition":
        assert isinstance(model, ReviewIssueDisposition)
        return _disposition_to_payload(model)
    assert isinstance(model, WriterRunContinuationAuthorization)
    return _continuation_authorization_to_payload(model)


def _decode_payload(record_type: str, payload: object) -> object:
    try:
        if record_type == "baseline":
            _require_object(
                payload,
                frozenset({"contract_id", "contract_version", "manifest"}),
                "baseline payload",
            )
            _require_slug(payload["contract_id"], "contract_id")
            _require_version(payload["contract_version"])
            return _manifest_from_payload(payload["manifest"])
        if record_type == "approval":
            return _approval_from_payload(payload)
        if record_type == "reviewer_result":
            return _review_from_payload(payload)
        if record_type == "disposition":
            return _disposition_from_payload(payload)
        if record_type == "continuation_authorization":
            return _continuation_authorization_from_payload(payload)
        raise ContractRecordStoreError("unknown record_type")
    except ContractRecordStoreError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError) as error:
        raise ContractRecordStoreError(f"invalid {record_type} payload") from error


def _manifest_to_payload(manifest: object) -> dict[str, Any]:
    if not isinstance(manifest, BaselineManifest):
        raise ContractRecordStoreError("baseline manifest type mismatch")
    return {
        "entries": [
            {
                "content_hash": entry.content_hash,
                "role": entry.role,
                "source_id": entry.source_id,
                "source_version": entry.source_version,
            }
            for entry in manifest.entries
        ],
        "fingerprint": manifest.fingerprint,
    }


def _continuation_authorization_to_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, WriterRunContinuationAuthorization):
        raise ContractRecordStoreError("continuation authorization type mismatch")
    return {
        "authorization_id": value.authorization_id, "run_id": value.run_id,
        "old_contract_id": value.old_contract_id,
        "old_contract_version": value.old_contract_version,
        "old_contract_hash": value.old_contract_hash, "actor": value.actor,
        "reason": value.reason, "created_at": value.created_at,
        "expires_at": value.expires_at, "status": value.status.value,
        "supersedes_authorization_id": value.supersedes_authorization_id,
    }


def _continuation_authorization_from_payload(payload: object) -> WriterRunContinuationAuthorization:
    _require_object(payload, frozenset({
        "authorization_id", "run_id", "old_contract_id", "old_contract_version",
        "old_contract_hash", "actor", "reason", "created_at", "expires_at",
        "status", "supersedes_authorization_id",
    }), "continuation authorization")
    for name in ("authorization_id", "run_id", "old_contract_id", "old_contract_hash",
                 "actor", "reason", "created_at", "expires_at", "status"):
        _require_exact_text(payload[name], name)
    if type(payload["old_contract_version"]) is not int:
        raise ContractRecordStoreError("old_contract_version must be exact integer")
    if payload["supersedes_authorization_id"] is not None:
        _require_exact_text(payload["supersedes_authorization_id"], "supersedes_authorization_id")
    return WriterRunContinuationAuthorization(
        authorization_id=payload["authorization_id"], run_id=payload["run_id"],
        old_contract_id=payload["old_contract_id"], old_contract_version=payload["old_contract_version"],
        old_contract_hash=payload["old_contract_hash"], actor=payload["actor"], reason=payload["reason"],
        created_at=payload["created_at"], expires_at=payload["expires_at"],
        status=RunContinuationStatus(payload["status"]),
        supersedes_authorization_id=payload["supersedes_authorization_id"],
    )


def _manifest_from_payload(payload: object) -> BaselineManifest:
    _require_object(payload, frozenset({"entries", "fingerprint"}), "baseline manifest")
    entries_payload = _require_list(payload["entries"], "baseline entries")
    entries: list[BaselineEntry] = []
    for entry in entries_payload:
        _require_object(
            entry,
            frozenset({"role", "source_id", "source_version", "content_hash"}),
            "baseline entry",
        )
        for field in ("role", "source_id", "source_version", "content_hash"):
            _require_exact_text(entry[field], f"baseline {field}")
        entries.append(BaselineEntry(**entry))
    _require_exact_text(payload["fingerprint"], "baseline fingerprint")
    return BaselineManifest(entries=tuple(entries), fingerprint=payload["fingerprint"])


def _evidence_to_payload(evidence: EvidenceRef) -> dict[str, Any]:
    if not isinstance(evidence, EvidenceRef) or evidence.is_legacy_replay_ref:
        raise ContractRecordStoreError("approval evidence must be a field EvidenceRef")
    assert evidence.role is not None and evidence.locator is not None
    return {
        "asserted_value": evidence.asserted_value,
        "assertion": evidence.assertion,
        "contract_id": evidence.contract_id,
        "contract_version": evidence.contract_version,
        "evidence_id": evidence.evidence_id,
        "excerpt": evidence.excerpt,
        "field_path": evidence.field_path,
        "locator": {"kind": evidence.locator.kind, "value": evidence.locator.value},
        "role": evidence.role.value,
        "source_content_hash": evidence.source_content_hash,
        "source_id": evidence.source_id,
        "source_version": evidence.source_version,
    }


def _evidence_from_payload(payload: object) -> EvidenceRef:
    fields = frozenset(
        {
            "asserted_value",
            "assertion",
            "contract_id",
            "contract_version",
            "evidence_id",
            "excerpt",
            "field_path",
            "locator",
            "role",
            "source_content_hash",
            "source_id",
            "source_version",
        }
    )
    _require_object(payload, fields, "approval evidence")
    for field in fields - {"asserted_value", "contract_version", "locator"}:
        _require_exact_text(payload[field], f"evidence {field}")
    _require_positive_int(payload["contract_version"], "evidence contract_version")
    asserted_value = payload["asserted_value"]
    if asserted_value is not None and type(asserted_value) not in (str, int, bool):
        raise ContractRecordStoreError("evidence asserted_value has an invalid type")
    locator = payload["locator"]
    _require_object(locator, frozenset({"kind", "value"}), "evidence locator")
    _require_exact_text(locator["kind"], "locator kind")
    _require_exact_text(locator["value"], "locator value")
    return EvidenceRef(
        evidence_id=payload["evidence_id"],
        contract_id=payload["contract_id"],
        contract_version=payload["contract_version"],
        field_path=payload["field_path"],
        role=EvidenceRole(payload["role"]),
        source_id=payload["source_id"],
        source_version=payload["source_version"],
        source_content_hash=payload["source_content_hash"],
        locator=EvidenceLocator(kind=locator["kind"], value=locator["value"]),
        excerpt=payload["excerpt"],
        assertion=payload["assertion"],
        asserted_value=asserted_value,
    )


def _approval_item_to_payload(item: ApprovalItem) -> dict[str, Any]:
    return {
        "approved_at": item.approved_at,
        "approved_by": item.approved_by,
        "decision_evidence": [_evidence_to_payload(value) for value in item.decision_evidence],
        "reason": item.reason,
        "status": item.status.value,
    }


def _approval_item_from_payload(payload: object) -> ApprovalItem:
    _require_object(
        payload,
        frozenset({"approved_at", "approved_by", "decision_evidence", "reason", "status"}),
        "approval item",
    )
    for field in ("approved_at", "approved_by", "reason", "status"):
        _require_exact_text(payload[field], f"approval {field}")
    evidence = tuple(
        _evidence_from_payload(value)
        for value in _require_list(payload["decision_evidence"], "approval decision_evidence")
    )
    return ApprovalItem(
        status=ApprovalStatus(payload["status"]),
        reason=payload["reason"],
        approved_by=payload["approved_by"],
        approved_at=payload["approved_at"],
        decision_evidence=evidence,
    )


def _approval_to_payload(record: object) -> dict[str, Any]:
    if not isinstance(record, ContractApprovalRecord):
        raise ContractRecordStoreError("approval record type mismatch")
    return {
        "baseline_manifest": _manifest_to_payload(record.baseline_manifest),
        "contract_content_hash": record.contract_content_hash,
        "contract_id": record.contract_id,
        "contract_version": record.contract_version,
        **{name: _approval_item_to_payload(record.item(name)) for name in APPROVAL_ITEMS},
    }


def _approval_from_payload(payload: object) -> ContractApprovalRecord:
    fields = frozenset(
        {"contract_id", "contract_version", "contract_content_hash", "baseline_manifest", *APPROVAL_ITEMS}
    )
    _require_object(payload, fields, "approval payload")
    _require_exact_text(payload["contract_id"], "approval contract_id")
    _require_positive_int(payload["contract_version"], "approval contract_version")
    _require_exact_text(payload["contract_content_hash"], "approval contract_content_hash")
    return ContractApprovalRecord(
        contract_id=payload["contract_id"],
        contract_version=payload["contract_version"],
        contract_content_hash=payload["contract_content_hash"],
        baseline_manifest=_manifest_from_payload(payload["baseline_manifest"]),
        **{name: _approval_item_from_payload(payload[name]) for name in APPROVAL_ITEMS},
    )


def _check_to_payload(check: EvidenceCheck) -> dict[str, Any]:
    return {"code": check.code, "detail": check.detail, "passed": check.passed}


def _check_from_payload(payload: object) -> EvidenceCheck:
    _require_object(payload, frozenset({"code", "detail", "passed"}), "evidence check")
    _require_exact_text(payload["code"], "evidence check code")
    _require_exact_text(payload["detail"], "evidence check detail")
    if type(payload["passed"]) is not bool:
        raise ContractRecordStoreError("evidence check passed must be an exact bool")
    return EvidenceCheck(code=payload["code"], detail=payload["detail"], passed=payload["passed"])


def _issue_to_payload(issue: ReviewIssue) -> dict[str, Any]:
    return {
        "blocking": issue.blocking,
        "canonical_issue_hash": issue.canonical_issue_hash,
        "code": issue.code,
        "evidence_checks": [_check_to_payload(check) for check in issue.evidence_checks],
        "evidence_hash": issue.evidence_hash,
        "field_path": issue.field_path,
        "issue_id": issue.issue_id,
        "repair_hint": issue.repair_hint,
        "requires_human_disposition": issue.requires_human_disposition,
        "severity": issue.severity,
    }


def _issue_from_payload(payload: object) -> ReviewIssue:
    fields = frozenset(
        {
            "blocking",
            "canonical_issue_hash",
            "code",
            "evidence_checks",
            "evidence_hash",
            "field_path",
            "issue_id",
            "repair_hint",
            "requires_human_disposition",
            "severity",
        }
    )
    _require_object(payload, fields, "review issue")
    for field in fields - {"blocking", "requires_human_disposition", "evidence_checks"}:
        _require_exact_text(payload[field], f"review issue {field}")
    if type(payload["blocking"]) is not bool or type(payload["requires_human_disposition"]) is not bool:
        raise ContractRecordStoreError("review issue booleans must be exact")
    return ReviewIssue(
        issue_id=payload["issue_id"],
        canonical_issue_hash=payload["canonical_issue_hash"],
        code=payload["code"],
        severity=payload["severity"],
        blocking=payload["blocking"],
        requires_human_disposition=payload["requires_human_disposition"],
        field_path=payload["field_path"],
        evidence_checks=tuple(
            _check_from_payload(value)
            for value in _require_list(payload["evidence_checks"], "review evidence_checks")
        ),
        evidence_hash=payload["evidence_hash"],
        repair_hint=payload["repair_hint"],
    )


def _review_to_payload(result: object) -> dict[str, Any]:
    if not isinstance(result, PrewriteReviewerResult):
        raise ContractRecordStoreError("reviewer result type mismatch")
    return {
        "baseline_fingerprint": result.baseline_fingerprint,
        "contract_content_hash": result.contract_content_hash,
        "contract_id": result.contract_id,
        "contract_version": result.contract_version,
        "issues": [_issue_to_payload(issue) for issue in result.issues],
        "result_hash": result.result_hash,
        "result_id": result.result_id,
        "ruleset_version": result.ruleset_version,
        "semantic_asset_versions": [list(value) for value in result.semantic_asset_versions],
    }


def _review_from_payload(payload: object) -> PrewriteReviewerResult:
    fields = frozenset(
        {
            "baseline_fingerprint",
            "contract_content_hash",
            "contract_id",
            "contract_version",
            "issues",
            "result_hash",
            "result_id",
            "ruleset_version",
            "semantic_asset_versions",
        }
    )
    _require_object(payload, fields, "reviewer result")
    for field in fields - {"contract_version", "issues", "semantic_asset_versions"}:
        _require_exact_text(payload[field], f"reviewer {field}")
    _require_positive_int(payload["contract_version"], "reviewer contract_version")
    assets: list[tuple[str, str]] = []
    for item in _require_list(payload["semantic_asset_versions"], "semantic asset versions"):
        if type(item) is not list or len(item) != 2:
            raise ContractRecordStoreError("semantic asset version must be an exact pair")
        _require_exact_text(item[0], "semantic asset name")
        _require_exact_text(item[1], "semantic asset version")
        assets.append((item[0], item[1]))
    return PrewriteReviewerResult(
        result_id=payload["result_id"],
        contract_id=payload["contract_id"],
        contract_version=payload["contract_version"],
        contract_content_hash=payload["contract_content_hash"],
        baseline_fingerprint=payload["baseline_fingerprint"],
        ruleset_version=payload["ruleset_version"],
        semantic_asset_versions=tuple(assets),
        issues=tuple(
            _issue_from_payload(value)
            for value in _require_list(payload["issues"], "review issues")
        ),
        result_hash=payload["result_hash"],
    )


_DISPOSITION_FIELDS = frozenset(
    {
        "actor",
        "canonical_issue_hash",
        "decided_at",
        "evidence_hash",
        "field_path",
        "issue_code",
        "issue_id",
        "reason",
        "reviewer_result_hash",
        "reviewer_result_id",
        "status",
    }
)


def _disposition_to_payload(disposition: object) -> dict[str, Any]:
    if not isinstance(disposition, ReviewIssueDisposition):
        raise ContractRecordStoreError("disposition type mismatch")
    return {field: getattr(disposition, field) for field in _DISPOSITION_FIELDS}


def _disposition_from_payload(payload: object) -> ReviewIssueDisposition:
    _require_object(payload, _DISPOSITION_FIELDS, "disposition payload")
    for field in _DISPOSITION_FIELDS:
        _require_exact_text(payload[field], f"disposition {field}")
    return ReviewIssueDisposition(**payload)


def _require_object(value: object, fields: frozenset[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise ContractRecordStoreError(f"{name} fields must be exact")
    return value


def _require_list(value: object, name: str) -> list[Any]:
    if type(value) is not list:
        raise ContractRecordStoreError(f"{name} must be an exact list")
    return value


def _require_exact_text(value: object, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ContractRecordStoreError(f"{name} must be exact non-empty text")
    return value


def _require_text(value: object, name: str) -> str:
    return _require_exact_text(value, name)


def _require_positive_int(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ContractRecordStoreError(f"{name} must be an exact positive integer")
    return value


def _require_version(value: object) -> int:
    version = _require_positive_int(value, "contract_version")
    if version > 9999:
        raise ContractRecordStoreError("contract_version exceeds vMMMM")
    return version


def _require_sha256(value: object, name: str) -> str:
    text = _require_exact_text(value, name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ContractRecordStoreError(f"{name} must be a lowercase sha256")
    return text


def _require_slug(value: object, name: str) -> str:
    text = _require_exact_text(value, name)
    if _SLUG.fullmatch(text) is None:
        raise ContractRecordStoreError(f"{name} must be a safe slug")
    return text


def _require_record_id(value: object) -> str:
    text = _require_exact_text(value, "record_id")
    if _RECORD_ID.fullmatch(text) is None:
        raise ContractRecordStoreError("record_id must be path safe")
    return text


def _require_record_type(value: object) -> str:
    if type(value) is not str or value not in _RECORD_DIRECTORIES:
        raise ContractRecordStoreError("unknown contract record type")
    return value


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _io_path(path: Path) -> Path:
    """Use Win32's extended path form without changing logical record paths."""
    if os.name != "nt":
        return path
    value = str(path.absolute())
    if value.startswith("\\\\?\\"):
        return Path(value)
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    return Path("\\\\?\\" + value)


def _parse_canonical_json(raw: str, name: str) -> dict[str, Any]:
    payload = json.loads(
        raw,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    if type(payload) is not dict or raw != _canonical_text(payload):
        raise ContractRecordStoreError(f"contract record JSON must be canonical: {name}")
    return payload


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _local_lock(path: Path) -> threading.Lock:
    key = str(path.absolute())
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.Lock())


def authoritative_record_hash(record: object) -> str:
    """Canonical payload hash used by activation bindings without copying payloads."""
    if isinstance(record, ContractApprovalRecord):
        return _canonical_hash(_approval_to_payload(record))
    if isinstance(record, PrewriteReviewerResult):
        return _canonical_hash(_review_to_payload(record))
    if isinstance(record, ReviewIssueDisposition):
        return _canonical_hash(_disposition_to_payload(record))
    raise TypeError("unsupported authoritative record")
