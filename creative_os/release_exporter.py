from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from creative_os.novel_project import sanitize_project_folder_name


REPORTS_TO_EXPORT = (
    "production_report.md",
    "v11_acceptance_report.md",
    "llm_writer_stress_report.md",
)


def export_novel_release(project_root: str | Path, output_root: str | Path) -> Path:
    project_path = Path(project_root)
    production_path = project_path / "production"
    title = _project_title(project_path)
    release_path = Path(output_root) / sanitize_project_folder_name(title)

    release_path.mkdir(parents=True, exist_ok=True)
    chapters_path = release_path / "chapters"
    reports_path = release_path / "reports"
    chapters_path.mkdir(exist_ok=True)
    reports_path.mkdir(exist_ok=True)

    book_source = production_path / "drafts" / "final_draft_polished.md"
    if not book_source.exists():
        raise FileNotFoundError(book_source)
    shutil.copyfile(book_source, release_path / "book.md")

    chapter_sources = sorted((production_path / "final_chapters").glob("chapter_*.md"))
    if not chapter_sources:
        raise FileNotFoundError(production_path / "final_chapters")
    for chapter_source in chapter_sources:
        shutil.copyfile(chapter_source, chapters_path / chapter_release_name(chapter_source))

    metadata = _read_json(project_path / "metadata.json") if (project_path / "metadata.json").exists() else {}
    metadata["title"] = title
    metadata["chapter_count"] = len(chapter_sources)
    _write_json(release_path / "metadata.json", metadata)

    for report_name in REPORTS_TO_EXPORT:
        report_source = production_path / "reports" / report_name
        if report_source.exists():
            shutil.copyfile(report_source, reports_path / report_name)

    _write_release_readme(release_path / "README.md", title, len(chapter_sources))
    return release_path


def chapter_release_name(chapter_path: Path) -> str:
    text = chapter_path.read_text(encoding="utf-8")
    first_heading = next((line.strip() for line in text.splitlines() if line.startswith("#")), "")
    match = re.search(r"第\s*(\d+)\s*章[：:]\s*(.+)", first_heading)
    if match:
        number = int(match.group(1))
        title = sanitize_project_folder_name(match.group(2))
    else:
        number_match = re.search(r"chapter_(\d+)", chapter_path.stem)
        number = int(number_match.group(1)) if number_match else 0
        title = chapter_path.stem
    return f"{number:03d}-{title}.md"


def _project_title(project_path: Path) -> str:
    project_json = project_path / "project.json"
    if project_json.exists():
        name = _read_json(project_json).get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return project_path.name


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_release_readme(path: Path, title: str, chapter_count: int) -> None:
    path.write_text(
        "\n".join(
            [
                f"# {title}",
                "",
                "## 正式正文",
                "",
                "- 全书：`book.md`",
                "- 章节：`chapters/`",
                "",
                "## 说明",
                "",
                f"- 章节数：{chapter_count}",
                "- `reports/` 仅保留正式发布相关报告。",
                "- 研发过程产物仍保留在原项目目录，不进入发布版。",
                "",
            ]
        ),
        encoding="utf-8",
    )
