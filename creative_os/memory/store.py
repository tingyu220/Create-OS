from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope, MemoryStatus


class MemoryStoreError(ValueError):
    pass


class ImmutableMemoryConflictError(MemoryStoreError):
    pass


_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()
_ITEM_FIELDS = frozenset(
    {
        "id",
        "kind",
        "scope",
        "scope_id",
        "title",
        "content",
        "applicability",
        "exceptions",
        "tags",
        "evidence",
        "status",
        "confidence",
        "version",
        "created_at",
        "updated_at",
        "approved_by",
    }
)
_EVIDENCE_FIELDS = frozenset({"source_type", "source_id", "note"})


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
        with _exclusive_store_lock(self.root / ".immutable.lock"):
            if path.exists():
                try:
                    existing = self._read_item_strict(path, expected_id=item.id)
                except MemoryStoreError as error:
                    raise ImmutableMemoryConflictError(f"immutable memory conflict: {item.id}") from error
                if existing != item:
                    raise ImmutableMemoryConflictError(f"immutable memory conflict: {item.id}")
                return existing
            self._write_item(path, item)
            return item

    def get(self, item_id: str) -> MemoryItem:
        path = self._item_path(item_id)
        if not path.exists():
            raise KeyError(item_id)
        return self._read_item(path)

    def get_strict(self, item_id: str) -> MemoryItem:
        """Read an exact, typed envelope without changing legacy get coercions."""
        path = self._item_path(item_id)
        if not path.exists():
            raise KeyError(item_id)
        return self._read_item_strict(path, expected_id=item_id)

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
        serialized = json.dumps(_item_to_dict(item), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        temporary: Path | None = None
        write_error: OSError | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                stream.write(serialized)
                temporary = Path(stream.name)
            temporary.replace(path)
        except OSError as error:
            write_error = error
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink()
                except OSError as error:
                    raise MemoryStoreError(f"temporary memory cleanup failed: {path}") from error
        if write_error is not None:
            raise MemoryStoreError(f"memory write failed: {path}") from write_error

    def _read_item(self, path: Path) -> MemoryItem:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _item_from_dict(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise MemoryStoreError(f"invalid memory file: {path}") from exc

    def _read_item_strict(self, path: Path, *, expected_id: str) -> MemoryItem:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            _validate_strict_payload(payload, expected_id=expected_id)
            return _item_from_dict(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise MemoryStoreError(f"invalid strict memory envelope: {path}") from exc


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


def _validate_strict_payload(payload: object, *, expected_id: str) -> None:
    if type(payload) is not dict or set(payload) != _ITEM_FIELDS:
        raise ValueError("memory envelope fields must be exact")

    text_fields = (
        "id",
        "kind",
        "scope",
        "scope_id",
        "title",
        "content",
        "status",
        "created_at",
        "updated_at",
    )
    if any(type(payload[field]) is not str for field in text_fields):
        raise TypeError("memory envelope text fields must be strings")
    if payload["id"] != expected_id:
        raise ValueError("memory envelope id does not match its physical path")

    for field in ("applicability", "exceptions", "tags"):
        values = payload[field]
        if type(values) is not list or any(type(value) is not str for value in values):
            raise TypeError(f"memory envelope {field} must be a string list")
    if payload["tags"] != sorted(set(payload["tags"])):
        raise ValueError("memory envelope tags must be canonical and unique")

    evidence = payload["evidence"]
    if type(evidence) is not list:
        raise TypeError("memory envelope evidence must be a list")
    for entry in evidence:
        if type(entry) is not dict or set(entry) != _EVIDENCE_FIELDS:
            raise ValueError("memory evidence fields must be exact")
        if any(type(entry[field]) is not str for field in _EVIDENCE_FIELDS):
            raise TypeError("memory evidence fields must be strings")

    if type(payload["confidence"]) is not float:
        raise TypeError("memory envelope confidence must be a float")
    if type(payload["version"]) is not int:
        raise TypeError("memory envelope version must be an integer")
    if payload["approved_by"] is not None and type(payload["approved_by"]) is not str:
        raise TypeError("memory envelope approved_by must be text or null")


@contextmanager
def _exclusive_store_lock(path: Path) -> Iterator[None]:
    try:
        local_lock = _local_lock(path)
        with local_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a+b") as stream:
                stream.seek(0, os.SEEK_END)
                if stream.tell() == 0:
                    stream.write(b"\0")
                    stream.flush()
                _lock_stream(stream)
                try:
                    yield
                finally:
                    _unlock_stream(stream)
    except MemoryStoreError:
        raise
    except OSError as error:
        raise MemoryStoreError(f"immutable memory lock failed: {path}") from error


def _local_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.Lock())


def _lock_stream(stream: Any) -> None:
    stream.seek(0)
    if os.name == "nt":
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
    else:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def _unlock_stream(stream: Any) -> None:
    stream.seek(0)
    if os.name == "nt":
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
