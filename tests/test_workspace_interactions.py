from pathlib import Path


WEB_ROOT = Path("creative_os/web")


def test_chapter_workspace_has_list_detail_and_command_hooks():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'id="chapter-list"' in html
    assert 'id="chapter-detail-drawer"' in html
    assert 'id="chapter-status-filter"' in html
    assert "data-chapter-key" in script
    assert "openChapterDetail" in script
    assert "/api/commands/start-chapter-run" in script


def test_overview_has_priority_work_panels_and_collapsed_evidence():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

    assert 'id="current-task"' in html
    assert 'id="recent-activity"' in html
    assert 'id="attention-items"' in html
    assert '<details class="evidence-details">' in html
    assert "当前任务" in html
    assert "最近活动" in html
    assert "重点关注" in html


def test_chapter_detail_drawer_has_accessible_close_and_evidence_region():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    css = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'aria-labelledby="chapter-detail-title"' in html
    assert 'id="chapter-detail-close"' in html
    assert 'id="chapter-detail-evidence"' in html
    assert "chapter-detail-drawer" in css
    assert "overflow-y: auto" in css
