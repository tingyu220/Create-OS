from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WINDOWS_FORBIDDEN_CHARS = r'[<>:"/\\|?*]'


def sanitize_project_folder_name(title: str) -> str:
    cleaned = re.sub(WINDOWS_FORBIDDEN_CHARS, "", title).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        raise ValueError("title must contain at least one valid folder character")
    return cleaned


def create_novel_project(root: str | Path, title: str, *, author: str = "", genre: str = "") -> Path:
    projects_root = Path(root)
    folder_name = sanitize_project_folder_name(title)
    project_path = projects_root / folder_name
    production_path = project_path / "production"

    for directory in [
        project_path / "design",
        project_path / "reviews",
        project_path / "reports",
        production_path / "drafts",
        production_path / "final_chapters",
        production_path / "final_chapters_v2",
        production_path / "llm_writer_pilot",
        production_path / "reports",
        production_path / "reviews",
        production_path / "runs",
        production_path / "tasks",
        production_path / "backups",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    _write_json(project_path / "project.json", {"id": folder_name, "name": title, "domain": "novel", "created_at": now})
    _write_json(project_path / "metadata.json", {"title": title, "author": author, "genre": genre, "created_at": now})
    _write_json(project_path / "state.json", {"current_phase": "brief", "current_goal": "完善新书 brief"})
    _write_json(project_path / "brief.json", {"title": title, "author": author, "genre": genre, "logline": ""})
    _write_json(project_path / "baseline.json", {"version": "v1", "created_at": now})
    (project_path / "production_log.jsonl").touch(exist_ok=True)
    return project_path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
