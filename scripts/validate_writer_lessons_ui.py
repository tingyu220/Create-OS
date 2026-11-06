"""临时项目与 Fake 模型的经验候选、批准和刷新浏览器验收。"""

import json
from pathlib import Path
import tempfile
from threading import Thread
from unittest.mock import patch

from validate_writer_proposal_ui import ROOT, FakeWorkspace, finish
from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.memory.feedback import FeedbackStore
from creative_os.web_workspace import WriterWebAdapter, create_server
from creative_os.workspace_command import CommandRequest


def main():
    from playwright.sync_api import sync_playwright

    output = ROOT / ".backup/lesson-ui"
    output.mkdir(parents=True, exist_ok=True)
    project = Path(tempfile.mkdtemp(prefix="creative-os-lesson-ui-"))
    calls = []

    class FakeClient:
        def complete(self, messages, **kwargs):
            calls.append(messages)
            return "第1章\n他在门前停步，把信交给了同伴。"

    with patch("creative_os.agent_runtime.OpenAICompatibleClient.from_env", return_value=FakeClient()):
        runtime = WriterAgentRuntime(project, "proposal-ui-test")
        runtime.store.save(1, "验收原工作稿", actor="作者")
        job = finish(runtime, runtime.submit("改写第一章", 1, mode="act"))
        rejected = runtime.proposal_commands.execute(CommandRequest(
            "review_writer_proposal", "reject", "作者",
            {"project_id": runtime.project_id, "chapter_number": 1, "session_id": job.session_id,
             "proposal_id": job.proposal_id}, {"action": "reject", "reason": "动机没有通过动作体现"}, idempotency_key="reject"))
        assert rejected.status == "accepted"
        server = create_server(FakeWorkspace(None, runtime.project_id),
                               writer_adapter=WriterWebAdapter(project, runtime.project_id), agent_runtime=runtime, port=0)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        errors = []
        experience = "本章通过可见动作承载人物动机，保留人物犹豫的过程。"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_address[1]}/writer?chapter=1")
                page.locator("#lesson-feedback option").wait_for(state="attached")
                page.locator(".lesson-review summary").first.click()
                page.locator("#lesson-title").fill("动作承载动机")
                page.locator("#lesson-content").fill(experience)
                page.locator("#lesson-create").click()
                page.get_by_role("button", name="批准经验", exact=True).wait_for()
                page.locator("#lesson-list details summary").click()
                page.locator("#lesson-list").scroll_into_view_if_needed()
                page.screenshot(path=str(output / "lesson-desktop.png"), full_page=True)
                finish(runtime, runtime.submit("检查本章", 1))
                assert experience not in calls[-1][-1].content
                page.locator("#lesson-note").fill("确认仅适用本章，作为写作方法参考")
                page.get_by_role("button", name="批准经验", exact=True).click()
                page.get_by_role("button", name="归档经验", exact=True).wait_for()
                finish(runtime, runtime.submit("检查本章动作", 1))
                assert experience in calls[-1][-1].content
                page.reload()
                page.wait_for_function("document.querySelector('#lesson-list').textContent.includes('已批准')")
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator('[data-workspace-panel="agent"]').click()
                page.locator(".lesson-review summary").first.click()
                page.locator("#lesson-list").scroll_into_view_if_needed()
                page.screenshot(path=str(output / "lesson-mobile.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.locator("#lesson-note").fill("本轮结束，停止后续引用")
                page.get_by_role("button", name="归档经验", exact=True).click()
                page.wait_for_function("document.querySelector('#lesson-list').textContent.includes('已归档')")
                finish(runtime, runtime.submit("再次检查本章", 1))
                assert experience not in calls[-1][-1].content
                assert runtime.store.current(1)[1] == "验收原工作稿"
                assert len(runtime.store.versions(1)) == len(FeedbackStore(project).list()) == 1
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
            runtime._pool.shutdown(wait=True)
    print(json.dumps({"status": "通过", "project": str(project), "screenshots": str(output),
                      "viewports": ["1440x1000", "390x844"], "browser_errors": errors, "fake_calls": len(calls)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
