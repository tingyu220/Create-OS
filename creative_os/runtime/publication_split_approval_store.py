from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re

from creative_os.domains.contract_record_filesystem import TrustedStoreFilesystem
from creative_os.domains.publication_split_planner import (
    PublicationSplitPlanner,
    SplitPlanCandidate,
    SplitPlanReviewRecord,
    split_plan_candidate_from_payload,
    split_plan_candidate_hash,
    split_plan_candidate_payload,
    split_plan_review_from_payload,
    split_plan_review_hash,
    split_plan_review_payload,
)
from creative_os.domains.publication_source_snapshot import ArchiveReceipt


_HASH = re.compile(r"^[0-9a-f]{64}$")
_ZERO_HASH = "0" * 64


class SplitPlanApprovalIntegrityError(ValueError):
    pass


class SplitPlanApprovalConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SplitPlanApprovalDecision:
    migration_id: str
    candidate_hash: str
    snapshot_hash: str
    review_hash: str
    reviewer_ruleset_version: str
    actor: str
    reason: str
    approved: bool
    decided_at: str
    decision_hash: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.migration_id, "migration_id"), (self.actor, "actor"),
            (self.reason, "reason"), (self.decided_at, "decided_at"),
        ):
            _require_text(value, name)
        for value, name in (
            (self.candidate_hash, "candidate_hash"), (self.snapshot_hash, "snapshot_hash"),
            (self.review_hash, "review_hash"), (self.decision_hash, "decision_hash"),
        ):
            _require_hash(value, name)
        if type(self.approved) is not bool:
            raise TypeError("approved must be bool")
        _require_timestamp(self.decided_at)
        _require_text(self.reviewer_ruleset_version, "reviewer_ruleset_version")
        if self.decision_hash != _decision_hash(self, include_hash=False):
            raise ValueError("decision_hash mismatch")


@dataclass(frozen=True, slots=True)
class SplitPlanApprovalRecovery:
    candidates: tuple[SplitPlanCandidate, ...]
    decisions: tuple[SplitPlanApprovalDecision, ...]


@dataclass(frozen=True, slots=True)
class _Record:
    kind: str
    key: tuple[str, ...]
    payload: dict[str, object]
    candidate: SplitPlanCandidate | None = None
    receipt: ArchiveReceipt | None = None
    review: SplitPlanReviewRecord | None = None
    decision: SplitPlanApprovalDecision | None = None


