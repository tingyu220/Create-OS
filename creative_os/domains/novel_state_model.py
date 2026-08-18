from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from creative_os.memory.store import JsonMemoryStore


STATE_KINDS = ("character", "location", "timeline", "event", "hook", "information_boundary")
STATE_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class StateEvidence:
    source_chapter: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class StateChange:
    id: str
    kind: str
    subject: str
    status: str
    fields: dict[str, Any]
    evidence: list[StateEvidence]
    schema_version: int = STATE_SCHEMA_VERSION

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, content: str) -> "StateChange":
        payload = json.loads(content)
        if payload.get("schema_version") != STATE_SCHEMA_VERSION:
            raise ValueError("unsupported state change schema version")
        if payload.get("kind") not in STATE_KINDS:
            raise ValueError(f"unsupported state kind: {payload.get('kind')}")
        required = ("id", "subject", "status", "fields", "evidence")
        if any(key not in payload for key in required):
            raise ValueError("state change is missing required fields")
        evidence = [StateEvidence(**item) for item in payload["evidence"]]
        return cls(
            id=str(payload["id"]), kind=str(payload["kind"]), subject=str(payload["subject"]),
            status=str(payload["status"]), fields=dict(payload["fields"]), evidence=evidence,
            schema_version=int(payload["schema_version"]),
        )


def build_state_changes(project_root: str | Path, chapter_number: int) -> list[StateChange]:
    root = Path(project_root)
    path = root / "production" / "final_chapters" / f"chapter_{chapter_number:03d}.md"
    text = path.read_text(encoding="utf-8")
    source = path.relative_to(root).as_posix()
    evidence: Callable[[str], list[StateEvidence]] = lambda excerpt: [StateEvidence(source, excerpt)]
    structured = _load_structured_candidates(root, chapter_number)
    return structured or _generic_changes(chapter_number, text, evidence)


def _load_structured_candidates(root: Path, chapter: int) -> list[StateChange]:
    store = JsonMemoryStore(root / ".creative_os" / "memory")
    prefix = f"state-chapter-{chapter:03d}-"
    changes: list[StateChange] = []
    for item in store.list():
        if not item.id.startswith(prefix) or item.scope_id != root.name:
            continue
        try:
            changes.append(StateChange.from_json(item.content))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return changes


def _generic_changes(chapter: int, text: str, evidence: Callable[[str], list[StateEvidence]]) -> list[StateChange]:
    excerpt = _first_paragraph(text)
    return [
        StateChange(
            f"chapter-{chapter:03d}-event-main", "event", f"第{chapter}章事件", "candidate",
            {"outcome": excerpt}, evidence(excerpt),
        ),
        StateChange(
            f"chapter-{chapter:03d}-timeline-order", "timeline", f"第{chapter}章之后", "candidate",
            {"relative_order": f"发生在第{chapter}章内", "precision": "chapter_only"}, evidence(excerpt),
        ),
    ]


def _first_paragraph(text: str) -> str:
    paragraphs = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    return paragraphs[0][:360] if paragraphs else "正文为空，需人工补充证据。"
