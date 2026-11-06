"""临时三书验证目录名与稳定ID解耦，不读取或写入真实小说。"""

import argparse
import json
from pathlib import Path
import sys
import tempfile
from threading import Thread
from urllib.parse import urlsplit, quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.novel_project_command import NovelProjectCreator
from creative_os.project_registry import ProjectRegistry
from creative_os.web_workspace import WorkspaceWebAdapter, WriterWebAdapter, create_server
from creative_os.workspace_recent_store import WorkspaceRecentStore
from scripts.fake_validation_guard import fake_validation_guard


class EmptyWorkspace(WorkspaceWebAdapter):
    def read_json(self):
        return json.dumps({"project_id": self._project_id, "snapshot": {}, "operations": {}}).encode()


def snapshot(root):
    return {str(path.relative_to(root)): (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
            for path in root.rglob("*")}


def main():
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", type=Path, default=ROOT / ".backup/project-directory-ui")
    args = parser.parse_args(); args.output_dir.mkdir(parents=True, exist_ok=True)
    projects = Path(tempfile.mkdtemp(prefix="project-directory-ui-"))
    pairs = [("雾城回声", "novel-validation-001"), ("末班钟表店", "novel-domain-validation"), ("文明升阶", "文明升阶")]
    roots = []
    for title, project_id in pairs:
        root = NovelProjectCreator(projects).create(title, "隔离想法", operation_id=title, story_mode=False)
        metadata = json.loads((root / "project.json").read_text(encoding="utf-8")); metadata["id"] = project_id
        (root / "project.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        (root / "production/final_chapters/chapter_001.md").write_text(title + "隔离正文", encoding="utf-8")
        roots.append(root)
    attempts, errors, posts, checks = [], [], [], []
    def forbidden():
        attempts.append("model"); raise AssertionError("禁止真实模型")
    registry = ProjectRegistry(projects, client_factory=forbidden)
    runtime = WriterAgentRuntime(roots[2], project_id=pairs[2][1], client_factory=forbidden, read_only=True, recover=False)
    server = create_server(EmptyWorkspace(None, pairs[2][1]), writer_adapter=WriterWebAdapter(roots[2], pairs[2][1]), agent_runtime=runtime, project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True); worker.start()
    base = "http://127.0.0.1:" + str(server.server_address[1])
    before = [snapshot(root) for root in roots]
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-background-networking", "--disable-sync"])
            for width, height in ((1440, 1000), (390, 844)):
                context = browser.new_context(viewport={"width": width, "height": height}, service_workers="block")
                context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname in {"127.0.0.1", "localhost", "::1"} else route.abort())
                page = context.new_page(); page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: posts.append(urlsplit(request.url).path) if request.method == "POST" else None)
                page.goto(base + "/"); page.wait_for_function("document.querySelector('#book-list').children.length === 3")
                assert page.locator("#catalog-warning").is_hidden()
                page.screenshot(path=str(args.output_dir / f"shelf-{width}.png"), full_page=True)
                for title, project_id in pairs:
                    row = page.locator("#book-list .book-row").filter(has_text=title)
                    assert row.locator(".book-open").get_attribute("href") == "/p/" + quote(project_id) + "/"
                    row.locator(".book-open").click()
                    page.wait_for_function("title => document.querySelector('#editor').value === title + '隔离正文'", arg=title)
                    page.wait_for_function("id => document.querySelector('#project-switch').value === id", arg=project_id)
                    assert urlsplit(page.url).path.startswith("/p/") and "source=formal" in page.url
                    page.wait_for_function("async id => { const value = await (await fetch('/api/projects/recent')).json(); return value.items[0]?.project_id === id; }", arg=project_id)
                    if width < 920: page.locator('[data-workspace-panel="navigation"]').click()
                    page.locator("#workspace-back").click(); page.wait_for_url(base + "/")
                    page.wait_for_function("document.querySelector('#book-list').children.length === 3")
                page.reload(); page.wait_for_function("document.querySelector('#recent-books').children.length === 3")
                assert {row["project_id"] for row in WorkspaceRecentStore(projects).read()} == {project_id for _, project_id in pairs}
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                checks.append(str(width) + ": three stable IDs, scoped content, recent reload, no overflow"); context.close()
            browser.close()
        assert [snapshot(root) for root in roots] == before
        assert not attempts and not errors
        assert all(path == "/api/projects/recent" for path in posts)
        report = {"status": "passed", "temporary_projects_root": str(projects), "checks": checks,
                  "model_calls": 0, "project_files_directories_content_mtime_unchanged": True, "browser_errors": errors,
                  "identities": [{"directory": title, "project_id": project_id} for title, project_id in pairs]}
        (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    finally:
        server.shutdown(); server.server_close(); worker.join(); registry.close()


if __name__ == "__main__":
    with fake_validation_guard() as blocked:
        main(); assert not blocked, blocked