class SplitPlanApprovalStore:
    """候选与人工决策的追加式权威记录；不激活迁移清单。"""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).absolute()
        self.root = self.project_root / ".creative_os" / "publication_migration" / "split_approvals"
        self.records_path = self.root / "records.jsonl"
        self.head_path = self.root / "head.json"
        self.journal_path = self.root / "journal.json"
        self._filesystem = TrustedStoreFilesystem(
            self.project_root,
            (self.root,),
            self.root / ".split-plan-approval.lock",
            error_type=SplitPlanApprovalIntegrityError,
            conflict_type=SplitPlanApprovalConflict,
            hook=lambda _event, _path: None,
        )

    def close(self) -> None:
        self._filesystem.close()

    def append_candidate(
        self, candidate: SplitPlanCandidate, receipt: ArchiveReceipt,
        review: SplitPlanReviewRecord,
    ) -> str:
        if not isinstance(candidate, SplitPlanCandidate):
            raise TypeError("candidate must be SplitPlanCandidate")
        if candidate.candidate_hash != split_plan_candidate_hash(candidate):
            raise SplitPlanApprovalIntegrityError("candidate_hash_invalid")
        exact_review = PublicationSplitPlanner().review_record(candidate, receipt, self.project_root)
        if review != exact_review or review.review_hash != split_plan_review_hash(review):
            raise SplitPlanApprovalIntegrityError("review_binding_invalid")
        record = _candidate_record({
            "kind": "candidate", "candidate": split_plan_candidate_payload(candidate),
            "archive_receipt": _receipt_payload(receipt), "review": split_plan_review_payload(review),
        }, self.project_root)
        with self._authority_lock():
            self._append(record)
        return candidate.candidate_hash

    def append_decision(
        self,
        candidate_hash: str,
        actor: str,
        reason: str,
        approved: bool,
        *,
        decided_at: str | None = None,
    ) -> SplitPlanApprovalDecision:
        _require_hash(candidate_hash, "candidate_hash")
        _require_text(actor, "actor")
        _require_text(reason, "reason")
        if type(approved) is not bool:
            raise TypeError("approved must be bool")
        if decided_at is not None:
            _require_timestamp(decided_at)
        with self._authority_lock():
            records = self._recover_records()
            candidate = next(
                (item.candidate for item in reversed(records)
                 if item.kind == "candidate" and item.candidate is not None
                 and item.candidate.candidate_hash == candidate_hash),
                None,
            )
            if candidate is None:
                raise SplitPlanApprovalIntegrityError("candidate_exact_not_found")
            current = next(
                item.candidate for item in reversed(records)
                if item.kind == "candidate" and item.candidate is not None
                and item.candidate.migration_id == candidate.migration_id
            )
            if current.candidate_hash != candidate_hash:
                raise SplitPlanApprovalIntegrityError("candidate_stale")
            current_record = next(
                item for item in reversed(records)
                if item.candidate is not None and item.candidate.candidate_hash == candidate_hash
            )
            if current_record.review is None or (approved and current_record.review.blocking_issues):
                raise SplitPlanApprovalIntegrityError("review_blocking")
            existing = next(
                (item.decision for item in records if item.kind == "decision"
                 and item.decision is not None and item.decision.candidate_hash == candidate_hash),
                None,
            )
            if existing is not None:
                if (existing.actor, existing.reason, existing.approved) == (actor, reason, approved):
                    return existing
                raise SplitPlanApprovalConflict("decision_conflict")
            decision = _new_decision(
                candidate, actor, reason, approved,
                current_record.review,
                decided_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            self._append_record_locked(_decision_record({"kind": "decision", "decision": _decision_payload(decision)}), records)
            return decision

    def recover(self) -> SplitPlanApprovalRecovery:
        with self._authority_lock():
            records = self._recover_records()
        return SplitPlanApprovalRecovery(
            tuple(item.candidate for item in records if item.candidate is not None),
            tuple(item.decision for item in records if item.decision is not None),
        )

    def load_current_bundle(
        self, migration_id: str,
    ) -> tuple[SplitPlanCandidate, ArchiveReceipt, SplitPlanReviewRecord]:
        _require_text(migration_id, "migration_id")
        with self._authority_lock():
            records = self._recover_records()
        record = next(
            (
                item for item in reversed(records)
                if item.kind == "candidate" and item.candidate is not None
                and item.candidate.migration_id == migration_id
            ),
            None,
        )
        if record is None or record.receipt is None or record.review is None:
            raise SplitPlanApprovalIntegrityError("candidate_current_not_found")
        return record.candidate, record.receipt, record.review

    def require_current_approval(
        self, candidate: SplitPlanCandidate, receipt: ArchiveReceipt,
        review: SplitPlanReviewRecord,
    ) -> SplitPlanApprovalDecision:
        if not isinstance(candidate, SplitPlanCandidate):
            raise TypeError("candidate must be SplitPlanCandidate")
        if candidate.candidate_hash != split_plan_candidate_hash(candidate):
            raise SplitPlanApprovalIntegrityError("candidate_hash_invalid")
        with self._authority_lock():
            records = self._recover_records()
            persisted_record = next(
                (item for item in records if item.candidate is not None
                 and item.candidate.candidate_hash == candidate.candidate_hash),
                None,
            )
            if persisted_record is None or persisted_record.candidate != candidate:
                raise SplitPlanApprovalIntegrityError("candidate_exact_not_found")
            exact_review = PublicationSplitPlanner().review_record(candidate, receipt, self.project_root)
            if (
                persisted_record.receipt != receipt or persisted_record.review != review
                or review != exact_review or review.blocking_issues
            ):
                raise SplitPlanApprovalIntegrityError("review_binding_invalid")
            current = next(
                item.candidate for item in reversed(records)
                if item.candidate is not None and item.candidate.migration_id == candidate.migration_id
            )
            if current.candidate_hash != candidate.candidate_hash:
                raise SplitPlanApprovalIntegrityError("candidate_stale")
            decision = next(
                (item.decision for item in records if item.decision is not None
                 and item.decision.candidate_hash == candidate.candidate_hash),
                None,
            )
            if decision is None:
                raise SplitPlanApprovalIntegrityError("decision_missing")
            if not decision.approved:
                raise SplitPlanApprovalIntegrityError("candidate_not_approved")
            if (
                decision.snapshot_hash != receipt.source_snapshot_hash
                or decision.review_hash != review.review_hash
                or decision.reviewer_ruleset_version != review.ruleset_version
            ):
                raise SplitPlanApprovalIntegrityError("decision_review_binding_invalid")
            return decision

    @contextmanager
    def _authority_lock(self):
        with self._filesystem.exclusive_lock():
            self._filesystem.validate_all()
            yield
            self._filesystem.validate_all()

    def _append(self, record: _Record) -> None:
        records = self._recover_records()
        self._append_record_locked(record, records)

    def _append_record_locked(self, record: _Record, records: tuple[_Record, ...]) -> None:
        existing = next((item for item in records if item.key == record.key), None)
        if existing is not None:
            if existing.payload == record.payload:
                return
            raise SplitPlanApprovalConflict("logical_append_conflict")
        envelopes = self._read_envelopes()
        envelope = _envelope(
            record.payload, len(envelopes) + 1,
            envelopes[-1]["envelope_hash"] if envelopes else _ZERO_HASH,
        )
        self._atomic_json(self.journal_path, {"state": "prepared", "envelope": envelope})
        self._write_records(envelope)
        self._atomic_json(self.head_path, _head(envelope))

    def _recover_records(self) -> tuple[_Record, ...]:
        records, envelopes = self._read_chain()
        actual = _actual_head(envelopes)
        persisted = self._read_head()
        if self._filesystem.exists_regular(self.journal_path):
            try:
                journal = _load_canonical(self._filesystem.read_bytes(self.journal_path))
                if not isinstance(journal, dict) or set(journal) != {"state", "envelope"} or journal["state"] != "prepared":
                    raise ValueError("invalid journal")
                pending = _record_from_envelope(
                    journal["envelope"], self.project_root,
                )
                envelope = journal["envelope"]
            except Exception as error:
                raise SplitPlanApprovalIntegrityError("tampered_journal") from error
            if envelope["sequence"] == len(envelopes) + 1 and envelope["previous_hash"] == actual["head_hash"]:
                if persisted not in (None, actual):
                    raise SplitPlanApprovalIntegrityError("tampered_head")
                self._write_records(envelope)
                records = (*records, pending)
                envelopes = (*envelopes, envelope)
                actual = _actual_head(envelopes)
            elif not envelopes or envelope != envelopes[-1]:
                raise SplitPlanApprovalIntegrityError("tampered_journal")
            else:
                prior = _actual_head(envelopes[:-1])
                if persisted not in (actual, prior) and not (
                    persisted is None and prior["count"] == 0
                ):
                    raise SplitPlanApprovalIntegrityError("tampered_head")
            if persisted != actual:
                self._atomic_json(self.head_path, actual)
        elif persisted != actual and not (persisted is None and actual["count"] == 0):
            raise SplitPlanApprovalIntegrityError("tampered_head")
        return records

    def _read_chain(self) -> tuple[tuple[_Record, ...], tuple[dict[str, object], ...]]:
        if not self._filesystem.exists_regular(self.records_path):
            return (), ()
        try:
            raw = self._filesystem.read_bytes(self.records_path)
            if not raw or not raw.endswith(b"\n"):
                raise ValueError("truncated records")
            records: list[_Record] = []
            envelopes: list[dict[str, object]] = []
            keys: set[tuple[str, ...]] = set()
            for line in raw.splitlines(keepends=True):
                envelope = _load_canonical(line)
                record = _record_from_envelope(envelope, self.project_root)
                previous = envelopes[-1]["envelope_hash"] if envelopes else _ZERO_HASH
                if envelope["sequence"] != len(envelopes) + 1 or envelope["previous_hash"] != previous or record.key in keys:
                    raise ValueError("record chain mismatch")
                keys.add(record.key)
                records.append(record)
                envelopes.append(envelope)
            return tuple(records), tuple(envelopes)
        except Exception as error:
            raise SplitPlanApprovalIntegrityError("tampered_records") from error

    def _read_envelopes(self) -> tuple[dict[str, object], ...]:
        return self._read_chain()[1]

    def _read_head(self) -> dict[str, object] | None:
        if not self._filesystem.exists_regular(self.head_path):
            return None
        try:
            value = _load_canonical(self._filesystem.read_bytes(self.head_path))
            if not isinstance(value, dict) or set(value) != {"count", "head_hash"}:
                raise ValueError("invalid head")
            if type(value["count"]) is not int or value["count"] < 0:
                raise ValueError("invalid head count")
            _require_hash(value["head_hash"], "head_hash")
            return value
        except Exception as error:
            raise SplitPlanApprovalIntegrityError("tampered_head") from error

    def _write_records(self, envelope: dict[str, object]) -> None:
        prior = self._filesystem.read_bytes(self.records_path) if self._filesystem.exists_regular(self.records_path) else None
        self._filesystem.atomic_write_bytes(
            self.records_path, (prior or b"") + _canonical(envelope) + b"\n", expected=prior,
        )

    def _atomic_json(self, path: Path, value: object) -> None:
        prior = self._filesystem.read_bytes(path) if self._filesystem.exists_regular(path) else None
        self._filesystem.atomic_write_bytes(path, _canonical(value) + b"\n", expected=prior)


def _candidate_record(
    payload: dict[str, object], project_root: Path,
) -> _Record:
    if set(payload) != {"kind", "candidate", "archive_receipt", "review"} or payload["kind"] != "candidate":
        raise ValueError("invalid candidate record")
    candidate = split_plan_candidate_from_payload(payload["candidate"])
    receipt = _receipt_from_payload(payload["archive_receipt"])
    review = split_plan_review_from_payload(payload["review"])
    if review != PublicationSplitPlanner().review_record(candidate, receipt, project_root):
        raise ValueError("review binding invalid")
    return _Record(
        "candidate", ("candidate", candidate.candidate_hash), payload,
        candidate=candidate, receipt=receipt, review=review,
    )


def _decision_record(payload: dict[str, object]) -> _Record:
    if set(payload) != {"kind", "decision"} or payload["kind"] != "decision":
        raise ValueError("invalid decision record")
    decision = _decision_from_payload(payload["decision"])
    return _Record("decision", ("decision", decision.candidate_hash), payload, decision=decision)


def _record_from_envelope(
    value: object, project_root: Path,
) -> _Record:
    fields = {"schema_version", "sequence", "previous_hash", "payload_hash", "payload", "envelope_hash"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("invalid envelope")
    if value["schema_version"] != 1 or type(value["sequence"]) is not int or value["sequence"] < 1:
        raise ValueError("invalid envelope identity")
    _require_hash(value["previous_hash"], "previous_hash")
    _require_hash(value["payload_hash"], "payload_hash")
    _require_hash(value["envelope_hash"], "envelope_hash")
    base = {key: value[key] for key in fields if key != "envelope_hash"}
    if value["payload_hash"] != _digest(value["payload"]) or value["envelope_hash"] != _digest(base):
        raise ValueError("envelope hash mismatch")
    payload = value["payload"]
    if not isinstance(payload, dict):
        raise ValueError("invalid payload")
    if payload.get("kind") == "candidate":
        return _candidate_record(payload, project_root)
    if payload.get("kind") == "decision":
        return _decision_record(payload)
    raise ValueError("unknown record kind")


def _new_decision(
    candidate: SplitPlanCandidate, actor: str, reason: str, approved: bool,
    review: SplitPlanReviewRecord, decided_at: str,
) -> SplitPlanApprovalDecision:
    values = {
        "migration_id": candidate.migration_id,
        "candidate_hash": candidate.candidate_hash,
        "snapshot_hash": candidate.source_snapshot_hash,
        "review_hash": review.review_hash,
        "reviewer_ruleset_version": review.ruleset_version,
        "actor": actor,
        "reason": reason,
        "approved": approved,
        "decided_at": decided_at,
    }
    decision_hash = _digest(values)
    return SplitPlanApprovalDecision(**values, decision_hash=decision_hash)


def _decision_payload(value: SplitPlanApprovalDecision) -> dict[str, object]:
    return {
        "migration_id": value.migration_id, "candidate_hash": value.candidate_hash,
        "snapshot_hash": value.snapshot_hash, "actor": value.actor, "reason": value.reason,
        "review_hash": value.review_hash, "reviewer_ruleset_version": value.reviewer_ruleset_version,
        "approved": value.approved, "decided_at": value.decided_at, "decision_hash": value.decision_hash,
    }


def _decision_from_payload(value: object) -> SplitPlanApprovalDecision:
    fields = {
        "migration_id", "candidate_hash", "snapshot_hash", "actor", "reason",
        "review_hash", "reviewer_ruleset_version", "approved", "decided_at", "decision_hash",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("invalid decision payload")
    return SplitPlanApprovalDecision(**value)


def _decision_hash(value: SplitPlanApprovalDecision, *, include_hash: bool) -> str:
    payload = _decision_payload(value)
    if not include_hash:
        payload.pop("decision_hash")
    return _digest(payload)


def _receipt_payload(value: ArchiveReceipt) -> dict[str, object]:
    if not isinstance(value, ArchiveReceipt):
        raise TypeError("archive receipt is required")
    return {
        "source_edition_id": value.source_edition_id,
        "archive_root": str(value.archive_root),
        "verified_file_count": value.verified_file_count,
        "source_snapshot_hash": value.source_snapshot_hash,
        "archive_hash": value.archive_hash,
    }


def _receipt_from_payload(value: object) -> ArchiveReceipt:
    fields = {
        "source_edition_id", "archive_root", "verified_file_count",
        "source_snapshot_hash", "archive_hash",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("invalid archive receipt payload")
    return ArchiveReceipt(
        source_edition_id=value["source_edition_id"], archive_root=Path(value["archive_root"]),
        verified_file_count=value["verified_file_count"],
        source_snapshot_hash=value["source_snapshot_hash"], archive_hash=value["archive_hash"],
    )


def _envelope(payload: dict[str, object], sequence: int, previous_hash: str) -> dict[str, object]:
    base = {
        "schema_version": 1, "sequence": sequence, "previous_hash": previous_hash,
        "payload_hash": _digest(payload), "payload": payload,
    }
    return {**base, "envelope_hash": _digest(base)}


def _head(envelope: dict[str, object]) -> dict[str, object]:
    return {"count": envelope["sequence"], "head_hash": envelope["envelope_hash"]}


def _actual_head(envelopes: tuple[dict[str, object], ...]) -> dict[str, object]:
    return _head(envelopes[-1]) if envelopes else {"count": 0, "head_hash": _ZERO_HASH}


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_canonical(raw: bytes) -> object:
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    if not raw.endswith(b"\n") or raw.endswith(b"\r\n"):
        raise ValueError("non-canonical newline")
    value = json.loads(raw[:-1].decode("utf-8"), object_pairs_hook=unique)
    if raw != _canonical(value) + b"\n":
        raise ValueError("non-canonical JSON")
    return value


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


def _require_hash(value: object, name: str) -> None:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _require_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("decided_at must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("decided_at must include a timezone")
