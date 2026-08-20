from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope, MemoryStatus


class MemoryStoreError(ValueError):
    pass


class JsonMemoryStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.items_dir = self.root / "items"
        self.revisions_dir = self.root / "revisions"
        self.audit_path = self.root / "audit.jsonl"
        self.items_dir.mkdir(parents=True, exist_ok=True)
        self.revisions_dir.mkdir(parents=True, exist_ok=True)
        self.audit_path.touch(exist_ok=True)

    def add_candidate(self, item: MemoryItem) -> None:
        if item.status != MemoryStatus.CANDIDATE:
            raise MemoryStoreError("add_candidate requires candidate status")
        path = self._item_path(item.id)
        if path.exists():
            raise MemoryStoreError(f"memory already exists: {item.id}")
        self._write_item(path, item)

    def add_immutable(self, item: MemoryItem) -> MemoryItem:
        """Create an item once; an exact repeated write is idempotent."""
        path = self._item_path(item.id)
        if path.exists():
            existing = self._read_item(path)
            if existing != item:
                raise MemoryStoreError(f"immutable memory conflict: {item.id}")
            return existing
        self._write_item(path, item)
        return item

    def get(self, item_id: str) -> MemoryItem:
        path = self._item_path(item_id)
        if not path.exists():
            raise KeyError(item_id)
        return self._read_item(path)

    def list(self) -> list[MemoryItem]:
        return [self._read_item(path) for path in sorted(self.items_dir.glob("*.json"))]

    def save_revision(self, item_id: str, *, content: str, actor: str) -> MemoryItem:
        if not actor.strip():
            raise MemoryStoreError("revision requires actor")
        current = self.get(item_id)
        revision_dir = self.revisions_dir / item_id
        revision_dir.mkdir(parents=True, exist_ok=True)
        self._write_item(revision_dir / f"v{current.version:04d}.json", current)
        revised = replace(
            current,
            content=content,
            status=MemoryStatus.CANDIDATE,
            approved_by=None,
            version=current.version + 1,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._write_item(self._item_path(item_id), revised)
        self.append_audit("revise", revised, actor=actor, from_status=current.status, note="")
        return revised

    def revisions(self, item_id: str) -> list[MemoryItem]:
        directory = self.revisions_dir / item_id
        if not directory.exists():
            return []
        return [self._read_item(path) for path in sorted(directory.glob("v*.json"))]

    def replace(self, item: MemoryItem) -> None:
        if not self._item_path(item.id).exists():
            raise KeyError(item.id)
        self._write_item(self._item_path(item.id), item)

    def append_audit(
        self,
        action: str,
        item: MemoryItem,
        *,
        actor: str,
        from_status: MemoryStatus,
        note: str,
    ) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "memory_id": item.id,
            "actor": actor,
            "from_status": from_status.value,
            "to_status": item.status.value,
            "note": note,
        }
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def _item_path(self, item_id: str) -> Path:
        if not item_id or any(char in item_id for char in '<>:"/\\|?*'):
            raise MemoryStoreError(f"invalid memory id: {item_id}")
        return self.items_dir / f"{item_id}.json"

    def _write_item(self, path: Path, item: MemoryItem) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(_item_to_dict(item), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _read_item(self, path: Path) -> MemoryItem:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _item_from_dict(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise MemoryStoreError(f"invalid memory file: {path}") from exc


def _item_to_dict(item: MemoryItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind.value,
        "scope": item.scope.value,
        "scope_id": item.scope_id,
        "title": item.title,
        "content": item.content,
        "applicability": list(item.applicability),
        "exceptions": list(item.exceptions),
        "tags": sorted(item.tags),
        "evidence": [
            {"source_type": evidence.source_type, "source_id": evidence.source_id, "note": evidence.note}
            for evidence in item.evidence
        ],
        "status": item.status.value,
        "confidence": item.confidence,
        "version": item.version,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "approved_by": item.approved_by,
    }


def _item_from_dict(payload: dict[str, Any]) -> MemoryItem:
    return MemoryItem(
        id=str(payload["id"]),
        kind=MemoryKind(payload["kind"]),
        scope=MemoryScope(payload["scope"]),
        scope_id=str(payload["scope_id"]),
        title=str(payload["title"]),
        content=str(payload["content"]),
        applicability=tuple(str(value) for value in payload["applicability"]),
        exceptions=tuple(str(value) for value in payload["exceptions"]),
        tags=frozenset(str(value) for value in payload["tags"]),
        evidence=tuple(MemoryEvidence(**value) for value in payload["evidence"]),
        status=MemoryStatus(payload["status"]),
        confidence=float(payload["confidence"]),
        version=int(payload["version"]),
        created_at=str(payload["created_at"]),
        updated_at=str(payload["updated_at"]),
        approved_by=payload.get("approved_by"),
    )
