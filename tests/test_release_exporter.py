import json
from pathlib import Path

from creative_os.release_exporter import chapter_release_name, export_novel_release


def test_chapter_release_name_uses_number_and_title(tmp_path):
    chapter = tmp_path / "chapter_001.md"
    chapter.write_text("# 第 1 章：回城\n\n正文", encoding="utf-8")

    assert chapter_release_name(chapter) == "001-回城.md"


def test_chapter_release_name_sanitizes_windows_forbidden_chars(tmp_path):
    chapter = tmp_path / "chapter_012.md"
    chapter.write_text("# 第 12 章：雾城:回声?\n\n正文", encoding="utf-8")

    assert chapter_release_name(chapter) == "012-雾城回声.md"


def test_export_novel_release_creates_clean_reader_facing_layout(tmp_path):
    project_root = tmp_path / "projects" / "validation_novel"
    production = project_root / "production"
    final_chapters = production / "final_chapters"
    reports = production / "reports"
    drafts = production / "drafts"
    final_chapters.mkdir(parents=True)
    reports.mkdir(parents=True)
    drafts.mkdir(parents=True)
    (project_root / "project.json").write_text(
        json.dumps({"name": "雾城回声"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (project_root / "metadata.json").write_text(
        json.dumps({"planned_chapters": 2}, ensure_ascii=False),
        encoding="utf-8",
    )
    (drafts / "final_draft_polished.md").write_text("# 第 1 章：回城\n\n正文", encoding="utf-8")
    (final_chapters / "chapter_001.md").write_text("# 第 1 章：回城\n\n正文", encoding="utf-8")
    (final_chapters / "chapter_002.md").write_text("# 第 2 章：旧灯巷\n\n正文", encoding="utf-8")
    (reports / "production_report.md").write_text("# Production", encoding="utf-8")
    (reports / "v11_acceptance_report.md").write_text("# Quality", encoding="utf-8")
    (reports / "llm_writer_stress_report.md").write_text("# Stress", encoding="utf-8")

    release_path = export_novel_release(project_root, tmp_path / "releases")

    assert release_path == tmp_path / "releases" / "雾城回声"
    assert (release_path / "README.md").exists()
    assert (release_path / "book.md").read_text(encoding="utf-8").startswith("# 第 1 章")
    assert sorted(path.name for path in (release_path / "chapters").glob("*.md")) == [
        "001-回城.md",
        "002-旧灯巷.md",
    ]
    assert (release_path / "metadata.json").exists()
    assert sorted(path.name for path in (release_path / "reports").glob("*.md")) == [
        "llm_writer_stress_report.md",
        "production_report.md",
        "v11_acceptance_report.md",
    ]
    assert not (release_path / "runs").exists()
    assert not (release_path / "backups").exists()
    assert not (release_path / "llm_writer_pilot").exists()


def test_export_accepts_book_title_project_root(tmp_path):
    project_root = tmp_path / "projects" / "雾城回声"
    production = project_root / "production"
    (production / "drafts").mkdir(parents=True)
    (production / "final_chapters").mkdir(parents=True)
    (project_root / "project.json").write_text('{"name":"雾城回声"}', encoding="utf-8")
    (project_root / "metadata.json").write_text("{}", encoding="utf-8")
    (production / "drafts" / "final_draft_polished.md").write_text("# 第 1 章：回城\n\n正文", encoding="utf-8")
    (production / "final_chapters" / "chapter_001.md").write_text("# 第 1 章：回城\n\n正文", encoding="utf-8")

    release = export_novel_release(project_root, tmp_path / "releases")

    assert release == tmp_path / "releases" / "雾城回声"
    assert (release / "book.md").exists()
    assert (release / "chapters" / "001-回城.md").exists()
