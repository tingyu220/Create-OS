"""临时 projects + Fake 模型 + Chromium，验证 Idea 到接受首章工作稿。"""

import argparse
import json
from pathlib import Path
import sys
import tempfile
from threading import Thread
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creative_os.project_registry import ProjectRegistry
from creative_os.web_workspace import WorkspaceWebAdapter, create_server


BLOCKS = [{"key": key, "title": title, "text": text} for key, title, text in [
    ("core", "故事核心", "核心哨兵：记忆可交易"), ("world", "世界背景", "世界哨兵：海上城市"),
    ("cast", "主要人物", "人物哨兵：修钟人"), ("conflict", "核心冲突", "冲突哨兵：救人与守约"),
    ("direction", "整体方向", "方向哨兵：寻找失落航线")]]


class FakeClient:
    def __init__(self):
        self.calls = []
        self.actions = iter([
            {"action": "read_candidate"}, {"action": "finish_turn", "reply": "这个 Idea 很适合从人物代价讨论：主角愿意牺牲哪段记忆？也可以先比较两种海城规则。"},
            {"action": "propose_revision", "expected_revision": 0, "blocks": BLOCKS, "open_questions": ["最终代价待讨论"]},
            {"action": "finish_turn", "reply": "已补充主角和核心冲突，右侧是可自由编辑的故事候选。"},
            {"action": "read_confirmed"},
            {"action": "propose_revision", "expected_revision": 2, "blocks": [{**BLOCKS[0], "text": "未确认哨兵：另一种核心"}], "open_questions": []},
            {"action": "finish_turn", "reply": "新想法只进入候选 v3，正式设定仍是作者确认的候选 v2。"},
            "《第1章》\n\n盲眼修钟人站在海城的栈桥，听见风里有人叫出他遗忘的名字。\n" + "他握住旧钟，选择先救眼前的人。" * 260,
        ])

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        result = next(self.actions)
        return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else result


class EmptyWorkspace(WorkspaceWebAdapter):
    def read_json(self):
        return b'{"project_id":"none","snapshot":{},"operations":{}}'


def main():
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".backup" / "story-ui")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="creative-os-story-ui-"))
    client = FakeClient()
    registry = ProjectRegistry(temporary, client_factory=lambda: client)
    server = create_server(EmptyWorkspace(None, "none"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True); worker.start()
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-background-networking", "--disable-sync"])
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, service_workers="block")
            context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname in {"127.0.0.1", "localhost", "::1"} else route.abort())
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/story")
            page.locator("#book-title").fill("海城隔离验收")
            page.locator("#book-idea").fill("一个能交易记忆的海上城市")
            page.locator("#create-submit").click()
            page.wait_for_url("**/p/**/story")
            page.locator("#story-input").wait_for(state="visible")
            page.wait_for_function("document.querySelector('#story-input').value.includes('交易记忆')")
            page.locator("#story-send").click()
            page.get_by_text("这个 Idea 很适合从人物代价讨论", exact=False).wait_for()
            page.locator("#story-input").fill("主角修钟人，愿意牺牲童年记忆去救人")
            page.locator("#story-send").click()
            page.wait_for_function("document.querySelector('#candidate-version').textContent === '候选 v1'")
            page.locator("#candidate-blocks textarea").nth(2).fill("人物哨兵：作者编辑为盲眼修钟人")
            assert page.locator("#confirm-candidate").is_disabled()
            page.locator("#save-candidate").click()
            page.wait_for_function("document.querySelector('#candidate-version').textContent === '候选 v2'")
            page.locator("#confirm-candidate").click()
            page.wait_for_function("document.querySelector('#confirmed-title').textContent.includes('候选 v2')")
            confirmed_text = page.locator("#confirmed-text").inner_text()
            page.screenshot(path=str(args.output_dir / "story-confirmed-desktop.png"), full_page=True)
            page.locator("#story-input").fill("再探索另一种故事核心")
            page.locator("#story-send").click()
            page.wait_for_function("document.querySelector('#candidate-version').textContent === '候选 v3'")
            assert page.locator("#confirmed-text").inner_text() == confirmed_text
            page.reload()
            page.wait_for_function("document.querySelector('#candidate-version').textContent === '候选 v3'")
            assert page.locator("#confirmed-text").inner_text() == confirmed_text
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(args.output_dir / "story-confirmed-mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator("#start-first-chapter").click()
            page.wait_for_url("**/writer?chapter=1")
            page.locator("#agent-proposal-list button").first.wait_for()
            page.locator("#agent-proposal-list button").first.click()
            page.wait_for_function("document.querySelector('#agent-candidate').textContent.includes('盲眼修钟人')")
            page.locator("#accept-agent-draft").click()
            page.wait_for_function("document.querySelector('#editor').value.includes('盲眼修钟人')")
            page.screenshot(path=str(args.output_dir / "story-first-chapter-accepted.png"), full_page=True)
            runtime = registry.get("海城隔离验收")["agent_runtime"]
            assert runtime.store.current(1) is not None
            assert not list((runtime.root / "production/final_chapters").iterdir())
            chapter = next(job for job in runtime._jobs.values() if job.chapter_number == 1)
            prompt = "\n".join(message.content for message in client.calls[-1])
            assert confirmed_text in prompt and "未确认哨兵" not in prompt
            assert all(block["text"] in prompt for block in BLOCKS if block["key"] != "cast")
            assert "人物哨兵：作者编辑为盲眼修钟人" in prompt
            source = next(item for item in chapter.context_snapshot["sources"] if item["label"] == "已确认故事设定")
            location = source["message_location"]
            assert client.calls[-1][location["index"]].content[location["start"]:location["end"]] == confirmed_text
            assert not errors, errors
            report = {"status": "passed", "temporary_projects_root": str(temporary), "project_id": runtime.project_id,
                      "confirmed": runtime.story.view()["confirmed"], "unconfirmed_revision": runtime.story.view()["candidate"]["revision"],
                      "chapter_job": chapter.job_id, "proposal_id": chapter.proposal_id, "draft_version": runtime.store.current(1)[0].version,
                      "model_calls": len(client.calls), "source": source, "browser_errors": errors}
            (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            browser.close()
            print(json.dumps({"status": "passed", "model_calls": len(client.calls), "output_dir": str(args.output_dir), "temporary_projects_root": str(temporary)}, ensure_ascii=False))
    finally:
        server.shutdown(); server.server_close(); worker.join(); registry.close()


if __name__ == "__main__":
    from scripts.fake_validation_guard import fake_validation_guard
    with fake_validation_guard():
        main()
