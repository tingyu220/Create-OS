from pathlib import Path


def test_roadmap_links_existing_reports():
    roadmap = Path("docs/novel-production-roadmap.md")
    assert roadmap.exists()
    text = roadmap.read_text(encoding="utf-8")
    assert "projects/validation_novel/production/reports/llm_writer_stress_report.md" in text
    assert "projects/validation_novel/production/reports/v2_backlog.md" in text


def test_readme_links_system_memory_boundaries():
    readme = Path("README.md").read_text(encoding="utf-8")
    memory_path = Path("DOMAIN/Memory.md")

    assert "DOMAIN/Memory.md" in readme
    assert memory_path.exists()
    memory = memory_path.read_text(encoding="utf-8")
    for term in ("candidate", "人工审批", "作用域", "来源追踪", "效果评估"):
        assert term in memory
