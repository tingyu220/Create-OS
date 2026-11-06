"""任务6浏览器矩阵：真实后端阶段、断连、显式核对及稳定入口。"""

import json
from pathlib import Path
from urllib.parse import urlsplit

from creative_os.project_directory_inventory import build_inventory
from scripts.bookshelf_issues_fixture import PhaseGate, isolated_bookshelf
from scripts.validate_bookshelf_issues_ui import snapshot

ALLOWED_POSTS = {"/api/commands/migrate-project-directory", "/api/commands/reconcile-project-directory",
                 "/api/commands/continue-project-directory", "/api/projects/recent"}


def new_page(browser, case, width):
    context = browser.new_context(viewport={"width": width, "height": 1000 if width == 1440 else 844}, service_workers="block")
    context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname == "127.0.0.1" else route.abort())
    page = context.new_page()
    evidence = {"posts": [], "errors": [], "failed_requests": []}
    page.on("request", lambda request: evidence["posts"].append({"path": urlsplit(request.url).path, "body": request.post_data_json}) if request.method == "POST" else None)
    page.on("pageerror", lambda error: evidence["errors"].append(str(error)))
    page.on("requestfailed", lambda request: evidence["failed_requests"].append(urlsplit(request.url).path))
    page.goto(case.base)
    page.wait_for_function("document.querySelector('#catalog-status').textContent === ''")
    print(f"已载入隔离书架 {width}", flush=True)
    return context, page, evidence


def open_issues(page):
    page.locator("#view-issues").focus()
    page.keyboard.press("Enter")
    page.wait_for_function("!window.bookshelfIssues.listBusy")
    assert page.locator("#issues-panel").is_visible()


def preview(page):
    page.get_by_role("button", name="预览目录整理", exact=True).click()
    page.locator("#migration-preview").wait_for(state="visible")
    assert page.locator("#confirm-migration").is_disabled()
    assert "已了解影响并确认先备份再迁移" in page.locator(".migration-consent").inner_text()
    return page.evaluate("window.bookshelfIssues.confirmation.data.operation_id")


def confirm(page):
    page.locator("#migration-confirm-check").check()
    page.locator("#confirm-migration").dblclick(force=True)


def wait_state(page, stage):
    page.wait_for_function("stage => !window.bookshelfIssues.busy && window.bookshelfIssues.serverState?.stage === stage", arg=stage)


def assert_network(evidence):
    assert not evidence["errors"], evidence["errors"]
    assert all(item["path"] in ALLOWED_POSTS for item in evidence["posts"]), evidence["posts"]


def open_stable_result(page, case, operation):
    with page.expect_response(lambda response: urlsplit(response.url).path == "/api/projects/recent" and response.request.method == "POST") as recorded:
        page.locator("#migration-open").click()
    assert recorded.value.status == 200
    page.wait_for_function("document.querySelector('#editor')?.value.includes('海风与钟声临时工作稿')")
    assert urlsplit(page.url).path == "/p/stable-book/writer"
    assert page.locator("#project-switch").input_value() == "stable-book"
    page.wait_for_function("async () => (await (await fetch('/api/projects/recent')).json()).items[0]?.project_id === 'stable-book'")
    assert case.service.status(operation)["stage"] == "verified"


