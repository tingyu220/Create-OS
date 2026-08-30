from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.memory.store import JsonMemoryStore
from creative_os.runtime import AppendOnlyEventLog, EventType


class FeedbackOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVISED = "revised"
    REGENERATED = "regenerated"


class FeedbackValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FeedbackRecord:
    id: str
    project_id: str
    task_id: str
    result_ref: str
    outcome: FeedbackOutcome
    reason: str
    chapter_number: int | None = None
    character_names: tuple[str, ...] = ()
    revision_ref: str | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.project_id.strip() or not self.task_id.strip() or not self.result_ref.strip():
            raise FeedbackValidationError("feedback requires id, project_id, task_id and result_ref")
        if self.outcome != FeedbackOutcome.ACCEPTED and not self.reason.strip():
            raise FeedbackValidationError("non-accepted feedback requires a reason")
        if self.chapter_number is not None and self.chapter_number < 1:
            raise FeedbackValidationError("chapter_number must be positive")

    @classmethod
    def new(
        cls,
        *,
        project_id: str,
        task_id: str,
        result_ref: str,
        outcome: FeedbackOutcome,
        reason: str = "",
        chapter_number: int | None = None,
        character_names: Iterable[str] = (),
        revision_ref: str | None = None,
    ) -> "FeedbackRecord":
        now = datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha256(
            f"{project_id}|{task_id}|{result_ref}|{outcome.value}|{reason}|{now}".encode("utf-8")
        ).hexdigest()[:16]
        return cls(
            id=f"feedback-{digest}",
            project_id=project_id,
            task_id=task_id,
            result_ref=result_ref,
            outcome=outcome,
            reason=reason.strip(),
            chapter_number=chapter_number,
            character_names=tuple(dict.fromkeys(name.strip() for name in character_names if name.strip())),
            revision_ref=revision_ref,
            created_at=now,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        payload["character_names"] = list(self.character_names)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "FeedbackRecord":
        return cls(
            id=str(payload["id"]),
            project_id=str(payload["project_id"]),
            task_id=str(payload["task_id"]),
            result_ref=str(payload["result_ref"]),
            outcome=FeedbackOutcome(str(payload["outcome"])),
            reason=str(payload.get("reason", "")),
            chapter_number=int(payload["chapter_number"]) if payload.get("chapter_number") is not None else None,
            character_names=tuple(str(value) for value in payload.get("character_names", [])),
            revision_ref=str(payload["revision_ref"]) if payload.get("revision_ref") is not None else None,
            created_at=str(payload.get("created_at", "")),
        )


class FeedbackStore:
    def __init__(self, project_root: str | Path) -> None:
        root = Path(project_root)
        self.path = root / ".creative_os" / "runtime" / "feedback.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, feedback: FeedbackRecord) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(feedback.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")

    def list(self) -> list[FeedbackRecord]:
        records: list[FeedbackRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(FeedbackRecord.from_dict(json.loads(line)))
        return records


def record_feedback(project_root: str | Path, feedback: FeedbackRecord) -> None:
    root = Path(project_root)
    if feedback.project_id != root.name:
        raise FeedbackValidationError("feedback project_id does not match project root")
    FeedbackStore(root).append(feedback)
    if feedback.outcome in {FeedbackOutcome.REVISED, FeedbackOutcome.REGENERATED}:
        AppendOnlyEventLog(root / ".creative_os" / "runtime" / "events.jsonl").append_simple(
            EventType.USER_REVISED,
            task_id=feedback.task_id,
            payload={"feedback_id": feedback.id, "outcome": feedback.outcome.value, "reason": feedback.reason},
        )


def create_lesson_candidate(
    project_root: str | Path,
    feedback: FeedbackRecord,
    *,
    title: str,
    content: str,
    character_name: str | None = None,
    applicability: Iterable[str] = ("writing", "planning", "review"),
) -> MemoryItem:
    root = Path(project_root)
    if feedback.project_id != root.name:
        raise FeedbackValidationError("feedback project_id does not match project root")
    if not title.strip() or not content.strip():
        raise FeedbackValidationError("lesson requires title and content")
    character = character_name.strip() if character_name else None
    tags = {"lesson", "feedback", "novel"}
    if character:
        tags.update({"character_lesson", f"character:{character}"})
        scope_title = f"人物：{character}"
    else:
        tags.add("project_lesson")
        scope_title = "项目"
    item_id = _lesson_id(root.name, character, content)
    item = MemoryItem.new_candidate(
        id=item_id,
        kind=MemoryKind.EXPERIENCE,
        scope=MemoryScope.PROJECT,
        scope_id=root.name,
        title=f"{scope_title} Lesson：{title.strip()}",
        content=json.dumps(
            {"schema_version": 1, "kind": "character_lesson" if character else "project_lesson", "character": character, "content": content.strip(), "feedback_id": feedback.id},
            ensure_ascii=False,
            sort_keys=True,
        ),
        evidence=(MemoryEvidence("feedback", feedback.id, feedback.reason),),
        applicability=applicability,
        tags=tags,
        confidence=0.7,
    )
    JsonMemoryStore(root / ".creative_os" / "memory").add_candidate(item)
    return item


def _lesson_id(project_id: str, character: str | None, content: str) -> str:
    digest = hashlib.sha256(f"{project_id}|{character or 'project'}|{content.strip()}".encode("utf-8")).hexdigest()[:16]
    return f"lesson-{digest}"
