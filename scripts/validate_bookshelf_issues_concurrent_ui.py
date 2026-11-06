"""任务5并发反例：隔离书的相同双POST、真实迁移和390页面操作身份保留。"""

from http.client import HTTPConnection
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creative_os.project_registry import ProjectRegistry
from creative_os.web_workspace import create_server, WriterWebAdapter
from scripts.fake_validation_guard import fake_validation_guard
from scripts.validate_bookshelf_issues_ui import EmptyWorkspace


def main():
    from playwright.sync_api import sync_playwright
    output = ROOT / ".backup/bookshelf-issues-task5"
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="cos-concurrent-ui-") as temporary:
        projects = Path(temporary) / "projects"
        source = projects / "technical_book"
        source.mkdir(parents=True)
        (source / "project.json").write_text(json.dumps({"id": "stable-book", "name": "并发隔离书"}, ensure_ascii=False), encoding="utf-8")
        (source / "chapter.md").write_text("仅临时书正文", encoding="utf-8")
        original = {path.name: path.read_bytes() for path in source.iterdir()}
        model_attempts = []
        def no_model():
            model_attempts.append(True)
            raise AssertionError("禁止模型调用")
        registry = ProjectRegistry(projects, client_factory=no_model)
        server = create_server(EmptyWorkspace(None, "stable-book"), writer_adapter=WriterWebAdapter(source, "stable-book"), project_registry=registry, port=0)
        service = server.RequestHandlerClass.migration_service
        validate = service.previews.validate
        entered, release = Event(), Event()
        paused = False
        def pause_first_validation(*args):
            nonlocal paused
            if not paused:
                paused = True
                entered.set()
                assert release.wait(15)
            return validate(*args)
        service.previews.validate = pause_first_validation
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        errors, responses, posts = [], [], []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, args=["--disable-background-networking", "--disable-sync"])
                context = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname == "127.0.0.1" else route.abort())
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
                page.on("response", lambda response: responses.append(response) if response.url.endswith("/api/commands/migrate-project-directory") else None)
                page.goto("http://127.0.0.1:" + str(server.server_address[1]))
                page.locator("#view-issues").click()
                page.get_by_role("button", name="预览目录整理").click()
                page.locator("#migration-preview").wait_for(state="visible")
                operation = page.evaluate("window.bookshelfIssues.confirmation.data.operation_id")
                page.locator("#migration-confirm-check").check()
                with page.expect_request("**/api/commands/migrate-project-directory") as first_request:
                    page.locator("#confirm-migration").click()
                body = first_request.value.post_data
                assert entered.wait(5)
                connection = HTTPConnection(*server.server_address, timeout=10)
                connection.request("POST", "/api/commands/migrate-project-directory", body=body.encode("utf-8"), headers={"Content-Type": "application/json"})
                second = connection.getresponse()
                second_body = json.loads(second.read())
                connection.close()
                assert second.status == 202
                assert service.status(operation)["stage"] == "verified"
                release.set()
                page.wait_for_function("!window.bookshelfIssues.busy")
                assert page.evaluate("window.bookshelfIssues.operation && window.bookshelfIssues.operation.operation_id") == operation
                assert page.evaluate("sessionStorage.getItem('creative-os-directory-operation')") == operation
                assert "尚未开始" not in page.locator("#migration-note").inner_text()
                assert page.locator("#migration-status").get_attribute("data-stage") == "verified"
                assert len(responses) == 1 and responses[0].status == 202
                assert responses[0].json() == second_body
                requests_after_reload = []
                page.on("request", lambda request: requests_after_reload.append((request.method, request.url)))
                page.reload()
                page.wait_for_function("window.bookshelfIssues && window.bookshelfIssues.serverState?.stage === 'verified'")
                assert not [url for method, url in requests_after_reload if method == "POST"]
                assert any(url.endswith("/migrations/" + operation) for method, url in requests_after_reload)
                page.locator("#view-issues").click()
                page.screenshot(path=str(output / "review-concurrent-390.png"))
                assert len(posts) == 1
                assert not errors and not model_attempts
                target = projects / "并发隔离书"
                backup = service.backup_root / operation / "project"
                assert not source.exists()
                assert {path.name: path.read_bytes() for path in target.iterdir()} == original
                assert {path.name: path.read_bytes() for path in backup.iterdir()} == original
                assert len(list(service.backup_root.glob("*/project"))) == 1
                report = {"width": 390, "identical_posts": 2, "responses": [202, 202], "stage": "verified",
                          "operation_preserved": True, "reload_get_only": True, "backups": 1,
                          "original_target_backup_bytes_equal": True, "page_errors": errors, "model_attempts": model_attempts}
                (output / "concurrent-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report, ensure_ascii=False))
                context.close(); browser.close()
        finally:
            release.set()
            server.shutdown(); server.server_close(); worker.join(); registry.close()


if __name__ == "__main__":
    with fake_validation_guard():
        main()
