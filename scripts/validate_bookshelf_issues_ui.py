"""任务5界面冒烟及拒绝/未知反例：仅临时书架，不执行迁移或模型请求。"""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creative_os.project_registry import ProjectRegistry
from creative_os.web_workspace import create_server, WriterWebAdapter, WorkspaceWebAdapter
from scripts.fake_validation_guard import fake_validation_guard


class EmptyWorkspace(WorkspaceWebAdapter):
    def read_json(self):
        return b"{}"


def snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


def assert_rejection_preserves_files(before, after):
    """原外置锁可产生空锁文件，不能产生项目或迁移数据变化。"""
    prefix = "projects/.creative_os/project-write-locks/"
    def data_files(files):
        return {name: value for name, value in files.items() if not name.replace("\\", "/").startswith(prefix)}
    assert data_files(after) == data_files(before)
    assert all(value[0] == b"" for name, value in after.items() if name.replace("\\", "/").startswith(prefix))


def main():
    from playwright.sync_api import sync_playwright
    output = ROOT / ".backup/bookshelf-issues-task5"
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="cos-issues-ui-") as temporary:
        workspace = Path(temporary)
        projects = workspace / "projects"
        source = projects / "technical_book"
        source.mkdir(parents=True)
        (source / "project.json").write_text(json.dumps({"id": "stable-book", "name": "海风里的书店"}, ensure_ascii=False), encoding="utf-8")
        chapters = source / "production/final_chapters"
        chapters.mkdir(parents=True)
        (chapters / "chapter_001.md").write_text("# 第一章\n隔离测试正文", encoding="utf-8")
        model_attempts = []

        def no_model():
            model_attempts.append(True)
            raise AssertionError("界面检查禁止模型调用")

        registry = ProjectRegistry(projects, client_factory=no_model)
        server = create_server(EmptyWorkspace(None, "stable-book"), writer_adapter=WriterWebAdapter(source, "stable-book"), project_registry=registry, port=0)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = "http://127.0.0.1:" + str(server.server_address[1])
        errors, posts, checks = [], [], []
        before = snapshot(workspace)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, args=["--disable-background-networking", "--disable-sync"])
                for width, height in ((1440, 1000), (390, 844)):
                    context = browser.new_context(viewport={"width": width, "height": height}, service_workers="block")
                    context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname == "127.0.0.1" else route.abort())
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
                    page.goto(base)
                    page.locator("#view-issues").click()
                    page.get_by_role("button", name="预览目录整理").click()
                    page.locator("#migration-preview").wait_for(state="visible")
                    assert page.locator("#confirm-migration").is_disabled()
                    assert "海风里的书店" in page.locator("#migration-preview-details").inner_text()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    assert page.locator("#issues-panel").evaluate("e => e.scrollWidth <= e.clientWidth")
                    page.screenshot(path=str(output / f"preview-{width}.png"))
                    page.locator("#cancel-migration-preview").click()
                    assert page.locator("#migration-preview").is_hidden()
                    page.keyboard.press("Escape")
                    assert page.locator("#issues-panel").is_hidden()
                    assert page.locator("#view-issues").evaluate("e => e === document.activeElement")
                    checks.append({"width": width, "preview_cancel": True, "focus_return": True, "no_overflow": True})
                    context.close()
                browser.close()
            assert not errors, errors
            assert not posts, posts
            assert not model_attempts
            assert snapshot(workspace) == before, "预览或取消修改了临时书架"
            report = {"checks": checks, "posts": posts, "page_errors": errors, "model_attempts": model_attempts, "files_unchanged": True}
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False))
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
            registry.close()


