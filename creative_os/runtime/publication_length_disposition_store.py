from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from creative_os.domains.contract_record_filesystem import TrustedStoreFilesystem
from creative_os.domains.publication_migration_model import (
    LengthDisposition,
    LengthIntervalKind,
    PublicationLengthPolicy,
    ShortChapterApproval,
    length_policy_hash,
)


_HASH = re.compile(r"^[0-9a-f]{64}$")
_ZERO = "0" * 64
_CHINESE = re.compile(r"[\u4e00-\u9fff]")
_RULESET = "publication-length-policy-v1"
_IO_HOOK = lambda _event, _path: None


class PublicationLengthDispositionIntegrityError(ValueError):
    pass


class PublicationLengthDispositionConflict(ValueError):
    pass


class PublicationLengthDispositionStore:
    """正文完成后的长度例外审批权威源。"""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).absolute()
        self.root = self.project_root / ".creative_os" / "publication_migration" / "length_dispositions"
        self.records_path = self.root / "records.jsonl"
        self.head_path = self.root / "head.json"
        self.journal_path = self.root / "journal.json"
        self._filesystem = TrustedStoreFilesystem(
            self.project_root, (self.root,), self.root / ".length-disposition.lock",
            error_type=PublicationLengthDispositionIntegrityError,
            conflict_type=PublicationLengthDispositionConflict,
            hook=lambda event, path: _IO_HOOK(event, path),
        )

    def close(self) -> None:
        self._filesystem.close()

    def append_decision(
        self, migration_id: str, target_chapter: int, body_text: str,
        policy: PublicationLengthPolicy,
        actor: str, reason: str, *, decided_at: str | None = None,
    ) -> LengthDisposition | ShortChapterApproval:
        _text(migration_id, "migration_id")
        if type(target_chapter) is not int or target_chapter <= 0:
            raise ValueError("target_chapter_invalid")
        if not isinstance(body_text, str) or not isinstance(policy, PublicationLengthPolicy):
            raise TypeError("body_text_and_policy_required")
        body_hash = hashlib.sha256(body_text.encode("utf-8")).hexdigest()
        character_count = len(_CHINESE.findall(body_text))
        if character_count < policy.short_min:
            kind = LengthIntervalKind.SHORT_CHAPTER
        elif policy.soft_max < character_count <= policy.hard_max:
            kind = LengthIntervalKind.SOFT_LIMIT
        else:
            raise ValueError("length_interval_not_approvable")
        _text(actor, "actor")
        _text(reason, "reason")
        timestamp = decided_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        _timestamp(timestamp)
        binding = (migration_id, target_chapter, body_hash, length_policy_hash(policy), kind.value)
        with self._locked():
            records = self._recover_locked()
            existing = next((item for item in records if _binding(item) == binding), None)
            if existing is not None:
                if (existing.actor, existing.reason, existing.decided_at) == (actor, reason, timestamp):
                    return existing
                raise PublicationLengthDispositionConflict("decision_conflict")
            sequence = len(records) + 1
            payload = {
                "migration_id": migration_id, "target_chapter": target_chapter,
                "body_hash": body_hash, "policy_hash": binding[3], "interval_kind": kind.value,
                "actor": actor, "reason": reason, "decided_at": timestamp,
                "chinese_character_count": character_count, "ruleset_version": _RULESET,
                "policy_thresholds": _policy_payload(policy),
            }
            decision_hash = _digest({"domain": "publication_length_disposition_v1", **payload})
            disposition_id = f"length:{migration_id}:{target_chapter}:{kind.value}:{decision_hash[:16]}"
            decision = _decision_from_payload({
                **payload, "disposition_id": disposition_id, "decision_hash": decision_hash,
                "record_sequence": sequence,
            })
            envelope = _envelope({**_decision_payload(decision),
                                  "chinese_character_count": character_count,
                                  "ruleset_version": _RULESET,
                                  "policy_thresholds": _policy_payload(policy)}, sequence,
                                 _envelope_hash_at(self._read_envelopes(), -1))
            self._write_prepared(envelope)
            self._publish_envelope(envelope)
            return decision

    def require_exact(self, reference: LengthDisposition | ShortChapterApproval,
                      body_text: str | None = None, policy: PublicationLengthPolicy | None = None):
        if not isinstance(reference, (LengthDisposition, ShortChapterApproval)):
            raise TypeError("length_disposition_reference_required")
        with self._locked():
            records = self._recover_locked()
            exact = next((item for item in records if item.disposition_id == reference.disposition_id), None)
            if exact != reference:
                raise PublicationLengthDispositionIntegrityError("decision_exact_not_found")
            payload = next(item["payload"] for item in self._read_envelopes()
                           if item["payload"]["disposition_id"] == reference.disposition_id)
            if body_text is not None or policy is not None:
                if not isinstance(body_text, str) or not isinstance(policy, PublicationLengthPolicy):
                    raise TypeError("body_text_and_policy_required")
                actual_count = len(_CHINESE.findall(body_text))
                if (hashlib.sha256(body_text.encode("utf-8")).hexdigest() != reference.body_hash
                        or length_policy_hash(policy) != reference.policy_hash
                        or payload["chinese_character_count"] != actual_count
                        or payload["ruleset_version"] != _RULESET
                        or payload["policy_thresholds"] != _policy_payload(policy)):
                    raise PublicationLengthDispositionIntegrityError("decision_actual_binding_mismatch")
            return exact

    def recover(self) -> tuple[LengthDisposition | ShortChapterApproval, ...]:
        with self._locked():
            return self._recover_locked()

    @contextmanager
    def _locked(self):
        with self._filesystem.exclusive_lock():
            self._filesystem.validate_all()
            self._validate_layout()
            try:
                yield
            finally:
                self._filesystem.validate_all()
                self._validate_layout()

    def _validate_layout(self) -> None:
        allowed = {".length-disposition.lock", "records.jsonl", "head.json", "journal.json"}
        if set(self._filesystem.list_names(self.root)) - allowed:
            raise PublicationLengthDispositionIntegrityError("authority_layout_tampered")

    def _recover_locked(self):
        envelopes = list(self._read_envelopes())
        if self._filesystem.exists_regular(self.journal_path):
            journal_bytes = self._filesystem.read_bytes(self.journal_path)
            if not journal_bytes:
                self._validate_head(envelopes)
                return tuple(_decision_from_payload(item["payload"]) for item in envelopes)
            try:
                journal = _load(journal_bytes)
            except Exception as cause:
                raise PublicationLengthDispositionIntegrityError("journal_tampered") from cause
            if not isinstance(journal, dict) or set(journal) != {"state", "envelope"} or journal["state"] != "prepared":
                raise PublicationLengthDispositionIntegrityError("journal_tampered")
            prepared = journal["envelope"]
            sequence = prepared.get("sequence")
            prior_hash = _ZERO if sequence == 1 else (
                envelopes[sequence - 2]["envelope_hash"] if type(sequence) is int and sequence - 2 < len(envelopes) else ""
            )
            _validate_envelope(prepared, sequence, prior_hash)
            if len(envelopes) + 1 == prepared["sequence"]:
                envelopes.append(prepared)
                self._write_envelopes(envelopes)
            elif not (prepared["sequence"] <= len(envelopes)
                      and envelopes[prepared["sequence"] - 1] == prepared):
                raise PublicationLengthDispositionIntegrityError("journal_conflict")
            self._write_head(envelopes)
            self._filesystem.atomic_write_bytes(self.journal_path, b"", expected=self._filesystem.read_bytes(self.journal_path))
        self._validate_head(envelopes)
        return tuple(_decision_from_payload(item["payload"]) for item in envelopes)

    def _read_envelopes(self) -> tuple[dict, ...]:
        if not self._filesystem.exists_regular(self.records_path):
            return ()
        raw = self._filesystem.read_bytes(self.records_path)
        try:
            lines = raw.decode("utf-8").splitlines()
            envelopes = tuple(_load(line.encode("utf-8")) for line in lines if line)
            previous = _ZERO
            for sequence, envelope in enumerate(envelopes, start=1):
                _validate_envelope(envelope, sequence, previous)
                previous = envelope["envelope_hash"]
            ids = [item["payload"]["disposition_id"] for item in envelopes]
            bindings = [tuple(item["payload"][key] for key in
                        ("migration_id", "target_chapter", "body_hash", "policy_hash", "interval_kind"))
                        for item in envelopes]
            if len(ids) != len(set(ids)) or len(bindings) != len(set(bindings)):
                raise PublicationLengthDispositionIntegrityError("decision_identity_duplicate")
            return envelopes
        except PublicationLengthDispositionIntegrityError:
            raise
        except Exception as cause:
            raise PublicationLengthDispositionIntegrityError("record_chain_tampered") from cause

    def _publish_envelope(self, envelope: dict) -> None:
        envelopes = [*self._read_envelopes(), envelope]
        self._write_envelopes(envelopes)
        self._write_head(envelopes)
        prior = self._filesystem.read_bytes(self.journal_path)
        self._filesystem.atomic_write_bytes(self.journal_path, b"", expected=prior)

    def _write_prepared(self, envelope: dict) -> None:
        payload = _canonical({"state": "prepared", "envelope": envelope})
        expected = self._filesystem.read_bytes(self.journal_path) if self._filesystem.exists_regular(self.journal_path) else None
        self._filesystem.atomic_write_bytes(self.journal_path, payload, expected=expected)

    def _write_envelopes(self, envelopes) -> None:
        payload = b"".join(_canonical(item) + b"\n" for item in envelopes)
        expected = self._filesystem.read_bytes(self.records_path) if self._filesystem.exists_regular(self.records_path) else None
        self._filesystem.atomic_write_bytes(self.records_path, payload, expected=expected)

    def _write_head(self, envelopes) -> None:
        payload = _canonical({"count": len(envelopes), "head_hash": _envelope_hash_at(envelopes, -1)})
        expected = self._filesystem.read_bytes(self.head_path) if self._filesystem.exists_regular(self.head_path) else None
        self._filesystem.atomic_write_bytes(self.head_path, payload, expected=expected)

    def _validate_head(self, envelopes) -> None:
        expected = {"count": len(envelopes), "head_hash": _envelope_hash_at(envelopes, -1)}
        if envelopes and not self._filesystem.exists_regular(self.head_path):
            raise PublicationLengthDispositionIntegrityError("head_missing")
        if self._filesystem.exists_regular(self.head_path):
            try:
                actual = _load(self._filesystem.read_bytes(self.head_path))
            except Exception as cause:
                raise PublicationLengthDispositionIntegrityError("head_tampered") from cause
            if actual != expected:
                raise PublicationLengthDispositionIntegrityError("head_tampered")


