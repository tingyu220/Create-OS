from pathlib import Path
import pytest

from creative_os.domains.production_readiness import ProductionReadinessAudit, ReadinessBlockedError


def test_empty_genre_and_logline_block_before_chapter_run(tmp_path: Path):
    (tmp_path / "brief.json").write_text('{"genre":"","logline":""}', encoding="utf-8")
    result = ProductionReadinessAudit(tmp_path).audit()
    assert result.status == "blocked"
    assert "genre_missing" in result.issues


def test_readiness_audit_binds_active_engagement_hashes():
    project_root = Path("projects/文明升阶")
    source = Path(r"D:\田雨\AI写作助手\NovelProject\Novels\文明升阶")
    approval = ProductionReadinessAudit(project_root).build_source_approval(project_root, source)
    assert approval["status"] == "approved"


def test_readiness_uses_original_novel_source_without_copying正文():
    authority = Path("projects/文明升阶")
    source = Path(r"D:\田雨\AI写作助手\NovelProject\Novels\文明升阶")
    approval = ProductionReadinessAudit(authority).build_source_approval(authority, source)
    assert approval["status"] == "approved"
    assert all("sha256" in item and "path" in item for item in approval["sources"])
