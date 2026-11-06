"""临时稿件与只读适配器验收作者首页，不创建运行时或调用模型。"""

import argparse
import json
from pathlib import Path
import sys
import tempfile
from threading import Thread
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from creative_os.web_workspace import WorkspaceWebAdapter, WriterWebAdapter, create_server
from creative_os.workspace_query import WorkspaceQueryAdapter
from scripts.fake_validation_guard import fake_validation_guard
from test_author_home_query import EmptyReader, ReadOnlyRegistry, seed, snapshot


class FakeWorkspace(WorkspaceWebAdapter):
    def read_json(self):
        return json.dumps({"project_id": "book", "snapshot": {
            "overview": {"chapter_count": 40, "blocked_chapter_count": 0, "blockers": []},
            "chapters": [{"chapter_number": number} for number in range(1, 41)],
            "quality": {"issues": []}}}).encode("utf-8")


def main():
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".backup" / "author-home-ui")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # 保留临时项目便于复核；不向生产目录写入任何内容。
    temporary = Path(tempfile.mkdtemp(prefix="creative-os-author-home-"))
    root = seed(temporary / "book")
    empty = temporary / "empty"
    empty.mkdir()
    registry = ReadOnlyRegistry({"book": root, "empty": empty})
    original_get = registry.get

    def get(project_id, **kwargs):
        entry = original_get(project_id, **kwargs)
        if project_id == "book": entry["workspace_adapter"] = FakeWorkspace(WorkspaceQueryAdapter(EmptyReader()), "book")
        return entry

    registry.get = get
    server = create_server(FakeWorkspace(WorkspaceQueryAdapter(EmptyReader()), "book"),
                           writer_adapter=WriterWebAdapter(root, "book"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    before = snapshot(temporary)
    errors, checks = [], []
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-background-networking", "--disable-sync"])
            context = browser.new_context(service_workers="block")

            def local_only(route):
                request = urlsplit(route.request.url)
                if request.hostname not in {"127.0.0.1", "localhost", "::1"}: route.abort()
                elif request.path == "/api/projects":
                    route.fulfill(status=200, content_type="application/json", body='{"items":[{"project_id":"book","title":"book"}]}')
                elif request.path == "/api/projects/recent":
                    route.fulfill(status=200, content_type="application/json", body='{"record":{}}')
                elif "/api/agent/conversations/" in request.path:
                    number = int(request.path.rsplit("/", 1)[1])
                    route.fulfill(status=200, content_type="application/json", body=json.dumps({
                        "project_id": "book", "chapter_number": number, "session_id": f"fake-session-{number}",
                        "messages": [], "jobs": [], "proposals": []}))
                else: route.continue_()

            context.route("**/*", local_only)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            for width, height in ((1440, 1000), (390, 844)):
                page.set_viewport_size({"width": width, "height": height})
                page.goto(url + "/p/book/overview")
                page.wait_for_function("document.querySelector('#candidate-count').textContent === '2'")
                assert page.locator("#formal-count").inner_text() == "2"
                assert page.locator("#draft-count").inner_text() == "2"
                assert page.locator("#continue-writing").get_attribute("href") == "/p/book/writer?chapter=4"
                assert page.locator(".writer-home").get_attribute("href") == "/story"
                assert page.locator("#story-link").get_attribute("href") == "/p/book/story"
                assert page.locator("#attention-items").inner_text().find("第 5 章") >= 0
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert page.locator("#workspace-main").evaluate("el => el.scrollWidth <= el.clientWidth")
                assert not any(word in page.locator("body").inner_text() for word in ("CURRENT STAGE", "Trace", "snapshot", "refresh-", "private technical detail"))
                assert page.locator("#continue-writing").bounding_box()["y"] < height
                page.screenshot(path=str(args.output_dir / f"author-home-{width}.png"), full_page=True)
                page.get_by_role("link", name="全部章节 →").click()
                assert page.locator("#chapter-list .manuscript-row").count() == 4
                page.locator("#chapter-filter").fill("2")
                assert page.locator("#chapter-list .manuscript-row").count() == 1
                page.get_by_role("link", name="总览", exact=True).click()
                page.locator("#chapter-number").fill("2")
                page.get_by_role("button", name="打开章节", exact=True).click()
                page.wait_for_url("**/p/book/writer?chapter=2*")
                page.wait_for_function("document.querySelector('#editor').value === '只有工作稿'")
                checks.append(f"{width}: counts, scope, failure, layout, filtering, chapter navigation")

            page.goto(url + "/p/empty/overview")
            page.wait_for_function("document.querySelector('#formal-count').textContent === '0'")
            assert page.locator("#continue-writing").get_attribute("href") == "/p/empty/story"
            checks.append("empty project")
            page.route("**/api/author-home", lambda route: route.fulfill(status=503, body="unavailable"))
            page.goto(url + "/p/book/overview")
            page.get_by_text("读取失败", exact=True).wait_for()
            assert page.locator("#formal-count").inner_text() == "—"
            assert page.locator("#open-chapter-form").is_visible()
            page.screenshot(path=str(args.output_dir / "author-home-read-error.png"), full_page=True)
            page.unroute("**/api/author-home")
            page.route("**/api/workspace", lambda route: route.fulfill(status=503, body="unavailable"))
            page.goto(url + "/p/book/overview")
            page.wait_for_function("document.querySelector('#formal-count').textContent === '2'")
            page.get_by_text("项目检查暂时无法读取。稿件仍可继续编辑，可打开诊断核对检查状态。", exact=True).wait_for()
            assert page.locator("#continue-writing").get_attribute("href") == "/p/book/writer?chapter=4"
            page.unroute("**/api/workspace")
            page.route("**/api/workspace", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"project_id": "book", "snapshot": {"overview": {"blocked_chapter_count": 1}}})))
            page.goto(url + "/p/book/overview")
            page.get_by_text("项目检查记录了阻塞事项，请查看诊断核对。", exact=True).wait_for()
            checks.append("summary failure, projection failure independence, visible blocker")
            page.unroute("**/api/workspace")
            for source, content in (("draft", "作者修改过的工作稿"), ("formal", "正式稿"), ("auto", "正式稿")):
                page.goto(url + f"/p/book/writer?chapter=1&source={source}")
                page.wait_for_function("expected => document.querySelector('#editor').value === expected", arg=content)
            checks.append("same chapter opens requested draft/formal; auto retains original behavior")
            assert snapshot(temporary) == before
            assert errors == [], errors
            browser.close()
        report = {"status": "passed", "temporary_projects_root": str(temporary), "checks": checks,
                  "browser_errors": errors, "query_files_and_mtime_unchanged": True, "model_calls": 0,
                  "production_runtime_instances": 0, "port": server.server_address[1]}
        (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


if __name__ == "__main__":
    with fake_validation_guard() as blocked:
        main()
        assert blocked == []
