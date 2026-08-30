from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from creative_os.memory.model import MemoryStatus
from creative_os.memory.store import JsonMemoryStore


STATE_SCHEMA_VERSION = 2
_CHAPTER_ID = re.compile(r"^state-chapter-(?P<chapter>\d+)-")

# These fields describe a growing set of facts. All other fields are snapshots
# and use the latest approved chapter value.
ADDITIVE_FIELDS = frozenset({
    "known_facts", "unknown_facts", "withheld_facts", "knows", "must_not_assume",
    "participants", "current_areas", "present_characters", "access_constraints", "anchors",
    "alternatives", "future_pressures",
})


class StateMergeConflictError(ValueError):
    """Raised when one chapter proposes two incompatible values."""


def materialize_active_state(project_root: str | Path) -> list[Path]:
    root = Path(project_root)
    store = JsonMemoryStore(root / ".creative_os" / "memory")
    active_items = [
        item for item in store.list()
        if item.status == MemoryStatus.ACTIVE
        and item.id.startswith("state-chapter-")
        and item.scope_id == root.name
    ]
    active_items.sort(key=lambda item: (_chapter_number(item.id), item.id))

    grouped: dict[tuple[str, str], list[tuple[Any, dict[str, Any]]]] = {}
    for item in active_items:
        payload = _load_state_payload(item.content)
        if payload is None:
            continue
        key = (str(payload["kind"]), str(payload["subject"]))
        grouped.setdefault(key, []).append((item, payload))

    written: list[Path] = []
    for (kind, subject), entries in sorted(grouped.items()):
        fields: dict[str, Any] = {}
        field_sources: dict[str, dict[str, Any]] = {}
        for item, payload in entries:
            chapter = _chapter_number(item.id)
            fields, field_sources = _merge_fields(
                fields, field_sources, payload.get("fields", {}), chapter, item.id,
            )
            change_path = root / ".creative_os" / "state" / "changes" / f"{item.id}.json"
            _write(change_path, {"memory_id": item.id, "state_change": payload})
            written.append(change_path)

        latest_item, latest_payload = entries[-1]
        snapshot_path = root / ".creative_os" / "state" / "snapshots" / kind / f"{_safe(subject)}.json"
        _write(snapshot_path, {
            "schema_version": STATE_SCHEMA_VERSION,
            "kind": kind,
            "subject": subject,
            "fields": fields,
            "field_sources": field_sources,
            "latest_change": latest_item.id,
            "evidence": latest_payload.get("evidence", []),
        })
        written.append(snapshot_path)
    return written


def load_active_snapshots(project_root: str | Path) -> list[dict[str, Any]]:
    project_root = Path(project_root)
    snapshot_root = project_root / ".creative_os" / "state" / "snapshots"
    store = JsonMemoryStore(project_root / ".creative_os" / "memory")
    active_ids = {item.id for item in store.list() if item.status == MemoryStatus.ACTIVE}
    return [
        payload for path in sorted(snapshot_root.glob("*/*.json"))
        if (payload := _load(path)).get("schema_version") == STATE_SCHEMA_VERSION
        and payload.get("latest_change") in active_ids
    ]


def compact_active_snapshots(
    project_root: str | Path,
    *,
    max_chars: int = 6000,
) -> list[dict[str, Any]]:
    """Return a bounded projection for Context; never mutates active snapshots."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    snapshots = [_compact_snapshot(snapshot) for snapshot in load_active_snapshots(project_root)]
    snapshots.sort(key=lambda item: (_kind_priority(str(item.get("kind"))), str(item.get("subject"))) )
    selected: list[dict[str, Any]] = []
    used = 2  # JSON array brackets
    for snapshot in snapshots:
        size = len(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
        separator = 2 if selected else 0  # default json.dumps uses ", "
        if used + separator + size > max_chars:
            continue
        selected.append(snapshot)
        used += separator + size
    return selected


def _merge_fields(
    current: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    incoming: dict[str, Any],
    chapter: int,
    change_id: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not isinstance(incoming, dict):
        raise ValueError("state fields must be an object")
    current = dict(current)
    sources = dict(sources)
    for field, value in incoming.items():
        if field not in current:
            current[field] = _copy_json(value)
            sources[field] = {"chapter": chapter, "change_id": change_id}
            continue
        previous = sources.get(field, {"chapter": -1, "change_id": "legacy"})
        if field in ADDITIVE_FIELDS:
            if not isinstance(current[field], list) or not isinstance(value, list):
                raise StateMergeConflictError(f"field {field} changed between list and non-list")
            current[field] = _unique(current[field] + value)
            if chapter >= int(previous["chapter"]):
                sources[field] = {"chapter": chapter, "change_id": change_id}
            continue
        if current[field] == value:
            if chapter >= int(previous["chapter"]):
                sources[field] = {"chapter": chapter, "change_id": change_id}
            continue
        previous_chapter = int(previous["chapter"])
        if chapter == previous_chapter:
            raise StateMergeConflictError(
                f"conflicting values for {field} in chapter {chapter}: {previous['change_id']} vs {change_id}"
            )
        if chapter > previous_chapter:
            current[field] = _copy_json(value)
            sources[field] = {"chapter": chapter, "change_id": change_id}
    return current, sources


def _load_state_payload(content: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != STATE_SCHEMA_VERSION:
        return None
    if payload.get("kind") not in {"character", "location", "timeline", "event", "hook", "information_boundary"}:
        return None
    if not payload.get("subject"):
        return None
    return payload


def _chapter_number(change_id: str) -> int:
    match = _CHAPTER_ID.match(change_id)
    return int(match.group("chapter")) if match else -1


def _compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": snapshot.get("schema_version", STATE_SCHEMA_VERSION),
        "kind": snapshot.get("kind", ""),
        "subject": snapshot.get("subject", ""),
        "fields": _compact_value(snapshot.get("fields", {})),
        "latest_change": snapshot.get("latest_change", ""),
    }


def _compact_value(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 360 else value[:360].rstrip() + "…"
    if isinstance(value, list):
        compacted = [_compact_value(item) for item in value[:8]]
        if len(value) > 8:
            compacted.append(f"还有{len(value) - 8}项")
        return compacted
    if isinstance(value, dict):
        return {str(key): _compact_value(item) for key, item in value.items()}
    return value


def _kind_priority(kind: str) -> int:
    return {"character": 0, "hook": 1, "location": 2, "information_boundary": 3, "timeline": 4, "event": 5}.get(kind, 9)


def _unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return result


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in "_-" else "_" for char in value)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
