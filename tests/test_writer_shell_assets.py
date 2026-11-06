from pathlib import Path


def test_writer_shell_has_editor_preview_and_save_controls():
    root = Path(__file__).parents[1] / "creative_os" / "web"
    html = (root / "writer.html").read_text(encoding="utf-8")
    script = (root / "writer.js").read_text(encoding="utf-8")
    assert 'id="editor"' in html
    assert 'id="preview"' in html
    assert "save_writer_draft" in script
    assert "/api/writer/chapters/" in script


def test_writer_shell_exposes_review_actions_after_agent_diff():
    root = Path(__file__).parents[1] / "creative_os" / "web"
    html = (root / "writer.html").read_text(encoding="utf-8")
    script = (root / "writer.js").read_text(encoding="utf-8")

    assert 'id="agent-review-actions"' in html
    assert 'id="accept-agent-draft"' in html
    assert 'id="reject-agent-draft"' in html
    assert 'id="revise-agent-draft"' in html
    assert 'agentConversation.review("reject")' in script


def test_writer_shell_has_three_pane_workspace_and_chapter_tabs():
    project_root = Path(__file__).parents[1]
    web_root = project_root / "creative_os" / "web"
    html = (web_root / "writer.html").read_text(encoding="utf-8")
    server = (project_root / "creative_os" / "web_workspace.py").read_text(encoding="utf-8")
    styles = (web_root / "writer.css").read_text(encoding="utf-8")

    assert '<link rel="stylesheet" href="/writer.css">' in html
    assert 'id="project-sidebar"' in html
    assert 'id="agent-workspace"' in html
    assert 'id="chapter-workspace"' in html
    assert 'id="formal-chapter-list"' in html
    assert 'id="draft-chapter-list"' in html
    for tab_name in ("editor", "preview", "diff", "versions", "details"):
        assert f'data-chapter-tab="{tab_name}"' in html
    for panel_name in ("navigation", "agent", "chapter"):
        assert f'data-workspace-panel="{panel_name}"' in html
    assert '"/writer.css": ("writer.css", "text/css; charset=utf-8")' in server
    assert "[hidden]{display:none!important}" in styles


def test_writer_shell_connects_navigation_tabs_and_mobile_panels():
    script = (Path(__file__).parents[1] / "creative_os" / "web" / "writer.js").read_text(encoding="utf-8")

    assert "function renderChapterNavigation(context)" in script
    assert "async function selectChapter(chapterNumber, source)" in script
    assert "function activateChapterTab(tabName)" in script
    assert "function activateWorkspacePanel(panelName)" in script
    assert "button.dataset.chapterNumber" in script
    assert "button.dataset.source" in script
    assert 'setAttribute("aria-selected"' in script
    assert "panel.hidden" in script
    assert 'querySelectorAll("[data-workspace-panel]")' in script
    assert 'selectChapter(Number(initialChapter), initialSource)' in script
    assert '["formal", "draft", "auto"].includes(requestedSource) ? requestedSource : "auto"' in script
    assert "source === currentSource" in script


def test_writer_shell_keeps_agent_review_version_and_publish_flow():
    script = (Path(__file__).parents[1] / "creative_os" / "web" / "writer.js").read_text(encoding="utf-8")

    assert 'activateChapterTab("candidate")' in script
    accept_handler = script.split('$("accept-agent-draft").addEventListener', 1)[1].split(
        '$("reject-agent-draft").addEventListener', 1
    )[0]
    assert "saveDraft" not in accept_handler
    assert 'agentConversation.review("accept")' in accept_handler
    assert 'agentConversation.review("reject")' in script
    assert "versionHistory = data.versions;" in script
    assert 'command_id: "publish_writer_draft"' in script
    assert '$("save-status").textContent' in script
    assert '$("agent-state-text").textContent' in script

