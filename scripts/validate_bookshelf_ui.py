"""临时作品书架与书内导航验收；零模型调用，仅显式 UI 最近记录和新建书命令。"""

import argparse
from dataclasses import asdict, replace
from http.client import HTTPConnection
import json
from pathlib import Path
import sys
import tempfile
from threading import Thread
from urllib.parse import quote, urlencode, urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creative_os.agent_conversation_store import AgentConversationStore
from creative_os.agent_proposal_store import AgentProposalStore
from creative_os.agent_runtime import AgentJob, WriterAgentRuntime
from creative_os.novel_project_command import NovelProjectCreator
from creative_os.project_registry import ProjectRegistry
from creative_os.story_architecture_store import StoryArchitectureStore
from creative_os.web_workspace import WorkspaceWebAdapter, WriterWebAdapter, create_server
from creative_os.workspace_recent_store import WorkspaceRecentStore
from creative_os.writer_draft_store import WriterDraftStore
from creative_os.workspace_command import FileCommandResultStore
from scripts.fake_validation_guard import fake_validation_guard


class EmptyWorkspace(WorkspaceWebAdapter):
    def read_json(self):
        return json.dumps({"project_id": self._project_id, "snapshot": {}, "operations": {}}).encode()


def snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns) for path in root.rglob("*") if path.is_file()}


