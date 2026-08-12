from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ChapterTaskStatus:
    chapter: int
    status: str
    attempts: int
    elapsed_seconds: float
    issues: list[str]


def write_chapter_status(project_root: str | Path, status: ChapterTaskStatus) -> Path:
    status_dir = _status_dir(Path(project_root))
    status_dir.mkdir(parents=True, exist_ok=True)
    path = status_dir / f"chapter_{status.chapter:03d}_status.json"
    path.write_text(json.dumps(asdict(status), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_chapter_statuses(project_root: str | Path) -> list[ChapterTaskStatus]:
    root = Path(project_root)
    status_dir = _status_dir(root)
    if not status_dir.exists():
        return _load_legacy_llm_writer_statuses(root)
    statuses = [ChapterTaskStatus(**_read_json(path)) for path in sorted(status_dir.glob("chapter_*_status.json"))]
    if not statuses:
        return _load_legacy_llm_writer_statuses(root)
    return sorted(statuses, key=lambda item: item.chapter)


def _status_dir(root: Path) -> Path:
    if root.name == "production":
        return root / "runs" / "status"
    return root / "production" / "runs" / "status"


def _legacy_run_path(root: Path) -> Path:
    if root.name == "production":
        return root / "llm_writer_pilot" / "runs" / "llm_writer_pilot_run.json"
    return root / "production" / "llm_writer_pilot" / "runs" / "llm_writer_pilot_run.json"


def _load_legacy_llm_writer_statuses(root: Path) -> list[ChapterTaskStatus]:
    run_path = _legacy_run_path(root)
    if not run_path.exists():
        return []

    run = _read_json(run_path)
    chapter_results = run.get("chapter_results", {})
    attempts = run.get("attempts", {})
    metrics = run.get("metrics", {})
    statuses: list[ChapterTaskStatus] = []

    for chapter_key, issues in chapter_results.items():
        chapter = _chapter_number_from_key(chapter_key)
        if chapter is None:
            continue
        issue_list = [str(issue) for issue in issues] if isinstance(issues, list) else []
        chapter_metrics = metrics.get(chapter_key, {}) if isinstance(metrics, dict) else {}
        statuses.append(
            ChapterTaskStatus(
                chapter=chapter,
                status="fail" if issue_list else "pass",
                attempts=int(attempts.get(chapter_key, 0)) if isinstance(attempts, dict) else 0,
                elapsed_seconds=float(chapter_metrics.get("elapsed_seconds", 0.0)) if isinstance(chapter_metrics, dict) else 0.0,
                issues=issue_list,
            )
        )

    return sorted(statuses, key=lambda item: item.chapter)


def _chapter_number_from_key(chapter_key: str) -> int | None:
    try:
        return int(chapter_key.rsplit("_", 1)[1])
    except (IndexError, TypeError, ValueError):
        return None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
