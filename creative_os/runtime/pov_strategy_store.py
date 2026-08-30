from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from creative_os.domains.pov_strategy_codec import POVStrategyCodecError, decode_candidate_set, encode_candidate_set
from creative_os.domains.pov_strategy_codec import _evidence, _option
from creative_os.domains.pov_strategy_model import HumanPOVOverride, POVSelectionRecord, POVStrategyAuditRecord, POVStrategyCandidateSet


class POVStrategyStoreError(ValueError):
    pass


class POVStrategyAuditStore:
    """保存运行时审计工件；它不是 Memory，也不提供活动事实查询。"""

    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root) / ".creative_os" / "runtime" / "pov_strategy"
        self.root.mkdir(parents=True, exist_ok=True)

    def append_candidate(self, value: POVStrategyCandidateSet) -> POVStrategyAuditRecord:
        path = self._path(value.id)
        if path.exists():
            return self.read(value.id)
        for record in self.list():
            if (
                record.candidate.target_chapter == value.target_chapter
                and record.status not in {"expired", "superseded"}
            ):
                self.set_status(record.candidate.id, "superseded", actor="candidate-recompute")
        candidate_json = encode_candidate_set(value)
        path.write_text(candidate_json, encoding="utf-8")
        self._append_event(value.id, "proposed", "system", {
            "candidate_digest": hashlib.sha256(candidate_json.encode("utf-8")).hexdigest(),
            "input_fingerprint": value.input_fingerprint,
            "schema_version": "pov-strategy-candidate-v1",
        })
        return self.read(value.id)

    def current_for_chapter(self, chapter: int) -> POVStrategyAuditRecord:
        matches = tuple(
            record for record in self.list()
            if record.candidate.target_chapter == chapter
            and record.status not in {"expired", "superseded"}
        )
        if len(matches) != 1:
            raise POVStrategyStoreError("chapter must have exactly one current POV candidate")
        return matches[0]

    def set_status(self, candidate_id: str, status: str, *, actor: str) -> POVStrategyAuditRecord:
        if status not in {"proposed", "selected", "expired", "superseded", "recompute_failed"}:
            raise POVStrategyStoreError("invalid status")
        self.read(candidate_id)
        self._append_event(candidate_id, status, actor, {})
        return self.read(candidate_id)

    def append_selection(self, selection) -> None:
        self.read(selection.candidate_id)
        self._append_event(selection.candidate_id, "selected", selection.actor, {"selection": asdict(selection)})

    def latest_selection_payload(self, candidate_id: str) -> dict | None:
        events = self._events(candidate_id)
        for event in reversed(events):
            if "selection" in event.get("payload", {}):
                return event["payload"]["selection"]
        return None

    def load_selection(self, candidate_id: str) -> POVSelectionRecord:
        payload = self.latest_selection_payload(candidate_id)
        if payload is None:
            raise POVStrategyStoreError("missing selected POV strategy")
        override_data = payload.get("override")
        override = None
        if override_data:
            override = HumanPOVOverride(
                _option(override_data["option"]), override_data["reason"],
                tuple(_evidence(value) for value in override_data["evidence_refs"]),
            )
        return POVSelectionRecord(
            payload["candidate_id"], payload["option_id"], payload["selection_kind"],
            payload["actor"], payload["input_fingerprint"], payload["selected_at"], override,
        )

    def read(self, candidate_id: str) -> POVStrategyAuditRecord:
        try:
            candidate_json = self._path(candidate_id).read_text(encoding="utf-8")
            digest = hashlib.sha256(candidate_json.encode("utf-8")).hexdigest()
            candidate = decode_candidate_set(candidate_json)
            events = self._events(candidate_id)
            anchor = events[0].get("payload", {}).get("candidate_digest")
            if anchor != digest:
                raise POVStrategyStoreError("pov strategy candidate anchor mismatch")
            latest = events[-1]
            return POVStrategyAuditRecord(candidate, latest["status"], latest["actor"], latest["timestamp"], digest)
        except (OSError, KeyError, json.JSONDecodeError, POVStrategyCodecError) as exc:
            raise POVStrategyStoreError(f"pov strategy artifact was tampered: {exc}") from exc

    def list(self) -> tuple[POVStrategyAuditRecord, ...]:
        return tuple(self.read(path.stem) for path in sorted(self.root.glob("*.json")) if not path.name.endswith(".events.json"))

    def _append_event(self, candidate_id, status, actor, payload):
        events = self._events(candidate_id, allow_missing=True)
        previous_hash = events[-1]["event_hash"] if events else "0" * 64
        event = {"candidate_id": candidate_id, "status": status, "actor": actor, "timestamp": datetime.now(timezone.utc).isoformat(), "payload": payload, "previous_hash": previous_hash}
        encoded = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        event["event_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self._event_path(candidate_id).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def _events(self, candidate_id, allow_missing=False):
        path = self._event_path(candidate_id)
        if not path.exists():
            if allow_missing:
                return []
            raise POVStrategyStoreError("missing audit events")
        result = []
        previous_hash = "0" * 64
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            event_hash = event.pop("event_hash")
            encoded = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if event.get("previous_hash") != previous_hash or hashlib.sha256(encoded.encode("utf-8")).hexdigest() != event_hash:
                raise POVStrategyStoreError("pov strategy audit metadata was tampered")
            event["event_hash"] = event_hash
            result.append(event)
            previous_hash = event_hash
        return result

    def _path(self, candidate_id):
        if not candidate_id or any(char in candidate_id for char in '<>:"/\\|?*'):
            raise POVStrategyStoreError("invalid candidate id")
        return self.root / f"{candidate_id}.json"

    def _event_path(self, candidate_id):
        return self.root / f"{candidate_id}.events.jsonl"
