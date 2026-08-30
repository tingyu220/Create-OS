from __future__ import annotations
from pathlib import Path
import json, hashlib
from creative_os.domains.target_chapter_grouping import TargetChapterGroupingCandidate, encode_grouping

class TargetGroupingStore:
    def __init__(self, project_root):
        self.root = Path(project_root) / ".creative_os/publication_migration/groupings"
        self.root.mkdir(parents=True, exist_ok=True)
        self.records = self.root / "records.jsonl"
        self.head = self.root / "head.json"
        self.journal = self.root / "journal.json"

    def append(self, value: TargetChapterGroupingCandidate) -> str:
        current = self._current_payload(value.migration_id, value.target_chapter_id)
        if current is not None:
            if current["candidate_hash"] == value.candidate_hash:
                return value.candidate_hash
            raise ValueError("grouping_conflict")
        self._append_payload(json.loads(encode_grouping(value)))
        return value.candidate_hash

    def append_revision(
        self,
        value: TargetChapterGroupingCandidate,
        *,
        replaces_candidate_hash: str,
        reason: str,
    ) -> str:
        if not reason.strip():
            raise ValueError("grouping_revision_reason_required")
        current = self._current_payload(value.migration_id, value.target_chapter_id)
        if current is None or current["candidate_hash"] != replaces_candidate_hash:
            raise ValueError("grouping_revision_base_mismatch")
        if current["candidate_hash"] == value.candidate_hash:
            return value.candidate_hash
        payload = json.loads(encode_grouping(value))
        payload.update(
            kind="candidate_revision",
            replaces_candidate_hash=replaces_candidate_hash,
            reason=reason,
        )
        self._append_payload(payload)
        return value.candidate_hash

    def load_current(self, migration_id: str, target_chapter_id: int) -> TargetChapterGroupingCandidate:
        payload = self._current_payload(migration_id, target_chapter_id)
        if payload is None:
            raise ValueError("grouping_not_found")
        value = TargetChapterGroupingCandidate(
            migration_id=payload["migration_id"],
            target_chapter_id=payload["target_chapter_id"],
            unit_indices=tuple(payload["unit_indices"]),
            source_mappings=tuple(tuple(item) for item in payload["source_mappings"]),
            estimated_chinese_chars=payload["estimated_chinese_chars"],
            hook_evidence=tuple(payload["hook_evidence"]),
            short_chapter_disposition=payload.get("short_chapter_disposition"),
        )
        if value.candidate_hash != payload["candidate_hash"]:
            raise ValueError("grouping_hash_mismatch")
        return value

    def list_current(self, migration_id: str) -> tuple[TargetChapterGroupingCandidate, ...]:
        target_ids = sorted({
            payload["target_chapter_id"]
            for payload in self._payloads()
            if payload.get("kind") != "decision"
            and payload.get("migration_id") == migration_id
        })
        return tuple(self.load_current(migration_id, target_id) for target_id in target_ids)

    def append_decision(self, candidate_hash, *, actor="用户总控", reason="批准69章分组及短章处置", approved=True):
        if not approved or not actor.strip() or not reason.strip():
            raise ValueError("invalid_decision")
        candidate = next(
            (item for item in self._payloads() if item.get("candidate_hash") == candidate_hash),
            None,
        )
        if candidate is None:
            raise ValueError("candidate_not_found")
        decision = {
            "candidate_hash": candidate_hash,
            "actor": actor,
            "reason": reason,
            "approved": approved,
        }
        digest = hashlib.sha256(self._canonical_json(decision).encode()).hexdigest()
        self._append_payload({"kind": "decision", **decision, "decision_hash": digest})
        return digest

    def _current_payload(self, migration_id: str, target_chapter_id: int):
        current = None
        for payload in self._payloads():
            if payload.get("kind") == "decision":
                continue
            if payload.get("migration_id") == migration_id and payload.get("target_chapter_id") == target_chapter_id:
                current = payload
        return current

    def _payloads(self) -> list[dict]:
        if not self.records.exists():
            return []
        return [json.loads(line) for line in self.records.read_text(encoding="utf-8").splitlines()]

    def _append_payload(self, payload: dict) -> None:
        payload = dict(payload)
        payload["previous_hash"] = self.head.read_text(encoding="utf-8") if self.head.exists() else "0" * 64
        line = self._canonical_json(payload)
        with self.records.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        head_hash = hashlib.sha256(line.encode()).hexdigest()
        self.head.write_text(head_hash, encoding="utf-8")
        self.journal.write_text(json.dumps({"head_hash": head_hash}), encoding="utf-8")

    @staticmethod
    def _canonical_json(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
