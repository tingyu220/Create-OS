from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from creative_os.domains.narrative_decision import (
    NarrativeChangeRequest,
    NarrativeDecision,
    NarrativeValidationError,
    WrittenTextStrategy,
)


@dataclass(frozen=True, slots=True)
class MigrationTask:
    chapter: int
    scope: str
    reason: str
    strategy: WrittenTextStrategy
    requires_approval: bool = True


@dataclass(frozen=True, slots=True)
class ChangeImpactReport:
    request_id: str
    affected_chapters: tuple[int, ...]
    affected_state_subjects: tuple[str, ...]
    affected_hooks: tuple[str, ...]
    tasks: tuple[MigrationTask, ...]


def analyze_change_impact(
    request: NarrativeChangeRequest,
    decisions: Iterable[NarrativeDecision] = (),
    *,
    written_chapters: Iterable[int] = (),
    state_snapshots: Iterable[dict[str, Any]] = (),
) -> ChangeImpactReport:
    """Create an auditable migration plan without changing any project data."""
    try:
        request.validate()
    except NarrativeValidationError:
        raise

    direct_chapters = set(request.affected_chapters)
    written = set(written_chapters)
    state_subjects = set(request.affected_state_subjects)
    hooks = set(request.affected_hooks)
    tasks: dict[tuple[int, str], MigrationTask] = {}

    for chapter in sorted(direct_chapters):
        scope = "written_text" if chapter in written else "future_decision"
        tasks[(chapter, scope)] = MigrationTask(
            chapter=chapter,
            scope=scope,
            reason=request.reason,
            strategy=request.written_text_strategy,
        )

    for decision in decisions:
        if decision.chapter < min(direct_chapters):
            continue
        serialized = decision.to_json()
        matched_hooks = [hook for hook in hooks if hook and hook in serialized]
        matched_subjects = [subject for subject in state_subjects if subject and subject in serialized]
        if not matched_hooks and not matched_subjects:
            continue
        reason_parts = []
        if matched_hooks:
            reason_parts.append("伏笔：" + "、".join(matched_hooks))
        if matched_subjects:
            reason_parts.append("状态：" + "、".join(matched_subjects))
        scope = "written_text" if decision.chapter in written else "future_decision"
        tasks[(decision.chapter, scope)] = MigrationTask(
            chapter=decision.chapter,
            scope=scope,
            reason="；".join(reason_parts),
            strategy=request.written_text_strategy,
        )

    for snapshot in state_snapshots:
        subject = str(snapshot.get("subject", ""))
        if subject not in state_subjects:
            continue
        kind = str(snapshot.get("kind", "state"))
        latest_change = str(snapshot.get("latest_change", ""))
        chapter = _chapter_from_change(latest_change)
        if chapter is None:
            continue
        tasks[(chapter, "state_snapshot")] = MigrationTask(
            chapter=chapter,
            scope="state_snapshot",
            reason=f"需要重新审核{kind}状态：{subject}",
            strategy=WrittenTextStrategy.LOCAL_REVISION,
        )

    return ChangeImpactReport(
        request_id=request.id,
        affected_chapters=tuple(sorted({task.chapter for task in tasks.values()})),
        affected_state_subjects=tuple(sorted(state_subjects)),
        affected_hooks=tuple(sorted(hooks)),
        tasks=tuple(sorted(tasks.values(), key=lambda task: (task.chapter, task.scope))),
    )


def _chapter_from_change(value: str) -> int | None:
    prefix = "state-chapter-"
    if not value.startswith(prefix):
        return None
    number = value[len(prefix):].split("-", 1)[0]
    return int(number) if number.isdigit() else None
