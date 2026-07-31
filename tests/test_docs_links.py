from pathlib import Path


def test_roadmap_links_existing_reports():
    roadmap = Path("docs/novel-production-roadmap.md")
    assert roadmap.exists()
    text = roadmap.read_text(encoding="utf-8")
    assert "projects/validation_novel/production/reports/llm_writer_stress_report.md" in text
    assert "projects/validation_novel/production/reports/v2_backlog.md" in text
