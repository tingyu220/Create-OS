import json

import pytest

from creative_os.publication_browser_workbench import (
    FakeBrowser,
    PersistentBrowserWorkbenchController,
    ReconnectionMismatch,
)


def test_state_persists_without_password_and_reconnect_requires_same_page(tmp_path):
    browser = FakeBrowser()
    page = browser.new_page(work_id="book-a", title="临时作品", chapter_number=1)
    path = tmp_path / "session.json"
    controller = PersistentBrowserWorkbenchController(path, browser=browser)
    controller.open(page)
    controller.bind_target(work_id="book-a", work_title="临时作品", chapter_number=1, current_step="fill_chapter")
    controller.set_operation(operation_id="op-a", content="正文一", step="fill_chapter")
    controller.fill("正文一")
    controller.pause("safe")

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["session_id"] == browser.session_id
    assert raw["page_id"] == page.page_id
    assert raw["operation_id"] == "op-a"
    assert "password" not in json.dumps(raw, ensure_ascii=False).lower()

    browser.crash()
    controller.poll()
    assert controller.state.status == "browser_session_interrupted"

    restored_browser = FakeBrowser(session_id=browser.session_id)
    restored_page = restored_browser.new_page(work_id="book-a", title="临时作品", chapter_number=1)
    restored_page.page_id = page.page_id
    restored_page.fill("正文一")
    assert controller.reconnect(restored_browser)["reconnect_verified"] is True
    assert controller.resume()["status"] == "connected"


def test_reconnect_checks_target_and_hash_before_resume(tmp_path):
    browser = FakeBrowser()
    page = browser.new_page(work_id="book-a", title="临时作品", chapter_number=2)
    controller = PersistentBrowserWorkbenchController(tmp_path / "state.json")
    controller.open(page)
    controller.bind_target(work_id="book-a", work_title="临时作品", chapter_number=2)
    controller.set_operation(operation_id="op", content="正文", step="publishing")
    controller.fill("正文")
    controller.pause("immediate")
    browser.crash()

    other = FakeBrowser(session_id=browser.session_id)
    wrong = other.new_page(work_id="book-b", title="另一部", chapter_number=2)
    wrong.page_id = page.page_id
    wrong.fill("正文")
    with pytest.raises(ReconnectionMismatch):
        controller.reconnect(other)


def test_platform_tabs_are_isolated_and_panel_is_fixed_right(tmp_path):
    tomato = FakeBrowser(platform="tomato")
    other = FakeBrowser(platform="other")
    tomato_page = tomato.new_page(work_id="book-a", title="A")
    other_page = other.new_page(work_id="book-a", title="A")
    one = PersistentBrowserWorkbenchController(tmp_path / "tomato.json")
    two = PersistentBrowserWorkbenchController(tmp_path / "other.json")
    one.open(tomato_page)
    two.open(other_page)
    assert one.state.session_id != two.state.session_id
    assert 'data-fixed-side="right"' in one.render_panel_html()
    assert one.view()["password_saved"] is False


def test_connect_cannot_replace_persisted_session_or_page_before_reconcile(tmp_path):
    browser = FakeBrowser()
    page = browser.new_page(work_id="book-a", title="临时作品", chapter_number=1)
    controller = PersistentBrowserWorkbenchController(tmp_path / "state.json")
    controller.open(page)
    controller.set_operation(operation_id="op", content="正文", step="fill_chapter")
    controller.mark_interrupted("browser_session_interrupted")

    other = FakeBrowser()
    other_page = other.new_page(work_id="book-b", title="另一部", chapter_number=1)
    with pytest.raises(ReconnectionMismatch):
        controller.connect(other, other_page)
    assert controller.browser is browser
    assert controller.state.session_id == browser.session_id
    assert controller.state.page_id == page.page_id

    same_session = FakeBrowser(session_id=browser.session_id)
    replacement = same_session.new_page(work_id="book-b", title="另一部", chapter_number=1)
    replacement.page_id = page.page_id
    with pytest.raises(ReconnectionMismatch):
        controller.connect(same_session, replacement)
    assert controller.browser is browser
    assert controller.state.work_id == "book-a"
