from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from creative_os.domains.legacy_narrative_adapter import (
    LegacyNarrativeAdapter, MigrationReport,
)
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_memory import build_narrative_candidate_item
from creative_os.memory.model import MemoryEvidence, MemoryStatus
from creative_os.memory.store import JsonMemoryStore


@dataclass(frozen=True, slots=True)
class MigrationResult:
    report: MigrationReport
    candidate_item_id: str | None


class NarrativeMigrationService:
    """Recoverable candidate-only legacy migration; never mutates current pointer."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        self.journal_dir = self.project_root / ".creative_os" / "narrative_migrations"
        self.journal_dir.mkdir(parents=True, exist_ok=True)

    def migrate(self, legacy_item_id: str, legacy_version: int,
                legacy_content_hash: str, content: str, *, actor: str,
                completed: bool = False, fault: str | None = None) -> MigrationResult:
        if not isinstance(actor, str) or not actor.strip() or actor.strip().casefold() == "system":
            raise ValueError("migration requires a human actor")
        report = LegacyNarrativeAdapter.adapt(
            legacy_item_id, legacy_version, legacy_content_hash, content,
            completed=completed,
        )
        path = self.journal_dir / f"{report.idempotency_key}.json"
        if path.exists():
            journal = self._read_journal(path)
            self._match(journal, report, content, actor.strip())
        else:
            journal = self._journal("prepared", report, content, actor.strip())
            self._write(path, journal)
        if fault == "after_prepare":
            raise RuntimeError("fault after_prepare")
        result = self._materialize(report, actor.strip())
        self._write(path, self._journal(
            "candidate_written", report, content, actor.strip(), result.candidate_item_id,
        ))
        if fault == "after_candidate":
            raise RuntimeError("fault after_candidate")
        self._write(path, self._journal("committed", report, content, actor.strip(), result.candidate_item_id))
        return result

    def recover(self) -> tuple[MigrationResult, ...]:
        results = []
        for path in sorted(self.journal_dir.glob("*.json")):
            journal = self._read_journal(path)
            payload = journal["payload"]
            if path.stem != payload["idempotency_key"]:
                raise ValueError("migration journal filename mismatch")
            result = self.migrate(
                payload["source_item_id"], payload["source_version"],
                payload["source_content_hash"], payload["content"],
                actor=payload["actor"], completed=payload["completed"],
            )
            results.append(result)
        return tuple(results)

    def _materialize(self, report: MigrationReport, actor: str) -> MigrationResult:
        if report.replay_only:
            return MigrationResult(report, None)
        decision = report.candidate
        assert decision is not None
        item_id = f"{decision.contract_id}-v{decision.contract_version:04d}"
        store = JsonMemoryStore(self.project_root / ".creative_os" / "memory")
        expected = build_narrative_candidate_item(
            self.project_root, decision,
            evidence=(MemoryEvidence("legacy_migration", report.idempotency_key,
                                     "requires manual review"),),
            item_id=item_id,
        )
        try:
            existing = store.get_strict(item_id)
        except KeyError:
            store.add_immutable(expected)
        else:
            stable_fields = (
                "id", "kind", "scope", "scope_id", "title", "content", "applicability",
                "exceptions", "tags", "evidence", "status", "confidence", "version",
                "approved_by",
            )
            if any(getattr(existing, name) != getattr(expected, name) for name in stable_fields):
                raise ValueError("migration candidate conflict")
        return MigrationResult(report, item_id)

    @staticmethod
    def _journal(state: str, report: MigrationReport, content: str, actor: str,
                 candidate_item_id: str | None = None) -> dict[str, object]:
        payload = {
            "idempotency_key": report.idempotency_key,
            "source_item_id": report.source_item_id,
            "source_version": report.source_version,
            "source_content_hash": report.source_content_hash,
            "content": content, "actor": actor, "completed": report.replay_only,
            "candidate_item_id": candidate_item_id,
        }
        base = {"schema_version": 1, "state": state, "payload": payload}
        return {**base, "entry_hash": _hash(base)}

    @staticmethod
    def _match(journal: dict[str, object], report: MigrationReport,
               content: str, actor: str) -> None:
        payload = journal["payload"]
        expected = (report.idempotency_key, report.source_item_id, report.source_version,
                    report.source_content_hash, content, actor, report.replay_only)
        actual = (payload["idempotency_key"], payload["source_item_id"],
                  payload["source_version"], payload["source_content_hash"],
                  payload["content"], payload["actor"], payload["completed"])
        if actual != expected:
            raise ValueError("migration idempotency conflict")

    @staticmethod
    def _read_journal(path: Path) -> dict[str, object]:
        raw = path.read_bytes()
        try:
            value = json.loads(raw, object_pairs_hook=_no_duplicates)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("invalid migration journal") from error
        if (not isinstance(value, dict)
                or set(value) != {"schema_version", "state", "payload", "entry_hash"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or value["state"] not in {"prepared", "candidate_written", "committed"}
                or not isinstance(value["payload"], dict)
                or set(value["payload"]) != {"idempotency_key", "source_item_id", "source_version",
                    "source_content_hash", "content", "actor", "completed", "candidate_item_id"}
                or value["entry_hash"] != _hash({key: item for key, item in value.items() if key != "entry_hash"})
                or raw != _canonical(value) + b"\n"):
            raise ValueError("invalid migration journal")
        payload = value["payload"]
        if (not isinstance(payload["idempotency_key"], str)
                or len(payload["idempotency_key"]) != 64
                or not isinstance(payload["source_item_id"], str) or not payload["source_item_id"].strip()
                or type(payload["source_version"]) is not int or payload["source_version"] < 1
                or not isinstance(payload["source_content_hash"], str)
                or len(payload["source_content_hash"]) != 64
                or not isinstance(payload["content"], str)
                or not isinstance(payload["actor"], str) or not payload["actor"].strip()
                or type(payload["completed"]) is not bool
                or (payload["candidate_item_id"] is not None
                    and not isinstance(payload["candidate_item_id"], str))):
            raise ValueError("invalid migration journal payload")
        if (value["state"] == "prepared" and payload["candidate_item_id"] is not None
                or value["state"] in {"candidate_written", "committed"}
                and payload["completed"] is False and payload["candidate_item_id"] is None
                or payload["completed"] is True and payload["candidate_item_id"] is not None):
            raise ValueError("invalid migration journal state")
        for name in ("idempotency_key", "source_content_hash"):
            if any(ch not in "0123456789abcdef" for ch in payload[name]):
                raise ValueError("invalid migration journal sha256")
        return value

    @staticmethod
    def _write(path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(_canonical(value) + b"\n"); handle.flush(); os.fsync(handle.fileno())
            os.replace(name, path)
            _fsync_directory(path.parent)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate migration journal key")
        value[key] = item
    return value


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
