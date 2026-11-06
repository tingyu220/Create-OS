"""用独立临时项目、延迟 Fake 模型与虚拟时钟验收等待体验，不连接真实服务。"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from threading import Event, Thread
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.web_workspace import WriterWebAdapter, create_server
from scripts.validate_writer_proposal_ui import FakeWorkspace


class DelayedClient:
    def __init__(self):
        self.release = Event()
        self.fail = False
        self.calls = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        assert self.release.wait(90), "验收模型等待超时"
        if self.fail:
            raise RuntimeError("验收用模型限流")
        return "第1章\n\n隔离验收候选正文。" * 30


def main():
    from playwright.sync_api import sync_playwright

    output = ROOT / ".backup" / "progress-ui"
    output.mkdir(parents=True, exist_ok=True)
    project = Path(tempfile.mkdtemp(prefix="creative-os-progress-ui-"))
    client = DelayedClient()
    errors = []
    with patch("creative_os.agent_runtime.OpenAICompatibleClient.from_env", return_value=client):
        runtime = WriterAgentRuntime(project, project_id="proposal-ui-test")
        runtime.store.save(1, "仅供验收的原始工作稿", actor="验收作者")
        server = create_server(FakeWorkspace(None, "proposal-ui-test"), writer_adapter=WriterWebAdapter(project, "proposal-ui-test"), agent_runtime=runtime, port=0)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.clock.install()
                page.goto(f"http://127.0.0.1:{server.server_address[1]}/writer?chapter=1")
                page.wait_for_function("!document.querySelector('#agent-continue').disabled")
                page.locator("#agent-continue").click()
                page.wait_for_function("document.querySelector('#agent-state-text').textContent.includes('生成候选')")
                assert client.calls == 1
                assert "暂不支持中断" in page.locator("#agent-action-reason").inner_text()
                assert page.locator("#agent-send").is_disabled()
                started = runtime.conversation(1)["jobs"][0]["started_at"]
                page.clock.fast_forward(65000)
                page.wait_for_function("document.querySelector('#agent-progress-time').textContent.includes('1分')")
                assert "等待模型服务响应" in page.locator("#agent-progress-note").inner_text()
                page.screenshot(path=str(output / "progress-desktop.png"), full_page=True)
                page.reload()
                page.wait_for_function("document.querySelector('#agent-progress-time').textContent.includes('1分')")
                assert runtime.conversation(1)["jobs"][0]["started_at"] == started
                page.route("**/api/agent/conversations/**", lambda route: route.abort())
                page.locator("#agent-refresh-status").click()
                page.wait_for_function("document.querySelector('#agent-state-text').textContent.includes('查询暂不可用')")
                assert "尚未确认任务完成或失败" in page.locator("#agent-progress-note").inner_text()
                assert runtime.conversation(1)["jobs"][0]["status"] == "thinking"
                assert client.calls == 1
                page.unroute("**/api/agent/conversations/**")
                page.locator("#agent-refresh-status").click()
                page.wait_for_function("document.querySelector('#agent-state-text').textContent.includes('生成候选')")
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator('[data-workspace-panel="agent"]').click()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                send_box = page.locator("#agent-send").bounding_box()
                assert send_box and send_box["y"] + send_box["height"] <= 844
                page.screenshot(path=str(output / "progress-mobile.png"), full_page=True)
                client.release.set()
                page.clock.resume()
                page.wait_for_function("!document.querySelector('#agent-send').disabled")
                page.wait_for_function("document.querySelector('#agent-candidate').textContent.includes('隔离验收候选正文')")
                assert runtime.store.current(1)[0].version == 1
                assert page.locator('[data-chapter-tab="candidate"]').get_attribute("aria-selected") == "true"
                # 第二次模型调用显式失败；只由点击既有重试入口发起第三次调用。
                client.fail = True
                page.locator('[data-workspace-panel="agent"]').click()
                page.locator("#agent-instruction").fill("请只分析候选结构")
                page.locator("#agent-send").click()
                page.wait_for_function("document.querySelector('#agent-state-text').textContent.includes('运行失败')")
                assert page.locator("#agent-send").is_enabled()
                assert client.calls == 2
                client.fail = False
                page.locator("#agent-session-actions button").click()
                page.wait_for_function("document.querySelector('#agent-state-text').textContent.includes('已完成')")
                assert client.calls == 3
                page.locator('[data-workspace-panel="navigation"]').click()
                page.locator("#chapter-number").fill("2")
                page.locator("#open-chapter").click()
                page.wait_for_function("document.querySelector('#agent-state-text').textContent.includes('可以开始对话')")
                page.locator('[data-workspace-panel="agent"]').click()
                assert not page.locator("#agent-progress-time").inner_text()
                assert not errors, errors
                browser.close()
        finally:
            client.release.set()
            server.shutdown()
            server.server_close()
            worker.join()
            runtime._pool.shutdown(wait=True)
    print(json.dumps({"status": "通过", "project": str(project), "output": str(output), "viewports": ["1440x1000", "390x844"], "fake_model_calls": client.calls, "browser_errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
