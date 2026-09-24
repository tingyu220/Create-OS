from pathlib import Path


WEB_ROOT = Path("creative_os/web")


def test_workspace_shell_exposes_semantic_sidebar_topbar_and_main_regions():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

    assert 'id="workspace-shell"' in html
    assert 'id="workspace-sidebar"' in html
    assert 'id="workspace-topbar"' in html
    assert 'id="workspace-main"' in html
    assert 'id="workspace-navigation"' in html


def test_workspace_navigation_is_rendered_from_domain_neutral_configuration():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'id="workspace-navigation"' in html
    assert "workspaceNavigation" in javascript
    assert "renderWorkspaceNavigation" in javascript
    assert 'label: "总览"' in javascript
    assert 'label: "章节"' in javascript
    assert 'label: "质量"' in javascript
    assert 'label: "运行"' in javascript


def test_workspace_shell_uses_fixed_viewport_and_independent_scroll_regions():
    css = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert "100vh" in css
    assert "workspace-shell" in css
    assert "workspace-sidebar" in css
    assert "workspace-main" in css
    assert "overflow-y: auto" in css
    assert "min-height: 0" in css


def test_workspace_shell_defines_semantic_tokens_focus_reduced_motion_and_narrow_layout():
    css = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    for token in (
        "--surface",
        "--text",
        "--text-muted",
        "--border",
        "--accent",
        "--success",
        "--warning",
        "--danger",
        "--space-",
        "--radius",
        "--focus-ring",
    ):
        assert token in css

    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "@media" in css
    assert "max-width: 760px" in css
