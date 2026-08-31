from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from creative_os.domains.project_authority import project_authority_lock


@dataclass(frozen=True, slots=True)
class EngagementAuthorityRecord:
    record_type: str
    record_id: str
    content_hash: str
    payload: dict[str, Any]


class ReaderEngagementStore:
    SCHEMA_VERSION = 1
    _TYPES = frozenset({"plan", "expectation_candidate", "expectation_decision", "expectation_transition", "engagement_review", "opening_checkpoint", "opening_checkpoint_decision"})

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        self.root = self.project_root / ".creative_os" / "engagement"
        self.records_path = self.root / "records.jsonl"
        self.head_path = self.root / "head.json"
        self.journal_path = self.root / "journal.json"

    def append_plan_candidate(self, payload: dict[str, Any]) -> EngagementAuthorityRecord:
        if not isinstance(payload, dict) or payload.get("id") is None:
            raise ValueError("invalid plan payload")
        record = EngagementAuthorityRecord("plan", str(payload["id"]), str(payload.get("content_hash", "")), dict(payload))
        if len(record.content_hash) != 64:
            raise ValueError("invalid content hash")
        with project_authority_lock(self.project_root):
            records = self._recover_locked()
            existing = next((item for item in records if item.record_id == record.record_id), None)
            if existing:
                if existing == record:
                    return existing
                raise ValueError("record_id_conflict")
            self._append_locked(record, records)
            return record

    def append_raw(self, record_type: str, payload: dict[str, Any]) -> None:
        if record_type not in self._TYPES or payload.get("schema_version") not in (None, self.SCHEMA_VERSION):
            raise ValueError("unknown schema")

    def append_engagement_review(self, payload: dict[str, Any]) -> EngagementAuthorityRecord:
        required = {"review_id", "status", "plan_hash", "ledger_head_hash", "curve_hash", "artifact_hash"}
        if set(payload) != required or payload["status"] not in {"passed", "blocked"}:
            raise ValueError("review_schema")
        record = EngagementAuthorityRecord("engagement_review", str(payload["review_id"]), hashlib.sha256(self._canonical(payload)).hexdigest(), dict(payload))
        with project_authority_lock(self.project_root):
            records = self._recover_locked()
            existing = next((x for x in records if x.record_type == record.record_type and x.record_id == record.record_id), None)
            if existing:
                if existing == record: return existing
                raise ValueError("review_conflict")
            self._append_locked(record, records)
        return record

    def append_opening_checkpoint_review(self, payload: dict[str, Any]) -> EngagementAuthorityRecord:
        required = {"record_id", "project_id", "chapter_number", "plan_hash", "projection_hash", "ledger_head_hash", "curve_hash", "contract_hash", "context_fingerprint", "artifact_hash", "ruleset_hash", "actor", "reason", "disposition"}
        if set(payload) != required or payload["chapter_number"] not in {1, 3, 6, 10} or not payload["actor"].strip() or not payload["reason"].strip():
            raise ValueError("opening_checkpoint_schema")
        record = EngagementAuthorityRecord("opening_checkpoint", str(payload["record_id"]), hashlib.sha256(self._canonical(payload)).hexdigest(), dict(payload))
        with project_authority_lock(self.project_root):
            records = self._recover_locked()
            existing = next((x for x in records if x.record_type == record.record_type and x.record_id == record.record_id), None)
            if existing:
                if existing == record: return existing
                raise ValueError("opening_checkpoint_conflict")
            self._append_locked(record, records)
        return record

    def compile_transition_candidate(self, expectation_id: str, from_state: str, to_state: str, artifact_hash: str, evidence: tuple[object, ...], *, plan_hash: str, projection_hash: str) -> EngagementAuthorityRecord:
        if not evidence or len(artifact_hash) != 64 or len(plan_hash) != 64 or len(projection_hash) != 64:
            raise ValueError("transition_evidence_required")
        return self.append_expectation_candidate({"expectation_id": expectation_id, "from_state": from_state, "to_state": to_state, "content_hash": artifact_hash, "evidence": list(evidence), "projection_hash": projection_hash, "plan_hash": plan_hash})

    def append_expectation_candidate(self, payload: dict[str, Any]) -> EngagementAuthorityRecord:
        if not isinstance(payload, dict):
            raise ValueError("invalid expectation candidate")
        required = {"expectation_id", "from_state", "to_state", "content_hash", "evidence"}
        allowed = required | {"previous_record_hash", "plan_hash", "projection_hash"}
        if not required <= set(payload) or not set(payload) <= allowed:
            raise ValueError("invalid expectation candidate schema")
        expectation_id = payload["expectation_id"]
        if not isinstance(expectation_id, str) or not expectation_id.strip():
            raise ValueError("expectation_id required")
        from_state, to_state = payload["from_state"], payload["to_state"]
        records = self.recover()
        existing = next((item for item in records if item.record_type == "expectation_candidate" and item.record_id == expectation_id), None)
        if from_state == "absent" and to_state != "open":
            raise ValueError("invalid_establish_transition")
        if from_state != "absent" and not any(item.record_type == "expectation_transition" and item.record_id == expectation_id for item in records):
            raise ValueError("missing_expectation")
        if existing:
            if self._canonical(existing.payload) == self._canonical(payload):
                return existing
            raise ValueError("record_id_conflict")
        normalized = json.loads(self._canonical(payload))
        record = EngagementAuthorityRecord("expectation_candidate", expectation_id, payload["content_hash"], normalized)
        with project_authority_lock(self.project_root):
            records = self._recover_locked()
            existing = next((item for item in records if item.record_type == record.record_type and item.record_id == record.record_id), None)
            if existing:
                if self._canonical(existing.payload) == self._canonical(record.payload):
                    return existing
                raise ValueError("record_id_conflict")
            self._append_locked(record, records)
        return record

    def append_raw_decision(self, payload: dict[str, Any]) -> EngagementAuthorityRecord:
        if set(payload) != {"plan_id", "plan_hash", "curve_id", "curve_hash", "actor", "reason", "disposition"}:
            raise ValueError("decision_schema")
        if payload["disposition"] != "approved":
            raise ValueError("decision_invalid")
        decision_id = f"{payload['plan_id']}:{payload['plan_hash']}:{payload['curve_id']}:{payload['curve_hash']}"
        record = EngagementAuthorityRecord("plan_decision", decision_id, hashlib.sha256(self._canonical(payload)).hexdigest(), dict(payload))
        with project_authority_lock(self.project_root):
            records = self._recover_locked()
            existing = next((item for item in records if item.record_type == "plan_decision" and item.record_id == decision_id), None)
            if existing:
                if existing.payload == record.payload:
                    return existing
                raise ValueError("decision_conflict")
            self._append_locked(record, records)
        return record

    def activate_plan_locked(self, plan_id: str, decision_id: str, expected_active_hash: str) -> EngagementAuthorityRecord:
        records = self._recover_locked()
        plan = next((item for item in records if item.record_type == "plan" and item.record_id == plan_id), None)
        decision = next((item for item in records if item.record_type == "plan_decision" and item.record_id == decision_id), None)
        if plan is None or decision is None or decision.payload.get("plan_hash") != plan.content_hash:
            raise ValueError("activation_binding_mismatch")
        if expected_active_hash not in {"0" * 64, plan.content_hash}:
            raise ValueError("stale_active_hash")
        payload = {"plan_id": plan_id, "plan_hash": plan.content_hash, "decision_id": decision_id,
                   "activation_binding_hash": hashlib.sha256(self._canonical({"plan": plan.content_hash, "decision": decision.content_hash})).hexdigest()}
        record = EngagementAuthorityRecord("plan_activation", plan_id, payload["activation_binding_hash"], payload)
        existing = next((item for item in records if item.record_type == "plan_activation" and item.record_id == plan_id), None)
        if existing:
            if existing.payload == payload:
                return existing
            raise ValueError("activation_conflict")
        self._append_locked(record, records)
        return record

    def project_chapter_locked(self, project_id: str, chapter_number: int) -> EngagementAuthorityRecord:
        if type(chapter_number) is not int or chapter_number <= 0:
            raise ValueError("active projection requires single chapter")
        records = self._recover_locked()
        active = [item for item in records if item.record_type == "plan_activation"]
        if not active:
            raise ValueError("active_plan_required")
        plan = next((item for item in records if item.record_type == "plan" and item.record_id == active[-1].payload["plan_id"]), None)
        if plan is None or plan.payload.get("project_id", project_id) != project_id:
            raise ValueError("active_plan_mismatch")
        payload = {"plan_id": plan.record_id, "plan_hash": plan.content_hash, "chapter_number": chapter_number}
        return EngagementAuthorityRecord("chapter_projection", f"{plan.record_id}:{chapter_number}", hashlib.sha256(self._canonical(payload)).hexdigest(), payload)

    def materialize_transition(self, candidate_id: str, decision: dict[str, Any], expected_head_hash: str) -> EngagementAuthorityRecord:
        with project_authority_lock(self.project_root):
            records = self._recover_locked()
            candidate = next((item for item in records if item.record_type == "expectation_candidate" and item.record_id == candidate_id), None)
            if candidate is None:
                raise ValueError("candidate_missing")
            if not isinstance(decision, dict) or decision.get("disposition") != "approved" or not decision.get("actor") or not decision.get("reason"):
                raise ValueError("decision_invalid")
            if candidate.payload.get("to_state") == "paid":
                for field in ("projection_hash", "payoff_window", "contract_pay_intent", "exact_evidence"):
                    if not candidate.payload.get(field):
                        raise ValueError("paid_requirements_missing")
            current_head = self._head_hash(records)
            if expected_head_hash != current_head:
                raise ValueError("stale_head")
            decision_payload = {"candidate_id": candidate_id, **decision, "previous_authority_hash": current_head}
            decision_hash = hashlib.sha256(self._canonical({"domain": "engagement_decision", "payload": decision_payload})).hexdigest()
            decision_payload["decision_hash"] = decision_hash
            decision_record = EngagementAuthorityRecord("expectation_decision", candidate_id, decision_hash, decision_payload)
            existing = next((item for item in records if item.record_type == "expectation_decision" and item.record_id == candidate_id), None)
            if existing:
                if existing.payload == decision_payload:
                    return next(item for item in records if item.record_type == "expectation_transition" and item.record_id == candidate_id)
                raise ValueError("decision_conflict")
            self._append_locked(decision_record, records)
            records = (*records, decision_record)
            transition = EngagementAuthorityRecord("expectation_transition", candidate_id, candidate.content_hash, {"candidate": candidate.payload, "decision_hash": decision_hash})
            self._append_locked(transition, records)
            return transition

    def load_exact(self, record_type: str, record_id: str, content_hash: str) -> EngagementAuthorityRecord:
        with project_authority_lock(self.project_root):
            for record in self._recover_locked():
                if record.record_type == record_type and record.record_id == record_id:
                    if record.content_hash != content_hash:
                        raise ValueError("content_hash_mismatch")
                    return record
        raise KeyError(record_id)

    def recover(self) -> tuple[EngagementAuthorityRecord, ...]:
        with project_authority_lock(self.project_root):
            return self._recover_locked()

    def recover_read_only(self) -> tuple[EngagementAuthorityRecord, ...]:
        """只读校验 authority 链，不创建锁文件、目录或其他状态。"""
        return self._recover_locked()

    def _recover_locked(self) -> tuple[EngagementAuthorityRecord, ...]:
        if self.journal_path.exists():
            raise ValueError("tampered_journal")
        if not self.records_path.exists():
            return ()
        try:
            raw = self.records_path.read_bytes()
            if not raw.endswith(b"\n"):
                raise ValueError("records newline")
            records = []
            previous = "0" * 64
            for line in raw.splitlines(keepends=True):
                envelope = json.loads(line, object_pairs_hook=self._unique)
                if set(envelope) != {"schema_version", "sequence", "previous_hash", "record", "entry_hash"}:
                    raise ValueError("invalid envelope")
                if envelope["schema_version"] != self.SCHEMA_VERSION or envelope["sequence"] != len(records) + 1 or envelope["previous_hash"] != previous:
                    raise ValueError("record chain")
                expected = hashlib.sha256(self._canonical({k: envelope[k] for k in envelope if k != "entry_hash"})).hexdigest()
                if envelope["entry_hash"] != expected:
                    raise ValueError("entry hash")
                record = envelope["record"]
                records.append(EngagementAuthorityRecord(record["record_type"], record["record_id"], record["content_hash"], record["payload"]))
                previous = envelope["entry_hash"]
            if self.head_path.exists():
                head = json.loads(self.head_path.read_bytes(), object_pairs_hook=self._unique)
                if head.get("count") != len(records) or head.get("head_hash") != previous:
                    raise ValueError("head drift")
            return tuple(records)
        except Exception as error:
            raise ValueError("tampered_records") from error

    def _append_locked(self, record: EngagementAuthorityRecord, records: tuple[EngagementAuthorityRecord, ...]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        previous = "0" * 64
        if records and self.records_path.exists():
            previous = json.loads(self.records_path.read_bytes().splitlines()[-1])["entry_hash"]
        envelope = self._envelope(record, len(records) + 1, previous)
        self.journal_path.write_bytes(self._canonical({"state": "prepared", "envelope": envelope}) + b"\n")
        prior = self.records_path.read_bytes() if self.records_path.exists() else b""
        temp = self.root / f".records-{uuid.uuid4().hex}.tmp"
        with temp.open("wb") as handle:
            handle.write(prior + self._canonical(envelope) + b"\n")
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, self.records_path)
        entry_hash = envelope["entry_hash"]
        self.head_path.write_bytes(self._canonical({"count": len(records) + 1, "head_hash": entry_hash}) + b"\n")
        self.journal_path.unlink(missing_ok=True)

    def _head_hash(self, records: tuple[EngagementAuthorityRecord, ...]) -> str:
        if not records or not self.records_path.exists():
            return "0" * 64
        return json.loads(self.records_path.read_bytes().splitlines()[-1])["entry_hash"]

    @staticmethod
    def _envelope(record: EngagementAuthorityRecord, sequence: int, previous: str) -> dict[str, Any]:
        base = {"schema_version": 1, "sequence": sequence, "previous_hash": previous,
                "record": {"record_type": record.record_type, "record_id": record.record_id,
                            "content_hash": record.content_hash, "payload": record.payload}}
        return {**base, "entry_hash": hashlib.sha256(ReaderEngagementStore._canonical(base)).hexdigest()}

    @staticmethod
    def _canonical(value: object) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

    @staticmethod
    def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
