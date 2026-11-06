from pathlib import Path


WEB_ROOT = Path("creative_os/web")


def test_chapter_workspace_lists_real_manuscripts_and_opens_writer():
    html = (WEB_ROOT / "author-home.html").read_text(encoding="utf-8")
    script = (WEB_ROOT / "author-home.js").read_text(encoding="utf-8")

    assert 'id="chapter-list"' in html
    assert 'id="chapter-filter"' in html
    assert 'id="open-chapter-form"' in html
    assert 'item.has_formal' in script
    assert 'item.has_draft' in script
    assert 'item.pending_candidates' in script
    assert 'writerLink(item.chapter_number' in script


def test_overview_prioritizes_continue_and_separate_manuscript_counts():
    html = (WEB_ROOT / "author-home.html").read_text(encoding="utf-8")

    assert 'id="continue-writing"' in html
    assert 'id="recent-manuscripts"' in html
    assert 'id="attention-items"' in html
    assert all(f'id="{kind}-count"' in html for kind in ("formal", "draft", "candidate"))
    assert 'id="attention-shortcut"' in html
    assert "最近稿件" in html
    assert "需要你处理" in html


def test_author_home_has_accessible_forms_and_diagnostic_entry():
    html = (WEB_ROOT / "author-home.html").read_text(encoding="utf-8")
    css = (WEB_ROOT / "author-home.css").read_text(encoding="utf-8")

    assert 'aria-labelledby="open-title"' in html
    assert 'label for="chapter-number"' in html
    assert 'aria-labelledby="attention-title"' in html
    assert 'id="diagnostic-link"' in html
    assert ":focus-visible" in css
    assert "overflow-y: auto" in css
