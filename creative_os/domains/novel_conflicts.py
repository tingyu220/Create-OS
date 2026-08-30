from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from creative_os.domains.novel_baseline import BaselineArtifact, NovelBaselineDraft


@dataclass(frozen=True, slots=True)
class ImportConflict:
    code: str
    severity: str
    subject: str
    values: list[str]
    sources: list[str]
    resolution_required: bool = True


def detect_import_conflicts(draft: NovelBaselineDraft) -> list[ImportConflict]:
    conflicts = [
        *_duplicate_chapters(draft),
        *_volume_count_conflicts(draft),
        *_completed_chapter_count_conflicts(draft),
    ]
    return sorted(conflicts, key=lambda item: (item.code, item.subject, item.sources))


def _duplicate_chapters(draft: NovelBaselineDraft) -> list[ImportConflict]:
    grouped: dict[int, list[str]] = defaultdict(list)
    for chapter in draft.canon_chapters:
        grouped[chapter.number].append(chapter.source_path)
    return [
        ImportConflict(
            code="duplicate_chapter_number",
            severity="high",
            subject=f"chapter_{number:03d}",
            values=[str(number)],
            sources=sorted(paths),
        )
        for number, paths in grouped.items()
        if len(paths) > 1
    ]


def _volume_count_conflicts(draft: NovelBaselineDraft) -> list[ImportConflict]:
    claims = _claims([*draft.world_rules, *draft.plot_milestones], r"(?:规划|重构为|全书|共|预计)?\s*(\d+)\s*卷")
    values = {value for value, _ in claims}
    if len(values) < 2:
        return []
    return [
        ImportConflict(
            code="volume_count_conflict",
            severity="high",
            subject="volume_count",
            values=sorted(values),
            sources=sorted({source for _, source in claims}),
        )
    ]


def _completed_chapter_count_conflicts(draft: NovelBaselineDraft) -> list[ImportConflict]:
    claims = _claims(
        [*draft.world_rules, *draft.plot_milestones, *draft.style_constraints],
        r"(?:当前总章节数|已完成(?:正文)?|完成章节数|已重写(?:/新增)?|已新增)\s*[：:]?\s*(\d+)\s*章?",
    )
    actual = str(len(draft.canon_chapters))
    conflicting = [(value, source) for value, source in claims if value != actual]
    if not conflicting:
        return []
    return [
        ImportConflict(
            code="completed_chapter_count_conflict",
            severity="high",
            subject="completed_chapter_count",
            values=sorted({actual, *(value for value, _ in conflicting)}),
            sources=sorted({source for _, source in conflicting} | {chapter.source_path for chapter in draft.canon_chapters}),
        )
    ]


def _claims(artifacts: list[BaselineArtifact], pattern: str) -> list[tuple[str, str]]:
    matcher = re.compile(pattern)
    claims: list[tuple[str, str]] = []
    for artifact in artifacts:
        for match in matcher.finditer(artifact.content):
            claims.append((match.group(1), artifact.source_path))
    return claims