def seed(root):
    creator = NovelProjectCreator(root)
    first = creator.create("隔离甲书", "想法甲", operation_id="a", story_mode=False)
    metadata = json.loads((first / "project.json").read_text(encoding="utf-8")); metadata["title"] = "甲书 · " + "很长的创作名称与真实稿件边界" * 4
    (first / "project.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    formal = first / "production/final_chapters/chapter_001.md"; formal.write_text("# 第1章 海风正式稿\n甲书正式哨兵", encoding="utf-8")
    WriterDraftStore(first).save(1, "# 第1章 海风工作稿\n甲书工作哨兵", actor="验收")
    conversations = AgentConversationStore(first, first.name); session = conversations.read(1)
    job = AgentJob("agent-" + uuid4().hex, "completed", "隔离已存候选", 1, project_id=first.name, session_id=session["session_id"], instruction="甲书对话哨兵", mode="act")
    proposals = AgentProposalStore(first, first.name); proposal = proposals.create(job, "message-" + uuid4().hex)
    proposals.complete(proposal["proposal_id"], "# 第1章 甲书候选哨兵")
    job = replace(job, proposal_id=proposal["proposal_id"]); session["jobs"][job.job_id] = asdict(job)
    for status in ("accepted", "rejected", "cancelled"):
        historical_job = AgentJob("agent-" + uuid4().hex, "completed", "历史候选", 1, project_id=first.name, session_id=session["session_id"], instruction="历史操作", mode="act")
        historical = proposals.create(historical_job, "message-" + uuid4().hex)
        historical = proposals.complete(historical["proposal_id"], "历史" + status + "候选不得抢占")
        historical["status"] = status; proposals.write(historical)
        historical_job = replace(historical_job, proposal_id=historical["proposal_id"])
        session["jobs"][historical_job.job_id] = asdict(historical_job)
    session["messages"] = [{"role": "user", "content": "甲书对话哨兵", "task_id": job.job_id, "message_id": "message-a"}]; conversations.write(session)
    second = creator.create("构思乙书", "乙书原始Idea", operation_id="b")
    story = StoryArchitectureStore(second, second.name)
    story.propose(story.session_id, [{"key": "core", "title": "故事核心", "text": "乙书设定哨兵"}], ["乙书未定问题"], expected_revision=0, actor="验收", operation_id="candidate")
    store = AgentConversationStore(second, second.name); conversation = store.read(None)
    conversation["messages"] = [{"role": "user", "content": "乙书对话哨兵", "task_id": "seed", "message_id": "message-b"}]; store.write(conversation)
    third = creator.create("无最近丙书", "想法丙", operation_id="c", story_mode=False)
    return first, second, third


def main():
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", type=Path, default=ROOT / ".backup/bookshelf-ui")
    args = parser.parse_args(); args.output_dir.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="cos-bookshelf-")); first, second, third = seed(root)
    model_attempts = []
    def no_model():
        model_attempts.append("forbidden"); raise AssertionError("书架验收不得构造模型客户端")
    registry = ProjectRegistry(root, client_factory=no_model)
    default_runtime = WriterAgentRuntime(first, client_factory=no_model, read_only=True, recover=False)
    server = create_server(EmptyWorkspace(None, first.name), writer_adapter=WriterWebAdapter(first, first.name), agent_runtime=default_runtime, project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True); worker.start()
    base = "http://127.0.0.1:" + str(server.server_address[1])
    errors, posts, checks, responses = [], [], [], []
    def get(path):
        connection = HTTPConnection(*server.server_address, timeout=5); connection.request("GET", path)
        response = connection.getresponse(); response.read(); connection.close(); return response.status
    before = snapshot(root)
    routes = ["/", "/api/projects", "/api/projects/recent", "/p/" + quote(first.name) + "/", "/writer?chapter=1&source=draft", "/overview", "/inspector",
              "/p/" + quote(first.name) + "/api/writer/context", "/p/" + quote(first.name) + "/api/writer/chapters/1?source=draft",
              "/p/" + quote(first.name) + "/api/agent/conversations/1?project_id=" + quote(first.name),
              "/p/" + quote(second.name) + "/api/story?" + urlencode({"project_id": second.name, "scope": "story", "session_id": StoryArchitectureStore(second, second.name).session_id})]
    try:
        assert all(get(route) in {200, 302} for route in routes)
        assert snapshot(root) == before; checks.append("all_gets_readonly")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-background-networking", "--disable-sync"])
            for width, height in ((1440, 1000), (390, 844)):
                context = browser.new_context(viewport={"width": width, "height": height}, timezone_id="Asia/Shanghai", service_workers="block")
                context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname in {"127.0.0.1", "localhost", "::1"} else route.abort())
                page = context.new_page(); page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: posts.append({"path": urlsplit(request.url).path, "method": request.method}) if request.method == "POST" else None)
                page.on("response", lambda response: responses.append({"path": urlsplit(response.url).path, "status": response.status}) if "/api/" in response.url else None)
                def mobile_writer_nav():
                    if width < 920: page.locator('[data-workspace-panel="navigation"]').click()
                def mobile_story_nav():
                    if width < 920: page.locator('.story-mobile-switcher [data-story-pane="navigation"]').click()
                def recent(project_id, page_kind):
                    page.wait_for_function("async value => { const data = await (await fetch('/api/projects/recent')).json(); return data.positions?.[value.id]?.page === value.page; }", arg={"id": project_id, "page": page_kind})
                page.goto(base + "/"); page.wait_for_function("document.querySelector('#book-list').children.length >= 3")
                if width == 1440: assert page.locator("#recent-empty").is_visible()
                page.screenshot(path=str(args.output_dir / ("shelf-" + str(width) + ".png")), full_page=True)
                page.locator("#book-search").fill("甲书")
                page.wait_for_function("document.querySelector('#book-list').children.length === 1")
                page.locator("#book-list .book-open").click()
                try:
                    page.wait_for_function("document.querySelector('#editor').value.includes('甲书工作哨兵')")
                except Exception:
                    print(json.dumps({"url": page.url, "errors": errors, "responses": responses, "body": page.locator("body").inner_text()}, ensure_ascii=False))
                    raise
                recent(first.name, "writer")
                assert "source=draft" in page.url
                page.locator("#view-formal").click(); page.wait_for_function("document.querySelector('#editor').value.includes('甲书正式哨兵')")
                page.locator("#view-draft").click(); page.wait_for_function("document.querySelector('#editor').value.includes('甲书工作哨兵')")
                mobile_writer_nav(); page.locator('[data-directory-filter="candidate"]').click(); page.locator("#chapter-directory button").click()
                if width < 920: page.locator('[data-workspace-panel="chapter"]').click()
                page.wait_for_function("document.querySelector('#agent-candidate').textContent.includes('甲书候选哨兵')")
                assert page.locator("#agent-review-actions").evaluate("node => !node.hidden")
                page.screenshot(path=str(args.output_dir / ("writer-" + str(width) + ".png")), full_page=True)
                draft_before = WriterDraftStore(first).current(1)
                page.locator('[data-chapter-tab="editor"]').click()
                page.locator("#editor").fill("未保存甲书本地哨兵")
                mobile_writer_nav(); page.once("dialog", lambda dialog: dialog.dismiss()); page.locator("#workspace-back").click()
                assert page.locator("#editor").input_value() == "未保存甲书本地哨兵"
                page.once("dialog", lambda dialog: dialog.accept())
                mobile_writer_nav(); page.locator("#project-switch").select_option(second.name)
                page.wait_for_function("document.querySelector('#story-title').textContent === '构思乙书'")
                recent(second.name, "story")
                assert WriterDraftStore(first).current(1) == draft_before
                assert "乙书对话哨兵" in page.locator("#story-thread").inner_text()
                if width < 920: page.locator('.story-mobile-switcher [data-story-pane="candidate"]').click()
                assert "乙书设定哨兵" in page.locator("#candidate-blocks textarea").first.input_value()
                page.screenshot(path=str(args.output_dir / ("story-" + str(width) + ".png")), full_page=True)
                page.locator("#candidate-blocks textarea").first.fill("未保存乙书本地哨兵")
                mobile_story_nav(); page.once("dialog", lambda dialog: dialog.dismiss()); page.locator("#workspace-back").click()
                assert urlsplit(page.url).path.endswith("/story")
                assert page.locator("#candidate-blocks textarea").first.input_value() == "未保存乙书本地哨兵"
                page.once("dialog", lambda dialog: dialog.accept()); page.locator("#project-switch").select_option(first.name)
                page.wait_for_function("document.querySelector('#editor').value.includes('甲书工作哨兵')")
                recent(first.name, "writer")
                assert "乙书" not in page.locator("#agent-thread").inner_text()
                assert StoryArchitectureStore(second, second.name).view()["candidate"]["content"]["blocks"][0]["text"] == "乙书设定哨兵"
                mobile_writer_nav(); page.locator("#workspace-back").click(); page.wait_for_url(base + "/")
                page.reload(); page.locator("#recent-books .recent-card").first.wait_for()
                assert first.name in WorkspaceRecentStore(root).read()[0]["project_id"]
                page.locator("#new-book").click(); page.locator("#book-title").fill("浏览器新书" + str(width)); page.locator("#book-idea").fill("新书真实输入，尚未调用模型")
                page.locator("#create-submit").click(); page.wait_for_function("document.querySelector('#create-book').hidden")
                recent("浏览器新书" + str(width), "story")
                mobile_story_nav(); page.locator("#workspace-back").click(); page.wait_for_url(base + "/")
                page.locator("#book-search").fill("浏览器新书" + str(width)); page.wait_for_function("document.querySelector('#book-list').children.length === 1")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                checks.append("loop-" + str(width)); context.close()
            bad = NovelProjectCreator(root).create("损坏摘要", "隔离异常条目", operation_id="bad-summary", story_mode=False)
            bad_session = bad / ".creative_os/agent/conversations/chapter_001.json"
            bad_session.parent.mkdir(parents=True, exist_ok=True)
            bad_session.write_text(json.dumps({"project_id": bad.name, "chapter_number": 1, "jobs": []}), encoding="utf-8")
            bad_command = NovelProjectCreator(root).create("损坏回执", "隔离异常回执", operation_id="bad-command", story_mode=False)
            bad_proposals = bad_command / ".creative_os/agent/proposals"; bad_proposals.mkdir(parents=True, exist_ok=True)
            (bad_proposals / ("proposal-" + "0" * 32 + ".json")).write_text(json.dumps({
                "project_id": bad_command.name, "chapter_number": 1, "status": "pending", "result": {"content": "隔离候选"}}), encoding="utf-8")
            bad_receipts = bad_command / ".creative_os/commands/results.json"
            bad_receipts.parent.mkdir(parents=True, exist_ok=True); bad_receipts.write_text("{broken", encoding="utf-8")
            proposal_store = AgentProposalStore(first, first.name)
            pending_path = next(path for path in proposal_store.root.glob("proposal-*.json") if json.loads(path.read_text(encoding="utf-8"))["status"] == "pending")
            recovering = proposal_store.read(pending_path.stem)
            recovering.update(status="accepted", review={"identity": {"action": "accept", "reason": "原审阅决定"}, "actor": "验收作者",
                              "feedback": {"id": "feedback-recovery"}, "job_id": recovering["task_id"], "commands": [{"key": "recovery-receipt"}]})
            proposal_store.write(recovering); FileCommandResultStore(first).reserve("recovery-receipt", "fixture-fingerprint")
            for width, height in ((1440, 1000), (390, 844)):
                context = browser.new_context(viewport={"width": width, "height": height}, service_workers="block")
                context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname in {"127.0.0.1", "localhost", "::1"} else route.abort())
                page = context.new_page(); page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: posts.append({"path": urlsplit(request.url).path, "method": request.method}) if request.method == "POST" else None)
                malformed_before = snapshot(root)
                page.goto(base + "/"); page.locator("#catalog-warning").wait_for()
                assert page.locator("#book-list").inner_text().find("损坏摘要") >= 0
                assert page.locator("#book-list").inner_text().find("构思乙书") >= 0
                assert "暂不可用" in page.locator("#book-list .book-row").filter(has_text=bad_command.name).locator(".book-counts").inner_text()
                assert snapshot(root) == malformed_before
                page.screenshot(path=str(args.output_dir / ("partial-summary-" + str(width) + ".png")), full_page=True)
                page.goto(base + "/p/" + quote(first.name) + "/writer?chapter=1&source=draft")
                page.wait_for_function("document.querySelector('#editor').value.includes('甲书工作哨兵')")
                if width < 920: page.locator('[data-workspace-panel="navigation"]').click()
                page.locator('[data-directory-filter="candidate"]').click(); page.locator("#chapter-directory button").click()
                page.wait_for_function("document.querySelector('#agent-candidate').textContent.includes('甲书候选哨兵')")
                assert page.locator("#reconcile-agent-review").evaluate("node => !node.hidden")
                assert page.locator("#agent-review-actions").evaluate("node => node.hidden")
                page.screenshot(path=str(args.output_dir / ("directory-recovery-" + str(width) + ".png")), full_page=True)
                page.goto(base + "/p/" + quote(first.name) + "/#chapters")
                legacy = page.locator("#workspace-notice a")
                legacy.wait_for(state="attached")
                assert legacy.get_attribute("href") == "/p/" + quote(first.name) + "/overview#chapters"
                page.wait_for_function("!document.querySelector('#editor').disabled && document.querySelector('.writer-grid').dataset.activePanel === 'chapter'")
                if width < 920: page.locator('[data-workspace-panel="navigation"]').click()
                legacy.click(); page.wait_for_url("**/overview#chapters")
                page.wait_for_function("document.querySelector('#chapter-list').children.length > 0")
                failed_chapter = "**/p/" + quote(third.name) + "/api/writer/chapters/1?*"
                page.route(failed_chapter, lambda route: route.fulfill(status=503, content_type="application/json", body='{"error":"unavailable"}'))
                page.goto(base + "/p/" + quote(third.name) + "/writer?chapter=1")
                page.locator("#agent-state-text").filter(has_text="章节读取失败").wait_for(state="attached")
                assert all(row["project_id"] != third.name for row in WorkspaceRecentStore(root).read())
                assert page.locator("#editor").is_disabled()
                assert "章节读取失败" in page.locator("#source-status").inner_text()
                page.screenshot(path=str(args.output_dir / ("chapter-error-" + str(width) + ".png")), full_page=True)
                page.route("**/api/projects/recent", lambda route: route.fulfill(status=503, content_type="application/json", body='{"error":{"message":"最近位置暂不可写"}}') if route.request.method == "POST" else route.continue_())
                page.goto(base + "/p/" + quote(first.name) + "/writer?chapter=1&source=draft")
                page.wait_for_function("document.querySelector('#editor').value.includes('甲书工作哨兵')")
                page.locator("#workspace-notice").filter(has_text="当前创作仍可继续").wait_for(state="attached")
                assert page.locator("#editor").is_enabled()
                page.route("**/api/projects?*", lambda route: route.fulfill(status=503, content_type="application/json", body='{"error":{"message":"作品目录暂时无法读取"}}'))
                page.goto(base + "/"); page.locator("#catalog-status").filter(has_text="作品目录暂时无法读取").wait_for()
                assert page.locator("#recent-books .recent-card").count() > 0
                page.screenshot(path=str(args.output_dir / ("catalog-error-" + str(width) + ".png")), full_page=True)
                page.unroute("**/api/projects?*")
                page.route("**/api/projects?*", lambda route: route.fulfill(status=200, content_type="application/json", body='{"items":[],"total":0,"offset":0,"limit":20,"warnings":[]}'))
                page.route("**/api/projects/recent", lambda route: route.fulfill(status=200, content_type="application/json", body='{"items":[],"positions":{},"warnings":[]}'))
                page.reload(); page.locator("#books-empty").wait_for()
                assert page.locator("#new-book").is_visible()
                page.screenshot(path=str(args.output_dir / ("shelf-empty-" + str(width) + ".png")), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                checks.append("failures-and-empty-" + str(width)); context.close()
            browser.close()
        assert not errors, errors
        assert not model_attempts
        assert all(item["path"] in {"/api/projects/recent", "/api/projects/create"} for item in posts), posts
        report = {"status": "passed", "temporary_projects_root": str(root), "model_calls": 0, "checks": checks, "browser_errors": errors, "posts": posts}
        (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "passed", "model_calls": 0, "checks": checks, "output_dir": str(args.output_dir)}, ensure_ascii=False))
    finally:
        server.shutdown(); server.server_close(); worker.join(); registry.close()


if __name__ == "__main__":
    with fake_validation_guard() as blocked:
        main(); assert not blocked, blocked