def _binding(item):
    return (item.migration_id, item.target_chapter, item.body_hash, item.policy_hash, item.interval_kind.value)


def _decision_payload(item):
    return {name: (getattr(item, name).value if name == "interval_kind" else getattr(item, name)) for name in (
        "disposition_id", "decision_hash", "record_sequence", "migration_id", "target_chapter",
        "body_hash", "policy_hash", "interval_kind", "actor", "reason", "decided_at",
    )}


def _decision_from_payload(value):
    required = {"disposition_id", "decision_hash", "record_sequence", "migration_id", "target_chapter",
                "body_hash", "policy_hash", "interval_kind", "actor", "reason", "decided_at",
                "chinese_character_count", "ruleset_version", "policy_thresholds"}
    if not isinstance(value, dict) or set(value) != required:
        raise PublicationLengthDispositionIntegrityError("decision_shape_invalid")
    count = value["chinese_character_count"]
    thresholds = value["policy_thresholds"]
    try:
        policy = PublicationLengthPolicy(**thresholds)
    except Exception as cause:
        raise PublicationLengthDispositionIntegrityError("decision_policy_invalid") from cause
    if (type(count) is not int or count < 0 or value["ruleset_version"] != _RULESET
            or length_policy_hash(policy) != value["policy_hash"]):
        raise PublicationLengthDispositionIntegrityError("decision_count_or_ruleset_invalid")
    kind = LengthIntervalKind(value["interval_kind"])
    if ((kind is LengthIntervalKind.SHORT_CHAPTER and count >= policy.short_min)
            or (kind is LengthIntervalKind.SOFT_LIMIT and not policy.soft_max < count <= policy.hard_max)):
        raise PublicationLengthDispositionIntegrityError("decision_interval_invalid")
    domain_payload = {key: item for key, item in value.items()
                      if key not in {"disposition_id", "decision_hash", "record_sequence"}}
    expected_hash = _digest({"domain": "publication_length_disposition_v1", **domain_payload})
    expected_id = f"length:{value['migration_id']}:{value['target_chapter']}:{kind.value}:{expected_hash[:16]}"
    if value["decision_hash"] != expected_hash or value["disposition_id"] != expected_id:
        raise PublicationLengthDispositionIntegrityError("decision_domain_hash_invalid")
    cls = LengthDisposition if kind is LengthIntervalKind.SOFT_LIMIT else ShortChapterApproval
    reference = {key: item for key, item in value.items()
                 if key not in {"chinese_character_count", "ruleset_version", "policy_thresholds"}}
    return cls(**{**reference, "interval_kind": kind})


