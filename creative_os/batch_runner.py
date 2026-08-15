from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BatchChapterStatus:
    chapter: int
    status: str
    attempts: int
    issues: list[str]


def load_completed_chapters(run_path: str | Path) -> set[int]:
    path = Path(run_path)
    if not path.exists():
        return set()

    data = json.loads(path.read_text(encoding="utf-8"))
    completed: set[int] = set()
    for key, issues in data.get("chapter_results", {}).items():
        if issues:
            continue
        completed.add(int(key.replace("chapter_", "")))
    return completed


def select_pending_chapters(chapters: list[int], completed: set[int], *, force: bool = False) -> list[int]:
    if force:
        return chapters
    return [chapter for chapter in chapters if chapter not in completed]