def review_regressions():
    """通过真实页面重载验证明确拒绝可恢复、未知结果保留原操作。"""
    from playwright.sync_api import sync_playwright
    output = ROOT / ".backup/bookshelf-issues-task5"
    with TemporaryDirectory(prefix="cos-issues-review-") as temporary:
        workspace = Path(temporary)
        source = workspace / "projects/technical_book"
        source.mkdir(parents=True)
        (source / "project.json").write_text(json.dumps({"id": "stable-book", "name": "隔离反例书"}, ensure_ascii=False), encoding="utf-8")
        chapter = source / "chapter.md"
        chapter.write_text("临时正文", encoding="utf-8")
        registry = ProjectRegistry(source.parent, client_factory=lambda: (_ for _ in ()).throw(AssertionError("禁止模型调用")))
        server = create_server(EmptyWorkspace(None, "stable-book"), writer_adapter=WriterWebAdapter(source, "stable-book"), project_registry=registry, port=0)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = "http://127.0.0.1:" + str(server.server_address[1])
        errors, results = [], []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, args=["--disable-background-networking", "--disable-sync"])
                for width in (1440, 390):
                    for outcome in ("stale", "lost", "5xx"):
                        context = browser.new_context(viewport={"width": width, "height": 1000 if width == 1440 else 844}, service_workers="block")
                        context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname == "127.0.0.1" else route.abort())
                        if outcome != "stale":
                            def reject(route):
                                if outcome == "lost":
                                    route.abort("failed")
                                else:
                                    route.fulfill(status=503, content_type="application/json", body=json.dumps({"error": {"code": "migration_evidence_unavailable"}}))
                            context.route("**/api/commands/migrate-project-directory", reject)
                        page = context.new_page()
                        requests = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.on("request", lambda request: requests.append((request.method, request.url)))
                        page.goto(base)
                        page.locator("#view-issues").click()
                        page.get_by_role("button", name="预览目录整理").click()
                        page.locator("#migration-preview").wait_for(state="visible")
                        operation = page.evaluate("window.bookshelfIssues.confirmation.data.operation_id")
                        if outcome == "stale":
                            chapter.write_text("临时正文变化：" + operation, encoding="utf-8")
                        before = snapshot(workspace)
                        page.locator("#migration-confirm-check").check()
                        page.locator("#confirm-migration").click()
                        page.wait_for_function("!window.bookshelfIssues.busy")
                        if outcome == "stale":
                            assert page.evaluate("window.bookshelfIssues.operation === null")
                            assert "尚未开始" in page.locator("#migration-note").inner_text()
                            assert page.evaluate("sessionStorage.getItem('creative-os-directory-operation') === null")
                        else:
                            assert page.evaluate("window.bookshelfIssues.operation.operation_id") == operation
                        assert_rejection_preserves_files(before, snapshot(workspace))
                        requests.clear()
                        page.reload()
                        page.wait_for_function("window.bookshelfIssues && window.bookshelf && document.querySelector('#catalog-status').textContent === ''")
                        page.locator("#view-issues").click()
                        button = page.get_by_role("button", name="预览目录整理")
                        button.wait_for(state="visible")
                        status_reads = [url for method, url in requests if "/migrations/" in url]
                        if outcome == "stale":
                            assert not status_reads, status_reads
                            assert button.is_enabled()
                            button.click()
                            page.locator("#migration-preview").wait_for(state="visible")
                        else:
                            assert button.is_disabled()
                            assert status_reads and all(url.endswith("/" + operation) for url in status_reads)
                            assert page.evaluate("sessionStorage.getItem('creative-os-directory-operation')") == operation
                        assert not [url for method, url in requests if method == "POST"]
                        assert_rejection_preserves_files(before, snapshot(workspace))
                        page.screenshot(path=str(output / f"review-{outcome}-{width}.png"))
                        results.append({"width": width, "outcome": outcome, "reload_get_only": True,
                                        "retry_preview_allowed": outcome == "stale", "project_and_migration_files_unchanged": True, "lease_artifacts_allowed": True})
                        context.close()
                browser.close()
            assert not errors, errors
            report = {"cases": results, "page_errors": errors, "model_clients_constructed": 0, "real_migrations": 0}
            (output / "review-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False))
        finally:
            server.shutdown(); server.server_close(); worker.join(); registry.close()


if __name__ == "__main__":
    with fake_validation_guard():
        if "--full" in sys.argv:
            from scripts.bookshelf_issues_acceptance import main as full_acceptance
            full_acceptance()
        else:
            main()
            if "--review-regressions" in sys.argv:
                review_regressions()
