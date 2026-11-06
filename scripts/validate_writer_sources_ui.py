"""临时项目与 Fake 模型：当次来源、历史不漂移、长文和窄屏验收。"""

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

    output = ROOT / ".backup/source-ui"
    output.mkdir(parents=True, exist_ok=True)
    project = Path(tempfile.mkdtemp(prefix="creative-os-source-ui-"))
    calls = []

    class FakeClient:
        def complete(self, messages, **kwargs):
            calls.append(messages)
            return "第2章\n他在门前停下，重新考虑自己的决定。"

    with patch("creative_os.agent_runtime.OpenAICompatibleClient.from_env", return_value=FakeClient()):
        runtime = WriterAgentRuntime(project, "proposal-ui-test")
        final = project / "production/final_chapters"
        final.mkdir(parents=True)
        (final / "chapter_001.md").write_text("历史前文章节。" * 1200, encoding="utf-8")
        projection = project / ".creative_os/projection/bundle.json"
        projection.parent.mkdir(parents=True)
        projection.write_text('{"marker":"未读取的投影正文"}', encoding="utf-8")
        original = "历史工作稿开始\n" + "当时正文段落，人物在门前犹豫。\n" * 400 + "历史工作稿结束"
        runtime.store.save(2, original, actor="作者")
        first = finish(runtime, runtime.submit("修改第二章", 2, mode="act"))
        reviewed = runtime.proposal_commands.execute(CommandRequest(
            "review_writer_proposal", "reject", "作者",
            {"project_id": runtime.project_id, "chapter_number": 2, "session_id": first.session_id, "proposal_id": first.proposal_id},
            {"action": "reject", "reason": "缺少可见动作"}, idempotency_key="reject"))
        assert reviewed.status == "accepted"
        feedback = FeedbackStore(project).list()[0]
        target = {"project_id": runtime.project_id, "chapter_number": 2, "session_id": first.session_id, "feedback_id": feedback.id}

        def lesson(action, key, **payload):
            return runtime.lesson_commands.execute(CommandRequest("manage_writer_lesson", key, "作者", target,
                                                                  {"action": action, **payload}, idempotency_key=key))

        created = lesson("create", "create", title="可见动作", content="通过具体动作表现犹豫，仅适用本章。", range="chapter")
        memory_id = created.emitted_event_refs[0].split(":")[1]
        assert lesson("approve", "approve", memory_id=memory_id, version=1, note="适用本章").status == "accepted"
        job = finish(runtime, runtime.submit("核对当次来源", 2))
        actual = calls[-1]
        scope = dict(project_id=runtime.project_id, chapter_number=2, session_id=job.session_id, job_id=job.job_id)
        index = runtime.context_sources.read(**scope)
        sources = [runtime.context_sources.read(**scope, source_id=item["source_id"])["source"] for item in index["sources"]]
        for item in sources:
            if item["usage"] == "included":
                location = item["message_location"]
                assert actual[location["index"]].content[location["start"]:location["end"]] == item["content_snapshot"]
        draft = next(item for item in sources if item["label"] == "当前工作稿")
        experience = next(item for item in sources if "experience" in item)
        projection_source = next(item for item in sources if item["label"] == "项目投影引用")
        assert lesson("archive", "archive", memory_id=memory_id, version=1, note="本轮停止使用").status == "accepted"
        runtime.store.save(2, "当前人工新稿（来源阅读不应改变）", actor="作者", expected_version=1)
        (final / "chapter_001.md").write_text("已经改过的前文", encoding="utf-8")
        server = create_server(FakeWorkspace(None, runtime.project_id), writer_adapter=WriterWebAdapter(project, runtime.project_id),
                               agent_runtime=runtime, port=0)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        errors = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))
                url = f"http://127.0.0.1:{server.server_address[1]}/writer?chapter=2"
                page.goto(url)
                page.wait_for_function("document.querySelector('#editor').value.includes('当前人工新稿')")
                page.locator(f'#agent-task-status [data-task-id="{job.job_id}"] button').click()
                page.locator(f'#agent-source-list [data-source-id="{draft["source_id"]}"]').click()
                page.wait_for_function("document.querySelector('#source-detail .source-content')?.textContent.includes('历史工作稿结束')")
                assert page.locator("#source-detail .source-content").inner_text() == original
                assert "完整内容" in page.locator("#source-detail").inner_text()
                panel = page.locator('[data-chapter-panel="details"]')
                assert panel.evaluate("el => el.scrollHeight > el.clientHeight")
                panel.evaluate("el => el.scrollTop = el.scrollHeight")
                assert panel.evaluate("el => el.scrollTop > 0")
                page.screenshot(path=str(output / "source-desktop.png"), full_page=True)
                assert page.locator("#editor").input_value() == "当前人工新稿（来源阅读不应改变）"
                page.locator(f'#agent-source-list [data-source-id="{experience["source_id"]}"]').click()
                page.wait_for_function("document.querySelector('#source-detail .source-content')?.textContent.includes('通过具体动作')")
                assert "当次入模" in page.locator("#source-detail-status").inner_text()
                assert "不代表资料当前状态" in page.locator("#source-detail").inner_text()
                page.locator(f'#agent-source-list [data-source-id="{projection_source["source_id"]}"]').click()
                page.wait_for_function("document.querySelector('#source-detail-status').textContent.includes('未入模')")
                assert "没有可展示" in page.locator("#source-detail .source-content").inner_text()
                page.reload()
                page.wait_for_function("document.querySelector('#editor').value.includes('当前人工新稿')")
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator('[data-workspace-panel="agent"]').click()
                page.locator(f'#agent-task-status [data-task-id="{job.job_id}"] button').click()
                page.wait_for_function("document.querySelector('#source-detail .source-content')")
                assert page.locator('.writer-grid').get_attribute("data-active-panel") == "chapter"
                page.locator('[data-workspace-panel="agent"]').click()
                page.locator(f'#agent-source-list [data-source-id="{draft["source_id"]}"]').click()
                page.wait_for_function("document.querySelector('#source-detail .source-content')?.textContent.includes('历史工作稿结束')")
                panel.evaluate("el => el.scrollTop = 0")
                page.screenshot(path=str(output / "source-mobile.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                assert page.locator('[data-chapter-tab="details"]').evaluate("el => { const box = el.getBoundingClientRect(); return box.left >= 0 && box.right <= innerWidth; }")
                assert panel.evaluate("el => el.scrollWidth <= el.clientWidth && el.scrollHeight > el.clientHeight")
                assert page.locator("#editor").input_value() == "当前人工新稿（来源阅读不应改变）"
                assert len(runtime.store.versions(2)) == 2 and not errors, errors
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
