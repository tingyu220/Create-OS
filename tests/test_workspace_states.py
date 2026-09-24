from pathlib import Path


WEB_ROOT = Path("creative_os/web")


def test_workspace_declares_semantic_copy_for_every_supported_state():
    script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    for label in (
        "正在读取工作区",
        "暂无可展示数据",
        "权威数据暂不可用",
        "数据已过期",
        "数据不完整",
        "数据已同步",
        "需要关注",
        "流程已阻塞",
        "读取失败",
    ):
        assert label in script


def test_workspace_state_banner_exposes_text_and_valid_next_action():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'id="workspace-state"' in html
    assert 'class="status-label"' in html
    assert 'id="workspace-state-action"' in html
    assert "renderWorkspaceState" in script
    assert "last_refresh_at" in script


def test_workspace_states_are_not_expressed_by_color_alone():
    css = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert ".workspace-state" in css
    assert ".status-label::before" in css
    assert "prefers-reduced-motion: reduce" in css
