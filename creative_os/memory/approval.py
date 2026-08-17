from __future__ import annotations

from collections.abc import Callable

from creative_os.memory.model import MemoryItem
from creative_os.memory.store import JsonMemoryStore


def approve_candidate(store: JsonMemoryStore, item_id: str, *, actor: str, note: str) -> MemoryItem:
    return _transition(store, item_id, actor=actor, note=note, action="approve", operation=lambda item: item.activate(actor=actor))


def reject_candidate(store: JsonMemoryStore, item_id: str, *, actor: str, note: str) -> MemoryItem:
    return _transition(store, item_id, actor=actor, note=note, action="reject", operation=lambda item: item.reject(actor=actor))


def archive_memory(store: JsonMemoryStore, item_id: str, *, actor: str, note: str) -> MemoryItem:
    return _transition(store, item_id, actor=actor, note=note, action="archive", operation=lambda item: item.archive(actor=actor))


def _transition(
    store: JsonMemoryStore,
    item_id: str,
    *,
    actor: str,
    note: str,
    action: str,
    operation: Callable[[MemoryItem], MemoryItem],
) -> MemoryItem:
    current = store.get(item_id)
    transitioned = operation(current)
    store.replace(transitioned)
    store.append_audit(action, transitioned, actor=actor.strip(), from_status=current.status, note=note.strip())
    return transitioned
