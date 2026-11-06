from pathlib import Path


WEB_ROOT = Path("creative_os/web")


def test_workspace_declares_semantic_copy_for_every_supported_state():
    script = (WEB_ROOT / "author-home.js").read_text(encoding="utf-8")

    for label in (
        "正在读取稿件",
        "还没有稿件",
        "稿件暂时无法读取",
        "部分稿件需要核对",
        "稿件已同步",
        "项目检查记录了阻塞事项",
        "读取失败",
    ):
        assert label in script


def test_workspace_state_banner_exposes_text_and_valid_next_action():
    html = (WEB_ROOT / "author-home.html").read_text(encoding="utf-8")
    script = (WEB_ROOT / "author-home.js").read_text(encoding="utf-8")

    assert 'id="workspace-state"' in html
    assert 'class="status-label"' in html
    assert 'id="workspace-state-action"' in html
    assert "renderWorkspaceState" in script
    assert 'addEventListener("click", loadWorkspace)' in script
    assert '"error", "partial"' in script


def test_workspace_states_are_not_expressed_by_color_alone():
    css = (WEB_ROOT / "author-home.css").read_text(encoding="utf-8")

    assert ".workspace-state" in css
    assert ".status-label::before" in css
    assert "prefers-reduced-motion: reduce" in css
