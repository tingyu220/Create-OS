"""在临时项目上用 Fake 模型验证真实浏览器；保留截图及临时数据供核对。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from threading import Thread
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.memory.feedback import FeedbackStore
from creative_os.web_workspace import WorkspaceWebAdapter, WriterWebAdapter, create_server


class FakeWorkspace(WorkspaceWebAdapter):
    def read_json(self):
        return json.dumps({"project_id": "proposal-ui-test", "snapshot": {}, "operations": {}}).encode()


class FakeClient:
    def complete(self, messages, **kwargs):
        return "第1章\n\n他停在门口，没有立即回答。\n" + "先看清眼前的选择，再决定下一步。" * 24


def finish(runtime, job):
    for _ in range(300):
        result = runtime.get(job.job_id)
        if result.status in {"completed", "failed"}:
            assert result.status == "completed", result.error
            return result
        time.sleep(0.01)
    raise AssertionError("候选生成超时")


def main():
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".backup" / "proposal-ui")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    project = Path(tempfile.mkdtemp(prefix="creative-os-proposal-ui-"))
    with patch("creative_os.agent_runtime.OpenAICompatibleClient.from_env", return_value=FakeClient()):
        runtime = WriterAgentRuntime(project, project_id="proposal-ui-test")
        original = "第一章原工作稿。作者还没有接受任何候选。"
        runtime.store.save(1, original, actor="验收作者")
        job = finish(runtime, runtime.submit("改写第一章", 1, mode="act"))
        server = create_server(FakeWorkspace(None, "proposal-ui-test"), writer_adapter=WriterWebAdapter(project, "proposal-ui-test"),
                               agent_runtime=runtime, port=0)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        errors = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_address[1]}/writer?chapter=1")
                page.wait_for_function("document.querySelector('#editor').value.includes('原工作稿')")
                assert runtime.store.current(1)[0].version == 1
                page.locator("#agent-proposal-list button").click()
                page.locator("#agent-candidate").get_by_text("他停在门口", exact=False).wait_for()
                assert page.locator("#editor").input_value() == original
                page.locator('[data-chapter-tab="diff"]').click()
                assert "第一章原工作稿" in page.locator("#agent-diff").inner_text()
                page.screenshot(path=str(args.output_dir / "proposal-desktop.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator('[data-workspace-panel="chapter"]').click()
                page.screenshot(path=str(args.output_dir / "proposal-mobile.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.locator('[data-workspace-panel="agent"]').click()
                page.locator("#decision-feedback").fill("人物动机不足，暂不采用")
                page.locator("#reject-agent-draft").click()
                page.wait_for_function("document.querySelector('#agent-proposal-summary').textContent.includes('已拒绝')")
                assert runtime.store.current(1)[1] == original
                assert len(runtime.store.versions(1)) == 1
                page.reload()
                page.wait_for_function("document.querySelector('#agent-proposal-summary').textContent.includes('已拒绝')")
                assert len(FeedbackStore(project).list()) == 1
                assert runtime.proposals.read(job.proposal_id)["status"] == "rejected"
                page.locator('[data-workspace-panel="agent"]').click()
                page.locator("#agent-continue").click()
                page.wait_for_function("document.querySelectorAll('#agent-proposal-list button').length === 2 && document.querySelector('#agent-proposal-summary').textContent.includes('待审阅')")
                page.locator('[data-workspace-panel="agent"]').click()
                page.locator("#decision-feedback").fill("以冻结原稿为准，增加人物动作")
                page.locator("#proposal-source").select_option("base")
                page.locator("#revise-agent-draft").click()
                page.wait_for_function("document.querySelectorAll('#agent-proposal-list button').length === 3 && document.querySelector('#agent-proposal-summary').textContent.includes('待审阅')")
                assert runtime.store.current(1)[0].version == 1
                page.locator('[data-workspace-panel="agent"]').click()
                page.locator("#accept-agent-draft").click()
                page.wait_for_function("document.querySelector('#agent-proposal-summary').textContent.includes('已接受为工作稿')")
                assert runtime.store.current(1)[0].version == 2
                assert "他停在门口" in page.locator("#editor").input_value()
                assert len(FeedbackStore(project).list()) == 3
                page.locator('[data-workspace-panel="chapter"]').click()
                page.screenshot(path=str(args.output_dir / "proposal-accepted.png"), full_page=True)
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
            runtime._pool.shutdown(wait=True)
    print(json.dumps({"status": "通过", "project": str(project), "output_dir": str(args.output_dir),
                      "viewports": ["1440x1000", "390x844"], "browser_errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
