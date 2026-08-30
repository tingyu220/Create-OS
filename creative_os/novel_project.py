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
        project_path / ".creative_os" / "contexts",
        project_path / ".creative_os" / "knowledge",
        project_path / ".creative_os" / "reviews",
        project_path / ".creative_os" / "tasks",
        project_path / ".creative_os" / "backups",
        project_path / ".creative_os" / "llm_writer",
        project_path / ".creative_os" / "memory" / "items",
        project_path / ".creative_os" / "memory" / "revisions",
        production_path / "drafts",
        production_path / "final_chapters",
        production_path / "reports",
        production_path / "runs",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    _write_json(project_path / "project.json", {"id": folder_name, "name": title, "domain": "novel", "created_at": now})
    _write_json(project_path / "metadata.json", {"title": title, "author": author, "genre": genre, "created_at": now})
    _write_json(project_path / "state.json", {"current_phase": "brief", "current_goal": "完善新书 brief"})
    _write_json(project_path / "brief.json", {"title": title, "author": author, "genre": genre, "logline": ""})
    _write_json(project_path / "baseline.json", {"version": "v1", "created_at": now})
    (project_path / "production_log.jsonl").touch(exist_ok=True)
    (project_path / ".creative_os" / "memory" / "audit.jsonl").touch(exist_ok=True)
    _write_project_readme(project_path / "README.md", title)
    return project_path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_project_readme(path: Path, title: str) -> None:
    path.write_text(
        "\n".join(
            [
                f"# {title}",
                "",
                "## 正文位置",
                "",
                "- 研发全书稿：`production/drafts/final_draft_polished.md`",
                f"- 正式发布版：运行导出后查看 `releases/{title}/book.md`",
                "",
                "## 生产过程",
                "",
                "研发过程产物在 `.creative_os/` 和 `production/` 中维护。",
                "",
            ]
        ),
        encoding="utf-8",
    )
