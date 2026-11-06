"""隔离验证持久化发布工作台和多平台发布全链。

只使用临时目录、Fake 浏览器、随机本地端口和内存适配器；不会访问真实番茄、账号、模型或 8877。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.publication_browser_workbench import (
    FakeBrowser,
    PersistentBrowserWorkbenchController,
    ReconnectionMismatch,
)
from creative_os.publication_models import ChapterSnapshot, PublicationStatus
from creative_os.publication_web import PublicationOrchestrator, create_publication_server
from creative_os.tomato_browser_adapter import FakeTomatoPage, TargetSpec, TomatoBrowserAdapter


CHECKS = {name: True for name in PublicationOrchestrator.CHECKS}


def snapshot(book_id: str, chapter: int, revision: str, text: str) -> ChapterSnapshot:
    return ChapterSnapshot(book_id=book_id, chapter_number=chapter, source_revision=revision, content=text)


def target(book_id: str, chapter: int) -> TargetSpec:
    return TargetSpec(work_id=book_id, title=f"临时作品-{book_id}", chapter_number=chapter, chapter_title=f"第{chapter}章")


def run_chain(book_id: str, root: Path, *, drop_response: bool = False) -> tuple[dict, list[dict]]:
    page = FakeTomatoPage(work_id=book_id, title=f"临时作品-{book_id}")
    adapter = TomatoBrowserAdapter(page)
    browser = FakeBrowser(platform="tomato")
    browser_page = browser.new_page(work_id=book_id, title=page.title, chapter_number=1)
    session = PersistentBrowserWorkbenchController(root / "browser-session.json")
    session.open(browser_page)
    orchestrator = PublicationOrchestrator(adapter)
    events: list[dict] = []
    for chapter in (1, 2):
        browser_page.chapter_number = chapter
        browser_page.chapter_title = f"第{chapter}章"
        formal = snapshot(book_id, chapter, f"r{chapter}", f"{book_id} 正式稿第{chapter}章。")
        target_spec = target(book_id, chapter)
        adapter.connect(require_existing=True)
        task = orchestrator.submit(formal, target_spec, checks=CHECKS)
        session.bind_target(work_id=book_id, work_title=page.title, chapter_number=chapter, current_step="checking")
        session.set_operation(operation_id=task.operation_id, content=formal.content, step="checking")
        if drop_response and chapter == 2:
            page.drop_next_response = True
        result = orchestrator.run(task.operation_id)
        session.set_step(result.get("current_step", "publishing"))
        events.append({"book_id": book_id, "chapter": chapter, "operation_id": task.operation_id, "response": result, "content_sha256": formal.content_sha256})
        if result["status"] == "unknown":
            reconciled = orchestrator.reconcile(task.operation_id)
            events.append({"book_id": book_id, "chapter": chapter, "operation_id": task.operation_id, "response": reconciled, "reconciled": True})
        # 读取编排器台账中的证据。核对成功后这里必须看到重建后的
        # published evidence，而不是适配器丢响应时缓存的旧 unknown。
        evidence = orchestrator.state(task.operation_id).get("evidence") or adapter.capture_evidence(task.operation_id)
        events.append({"book_id": book_id, "chapter": chapter, "operation_id": task.operation_id, "evidence": evidence})
    return {"session": session.view(), "events": events, "adapter_page": page}, events


def write_screenshots(output: Path, controller: PersistentBrowserWorkbenchController) -> list[str]:
    """加载真实 writer.html、writer.css 和 writer.js，生成隔离浏览器布局证据。"""
    web_root = ROOT / "creative_os" / "web"
    (output / "publication-workbench.html").write_text(
        (web_root / "writer.html").read_text(encoding="utf-8"), encoding="utf-8"
    )
    class WriterHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_root), **kwargs)
        def do_GET(self):  # noqa: N802
            if self.path.split("?", 1)[0] == "/writer":
                self.path = "/writer.html" + (("?" + self.path.split("?", 1)[1]) if "?" in self.path else "")
            return super().do_GET()
        def log_message(self, format, *args):
            return
    server = ThreadingHTTPServer(("127.0.0.1", 0), WriterHandler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    paths: list[str] = []
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-background-networking", "--disable-sync"])
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"http://127.0.0.1:{server.server_port}/writer?chapter=1", wait_until="domcontentloaded")
            assert page.locator(".publication-browser-workbench").count() == 1
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            wide = output / "publication-1440.png"
            page.screenshot(path=str(wide), full_page=True)
            paths.append(str(wide))
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            narrow = output / "publication-390.png"
            page.screenshot(path=str(narrow), full_page=True)
            paths.append(str(narrow))
            browser.close()
    except Exception as exc:  # pragma: no cover - 环境缺少浏览器时仍保留 HTML 证据
        (output / "screenshot-error.txt").write_text(str(exc), encoding="utf-8")
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=2)
    return paths


def validate(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="publication-task6-") as temp:
        temp_root = Path(temp)
        book_a_root, book_b_root = temp_root / "book-a", temp_root / "book-b"
        book_a_root.mkdir(); book_b_root.mkdir()
        a_summary, a_events = run_chain("book-a", book_a_root, drop_response=True)
        b_summary, b_events = run_chain("book-b", book_b_root)

        # 检查门槛阻断与版本冲突。
        blocked_adapter = TomatoBrowserAdapter(FakeTomatoPage(work_id="book-a", title="临时作品-book-a"))
        blocked = PublicationOrchestrator(blocked_adapter)
        blocked_task = blocked.submit(snapshot("book-a", 3, "bad", "未通过检查"), target("book-a", 3), checks={})
        conflict = blocked.submit(snapshot("book-a", 3, "new", "版本变化"), target("book-a", 3), checks=CHECKS)

        # 安全/立即暂停、浏览器崩溃后重连：恢复前只核对页面和哈希。
        pause_browser = FakeBrowser()
        pause_page = pause_browser.new_page(work_id="book-a", title="临时作品-book-a", chapter_number=9)
        pause_controller = PersistentBrowserWorkbenchController(temp_root / "pause-session.json")
        pause_controller.open(pause_page)
        pause_controller.set_operation(operation_id="pause-op", content="暂停正文", step="fill_chapter")
        pause_controller.fill("暂停正文")
        pause_controller.pause("safe")
        safe_pause = pause_controller.view()
        pause_controller.pause("immediate", reason="user_immediate_pause")
        immediate_pause = pause_controller.view()
        pause_browser.crash(); interrupted = pause_controller.poll()
        reconnected_browser = FakeBrowser(session_id=pause_browser.session_id)
        restored_page = reconnected_browser.new_page(work_id="book-a", title="临时作品-book-a", chapter_number=9)
        restored_page.page_id = pause_page.page_id; restored_page.fill("暂停正文")
        reconnected = pause_controller.reconnect(reconnected_browser)
        resumed = pause_controller.resume()

        # 验证码与登录失效均停留在 paused，不会自动发布或重发。
        gate_page = FakeTomatoPage(work_id="book-a", title="临时作品-book-a")
        gate_adapter = TomatoBrowserAdapter(gate_page); gate_adapter.connect()
        gate_orch = PublicationOrchestrator(gate_adapter)
        captcha_task = gate_orch.submit(snapshot("book-a", 20, "r20", "验证码正文"), target("book-a", 20), checks=CHECKS)
        gate_page.captcha_required = True
        captcha_result = gate_orch.run(captcha_task.operation_id)
        login_task = gate_orch.submit(snapshot("book-a", 21, "r21", "登录正文"), target("book-a", 21), checks=CHECKS)
        gate_page.captcha_required = False; gate_page.logged_in = False
        login_result = gate_orch.run(login_task.operation_id)

        # GET 只读探针：不改变操作状态。
        probe_page = FakeTomatoPage(work_id="book-a", title="临时作品-book-a")
        probe_adapter = TomatoBrowserAdapter(probe_page); probe_adapter.connect()
        probe_orch = PublicationOrchestrator(probe_adapter)
        probe_task = probe_orch.submit(snapshot("book-a", 11, "r11", "探针正文"), target("book-a", 11), checks=CHECKS)
        server = create_publication_server(probe_orch, port=0); server_thread = __import__("threading").Thread(target=server.serve_forever, daemon=True); server_thread.start()
        try:
            before = probe_orch.state(probe_task.operation_id)
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/publication?operation_id={probe_task.operation_id}") as response:
                get_body = json.loads(response.read().decode("utf-8"))
            after = probe_orch.state(probe_task.operation_id)
        finally:
            server.shutdown(); server.server_close(); server_thread.join(timeout=2)

        screenshots = write_screenshots(output, pause_controller)
        payload = {
            "status": "isolated_validation_complete",
            "constraints": {"real_tomato_url": False, "real_account": False, "real_model": False, "runtime_8877": False, "git": False},
            "random_ports": [a_summary["session"].get("endpoint"), b_summary["session"].get("endpoint")],
            "books": {"book-a": a_events, "book-b": b_events},
            "cross_book_isolation": all(event["book_id"] == "book-a" for event in a_events) and all(event["book_id"] == "book-b" for event in b_events),
            "check_blocked": {"status": blocked_task.status.value, "reason": blocked_task.pause_reason},
            "version_conflict": {"status": conflict.status.value, "reason": conflict.pause_reason},
            "pause_reconnect": {"interrupted": interrupted, "reconnected": reconnected, "resumed": resumed},
            "pause_modes": {"safe": safe_pause, "immediate": immediate_pause},
            "captcha_login": {"captcha": captcha_result, "login_expired": login_result},
            "get_read_only": {"same_operation": before["operation_id"] == after["operation_id"], "same_status": before["status"] == after["status"], "response": get_body},
            "post_responses": [
                {"method": "POST", "action": "submit/run", "book_id": event["book_id"], "response": event["response"]}
                for event in a_events + b_events if event.get("response")
            ] + [
                {"method": "POST", "action": "reconcile", "book_id": event["book_id"], "response": event["response"]}
                for event in a_events if event.get("reconciled")
            ],
            "screenshots": screenshots,
            "hashes": sorted({event["content_sha256"] for event in a_events + b_events if event.get("content_sha256")}),
            "evidence": [event["evidence"] for event in a_events + b_events if event.get("evidence", {}).get("evidence_available")],
        }
    (output / "publication-validation.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/publication-v1-validation"))
    args = parser.parse_args()
    result = validate(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