def success_case(browser, output, width):
    stages = {"after_intent": "reserved", "after_backing_up": "backing_up", "after_backup_verified": "backup_verified",
              "after_moving": "moving", "after_verified": "verified"}
    with isolated_bookshelf(output, f"success-{width}", mixed=True) as case:
        print(f"开始混合成功矩阵 {width}", flush=True)
        gate = PhaseGate(stages)
        case.service.checkpoint = gate
        context, page, evidence = new_page(browser, case, width)
        try:
            assert page.locator("#book-list .book-row").count() == 4
            healthy = page.locator("#book-list .book-row").filter(has_text="正常书")
            with page.expect_response(lambda response: urlsplit(response.url).path == "/api/projects/recent" and response.request.method == "POST") as recorded:
                healthy.locator(".book-open").click()
            assert recorded.value.status == 200
            page.wait_for_function("document.querySelector('#editor')?.value.includes('正常书临时正式稿')")
            assert page.locator("#project-switch").input_value() == "healthy-book"
            page.wait_for_function("async () => (await (await fetch('/api/projects/recent')).json()).items[0]?.project_id === 'healthy-book'")
            page.goto(case.base)
            page.wait_for_function("document.querySelector('#catalog-status').textContent === ''")
            before = snapshot(case.workspace)
            open_issues(page)
            issues = page.locator("#issues-list .issue-entry")
            assert issues.count() >= 6
            assert "7 / 7" in page.locator("#issues-summary").inner_text()
            assert page.get_by_role("button", name="预览目录整理", exact=True).count() == 1
            text = page.locator("#issues-list").inner_text()
            assert "ID 重复" in text and "元数据" in text and "未知" in text and "摘要异常" in text
            summary = issues.filter(has_text="摘要异常")
            assert "正式稿 1" in summary.first.inner_text()
            assert "待确认候选 未知" in summary.first.inner_text()
            page.screenshot(path=str(output / f"mixed-{width}.png"))
            first = preview(page)
            assert snapshot(case.workspace) == before
            before_posts = len(evidence["posts"])
            page.locator("#cancel-migration-preview").click()
            assert page.get_by_role("button", name="预览目录整理", exact=True).evaluate("e => e === document.activeElement")
            page.keyboard.press("Escape")
            assert page.locator("#view-issues").evaluate("e => e === document.activeElement")
            assert len(evidence["posts"]) == before_posts
            assert snapshot(case.workspace) == before
            open_issues(page)
            operation = preview(page)
            assert operation != first
            page.screenshot(path=str(output / f"confirm-{width}.png"))
            confirm(page)
            observed = []
            for point, stage in stages.items():
                gate.wait(point, page)
                page.locator("#refresh-migration-status").click()
                page.wait_for_function("stage => document.querySelector('#migration-status').dataset.stage === stage", arg=stage)
                assert case.service.status(operation)["stage"] == stage
                assert page.locator("#reconcile-migration").is_disabled()
                assert len([item for item in evidence["posts"] if item["path"].endswith("/migrate-project-directory")]) == 1
                if stage != "verified":
                    assert case.request("GET", "/api/author-home")[0] == 503
                    assert case.request("GET", "/p/stable-book/api/author-home")[0] == 503
                    assert case.request("POST", "/api/commands/save-writer-draft", {})[0] == 409
                    assert case.request("GET", "/p/healthy-book/api/author-home")[0] == 200
                page.screenshot(path=str(output / f"stage-{stage}-{width}.png"))
                observed.append(stage)
                print(f"真实阶段 {width}: {stage}", flush=True)
                gate.release(point)
            wait_state(page, "verified")
            assert "读取失败" not in page.locator("#migration-note").inner_text()
            backup = case.verify_success(operation)
            page.screenshot(path=str(output / f"success-{width}.png"))
            open_stable_result(page, case, operation)
            page.screenshot(path=str(output / f"opened-{width}.png"))
            assert_network(evidence)
            # keepalive最近记录已确认落盘；离页时浏览器可取消其未消费的响应体。
            assert all(path == "/api/projects/recent" for path in evidence["failed_requests"]), evidence["failed_requests"]
            return {"case": "mixed-success", "width": width, "workspace": str(case.workspace), "operation_id": operation,
                    "observed_backend_stages": observed, "final_backend_stage": "verified", "backup": backup, "mixed_projects": 7, "counts_and_unknowns": True,
                    "preview_cancel_readonly": True, "keyboard_focus": True, "double_click_one_post": True,
                    "default_scoped_gates": True, "old_runtime_writes_rejected": True, "stable_entry_and_recent": True,
                    "id_bytes_inventory_equal": True, **evidence}
        except Exception as exc:
            page.screenshot(path=str(output / f"failure-success-{width}.png"))
            print(json.dumps({"failure": repr(exc), "url": page.url, "posts": [item["path"] for item in evidence["posts"]],
                              "note": page.evaluate("document.querySelector('#migration-note')?.textContent"),
                              "state": page.evaluate("window.bookshelfIssues?.serverState")}, ensure_ascii=False))
            raise
        finally:
            gate.release(); context.close()