def _envelope(payload, sequence, previous):
    base = {"schema_version": 1, "sequence": sequence, "previous_hash": previous,
            "payload_hash": _digest(payload), "payload": payload}
    return {**base, "envelope_hash": _digest(base)}


def _validate_envelope(value, sequence, previous):
    try:
        if (not isinstance(value, dict) or set(value) != {"schema_version", "sequence", "previous_hash", "payload_hash", "payload", "envelope_hash"}
                or value["schema_version"] != 1 or value["sequence"] != sequence or value["previous_hash"] != previous
                or value["payload_hash"] != _digest(value["payload"])
                or value["envelope_hash"] != _digest({key: value[key] for key in value if key != "envelope_hash"})):
            raise ValueError
        decision = _decision_from_payload(value["payload"])
        if decision.record_sequence != sequence:
            raise ValueError
    except PublicationLengthDispositionIntegrityError:
        raise
    except Exception as cause:
        raise PublicationLengthDispositionIntegrityError("record_chain_tampered") from cause


def _envelope_hash_at(envelopes, index):
    return envelopes[index]["envelope_hash"] if envelopes else _ZERO


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load(payload):
    return json.loads(payload.decode("utf-8"))


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}_required")


def _hash(value, name):
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError(f"{name}_invalid")


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as cause:
        raise ValueError("decided_at_invalid") from cause
    if parsed.tzinfo is None:
        raise ValueError("decided_at_invalid")


def _policy_payload(policy):
    return {"target_min": policy.target_min, "target_max": policy.target_max,
            "soft_max": policy.soft_max, "hard_max": policy.hard_max,
            "short_min": policy.short_min,
            "hook_tail_window_codepoints": policy.hook_tail_window_codepoints}
