"""临时项目与出口保护下，验证重启后的显式审阅核对及人工稿保留。"""

import argparse
import json
from pathlib import Path
import sys
import tempfile
from threading import Thread
import time
from unittest.mock import patch
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creative_os.memory.feedback import FeedbackStore
from creative_os.novel_project_command import NovelProjectCreator
from creative_os.project_registry import ProjectRegistry
from creative_os.web_workspace import WorkspaceWebAdapter, create_server
from creative_os.workspace_command import CommandRequest, FileCommandResultStore
from scripts.fake_validation_guard import fake_validation_guard


class FakeClient:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        return "第1章\n\n这是原候选正文。" * 20


class EmptyWorkspace(WorkspaceWebAdapter):
    def read_json(self):
        return b'{"project_id":"none","snapshot":{},"operations":{}}'


def finish(runtime, job):
    for _ in range(300):
        current = runtime.get(job.job_id)
        if current.status in {"completed", "failed"}:
            assert current.status == "completed", current.error
            return current
        time.sleep(.01)
    raise AssertionError("临时候选未结束")


def files(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns) for path in root.rglob("*") if path.is_file()}


def main():
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".backup" / "proposal-reconcile-ui")
    args = parser.parse_args(); args.output_dir.mkdir(parents=True, exist_ok=True)
    projects = Path(tempfile.mkdtemp(prefix="creative-os-reconcile-ui-"))
    root = NovelProjectCreator(projects).create("审阅核对验收", "Idea", operation_id="create", story_mode=False)
    client = FakeClient()
    original_registry = ProjectRegistry(projects, client_factory=lambda: client)
    runtime = original_registry.get(root.name, writable=True)["agent_runtime"]
    job = finish(runtime, runtime.submit("生成候选", 1, mode="act"))
    original_append = FeedbackStore.append_once
    def interrupted_append(store, record):
        original_append(store, record)
        raise OSError("feedback_after_append_interrupted")
    target = {"project_id": root.name, "chapter_number": 1, "session_id": job.session_id, "proposal_id": job.proposal_id}
    with patch.object(FeedbackStore, "append_once", interrupted_append):
        result = runtime.proposal_commands.execute(CommandRequest("review_writer_proposal", "original-accept", "验收作者", target,
                                                                 {"action": "accept", "reason": "原审阅决定"}, idempotency_key="original-accept"))
        assert result.error.code == "command_outcome_unknown"
    original_review = runtime.proposals.read(job.proposal_id)["review"]
    manual = "这是随后由作者保存的人工稿，核对原操作不得覆盖。"
    runtime.store.save(1, manual, actor="作者", expected_version=1)
    original_registry.close()
    registry = ProjectRegistry(projects, client_factory=lambda: client)
    server = create_server(EmptyWorkspace(None, "none"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True); worker.start()
    errors = []
    try:
        before = files(root)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-background-networking", "--disable-sync"])
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, service_workers="block")
            context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname in {"127.0.0.1", "localhost", "::1"} else route.abort())
            page = context.new_page(); page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/p/{quote(root.name)}/writer?chapter=1")
            page.wait_for_function("document.querySelector('#editor').value.includes('随后由作者保存')")
            page.locator("#reconcile-agent-review").wait_for(state="visible")
            assert page.locator("#agent-review-actions").is_hidden()
            assert files(root) == before and client.calls == 1
            page.locator("#reconcile-agent-review").scroll_into_view_if_needed()
            page.screenshot(path=str(args.output_dir / "needs-reconcile.png"), full_page=True)
            page.locator("#reconcile-agent-review").click()
            page.locator("#reconcile-agent-review").wait_for(state="hidden")
            assert page.locator("#editor").input_value() == manual
            active = registry.get(root.name)["agent_runtime"]
            proposal = active.proposals.read(job.proposal_id)
            assert proposal["status"] == "accepted"
            assert active.store.current(1)[1] == manual and len(active.store.versions(1)) == 2
            assert proposal["review"]["feedback"] == original_review["feedback"] and proposal["review"]["actor"] == "验收作者"
            assert len(FeedbackStore(root, initialize=False).list()) == 1
            assert FileCommandResultStore(root).read("original-accept").state.value == "completed"
            assert client.calls == 1 and not errors, errors
            page.screenshot(path=str(args.output_dir / "reconciled.png"), full_page=True)
            report = {"status": "passed", "temporary_projects_root": str(projects), "model_calls": client.calls,
                      "proposal_id": job.proposal_id, "feedback_id": original_review["feedback"]["id"],
                      "draft_versions": 2, "manual_draft_preserved": True, "browser_errors": errors}
            (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            browser.close(); print(json.dumps(report, ensure_ascii=False))
    finally:
        server.shutdown(); server.server_close(); worker.join(); registry.close()


if __name__ == "__main__":
    with fake_validation_guard() as blocked:
        main()
        assert not blocked, blocked