def interrupted_case(browser, output, width, point):
    labels = {"after_command_reserve": ("before-backup", "reserved"), "after_backup_verified": ("after-backup", "backup_verified"),
              "after_rename": ("after-rename", "moving")}
    label, interrupted_stage = labels[point]
    with isolated_bookshelf(output, f"{label}-{width}") as case:
        print(f"开始中断矩阵 {label} {width}", flush=True)
        fired = False
        def crash(window, _record):
            nonlocal fired
            if window == point and not fired:
                fired = True
                raise SystemExit("隔离测试请求执行线程中断")
        case.service.checkpoint = crash
        context, page, evidence = new_page(browser, case, width)
        try:
            open_issues(page); operation = preview(page); confirm(page)
            page.wait_for_function("() => !window.bookshelfIssues.busy && window.bookshelfIssues.serverState?.needs_reconciliation")
            assert fired
            assert case.service.status(operation)["stage"] == interrupted_stage
            assert page.locator("#migration-status").get_attribute("data-stage") == interrupted_stage
            assert page.locator("#migration-open").is_hidden()
            assert page.locator("#reconcile-migration").is_enabled()
            page.screenshot(path=str(output / f"interrupted-{label}-{width}.png"))
            before = snapshot(case.workspace)
            posts_before = len(evidence["posts"])
            page.reload()
            page.wait_for_function("window.bookshelfIssues?.serverState?.needs_reconciliation")
            assert len(evidence["posts"]) == posts_before
            assert snapshot(case.workspace) == before
            assert page.evaluate("window.bookshelfIssues.operation.operation_id") == operation
            open_issues(page)
            target = case.projects / "海风与钟声"
            inode = target.stat().st_ino if target.exists() else None
            page.locator("#reconcile-migration").click()
            final_stage = "failed" if label == "before-backup" else "backup_verified" if label == "after-backup" else "verified"
            wait_state(page, final_stage)
            assert "读取失败" not in page.locator("#migration-note").inner_text()
            assert len(evidence["posts"]) == posts_before + 1
            if label == "after-backup":
                assert case.source.exists() and not target.exists()
                before = snapshot(case.workspace)
                page.locator("#continue-migration").click()
                assert page.locator("#confirm-migration").is_disabled()
                page.locator("#cancel-migration-preview").click()
                assert len(evidence["posts"]) == posts_before + 1
                assert snapshot(case.workspace) == before
                page.locator("#continue-migration").click()
                confirm(page); wait_state(page, "verified")
                assert len(evidence["posts"]) == posts_before + 2
            page.screenshot(path=str(output / f"reconciled-{label}-{width}.png"))
            if label == "before-backup":
                assert build_inventory(case.source) == case.original and not target.exists()
                assert not case.service.backup_root.exists()
                assert page.locator("#migration-open").is_hidden()
                assert page.locator("#migration-reload").inner_text() == ""
                assert case.request("GET", "/api/author-home")[0] == 200
                backup = None
            else:
                backup = case.verify_success(operation)
                if inode is not None:
                    assert target.stat().st_ino == inode
                open_stable_result(page, case, operation)
            assert_network(evidence)
            assert evidence["failed_requests"] == ["/api/commands/migrate-project-directory"], evidence["failed_requests"]
            return {"case": label, "width": width, "workspace": str(case.workspace), "operation_id": operation,
                    "interrupted_backend_stage": interrupted_stage, "final_backend_stage": case.service.status(operation)["stage"],
                    "backup": backup, "reload_get_only": True, "explicit_reconciliation": True,
                    "separate_continue_confirmation": label == "after-backup", "id_bytes_inventory_equal": True, **evidence}
        finally:
            context.close()


def main():
    from playwright.sync_api import sync_playwright
    output = Path(__file__).resolve().parents[1] / ".backup/bookshelf-issues-task6"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--disable-background-networking", "--disable-sync"])
        try:
            for width in (1440, 390):
                results.append(success_case(browser, output, width))
                for point in ("after_command_reserve", "after_backup_verified", "after_rename"):
                    results.append(interrupted_case(browser, output, width, point))
        finally:
            browser.close()
    report = {"status": "passed", "cases": results, "production_touched": False, "model_attempts": [],
              "temporary_fixtures_retained": True,
              "screenshots": [str(path.resolve()) for path in sorted(output.glob("*.png")) if not path.name.startswith("failure-")]}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "passed", "cases": len(results), "report": str(output / "report.json"), "model_attempts": []}, ensure_ascii=False))
