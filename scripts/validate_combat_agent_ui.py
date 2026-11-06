"""战斗 Agent V1 任务6隔离验收。

只创建临时项目、随机本机端口和 Fake 模型；脚本不会读取或写入真实书稿。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from http.client import HTTPConnection
from pathlib import Path
import sys
from threading import Thread
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from creative_os.project_registry import ProjectRegistry
from creative_os.web_workspace import WorkspaceWebAdapter, create_server
from creative_os.workspace_query import WorkspaceQueryAdapter
from scripts.fake_validation_guard import fake_validation_guard


class EmptyWorkspace(WorkspaceWebAdapter):
    """HTTP 根页面只需要一个稳定的空投影；项目数据由 /p/<id> 路由提供。"""

    def read_json(self):
        return b'{"project_id":"temporary-root","snapshot":{},"operations":{}}'


class FakeCombatClient:
    """按协议动作返回确定性结果，并保留每次真实入模消息。"""

    def __init__(self):
        self.calls = []
        self.fail_once_for = {"乙书故障重试"}
        self.failed = set()

    def complete(self, messages, **kwargs):
        rows = [{"role": item.role, "content": item.content} for item in messages]
        self.calls.append(rows)
        joined = "\n".join(item["content"] for item in rows)
        if any(marker in joined for marker in self.fail_once_for) and "乙书故障重试" not in self.failed:
            self.failed.add("乙书故障重试")
            raise RuntimeError("fake_retry_once")
        system = rows[0]["content"] if rows else ""
        if "小说前期架构讨论 Agent" in system:
            return json.dumps({"action": "finish_turn", "reply": "讨论完成；正式设定仍需作者确认。"}, ensure_ascii=False)
        if "长篇小说 Writer Agent" in system and "请只分析问题" in joined:
            return json.dumps({"action": "finish", "reply": "分析完成，候选仍需作者审阅。"}, ensure_ascii=False)
        if "战斗编排专家" in system:
            header = {}
            for item in reversed(rows):
                try:
                    value = json.loads(item["content"])
                except (TypeError, ValueError):
                    continue
                if isinstance(value, dict) and "scope" in value and "sources" in value:
                    header = value
                    break
            sources = header.get("sources") or []
            source_id = next((item["source_id"] for item in sources if item.get("source_id") and item.get("usage") == "included"), "")
            scope = header.get("scope", {}).get("chapter_numbers", [])
            instruction = header.get("instruction", "")
            if source_id and len(scope) == 1 and "缺正文" not in instruction:
                if not any("只读工具结果" in item["content"] for item in rows):
                    return json.dumps({"action": "read_source", "source_id": source_id}, ensure_ascii=False)
                noncombat = "乙书" in joined
                return json.dumps({
                    "action": "finish", "verdict": "noncombat" if noncombat else "combat",
                    "reply": "乙书本章以谈判冲突为主。" if noncombat else "甲书战斗计划：断桥撤离并承担声誉代价。",
                    "alternatives": ["保留谈判出口"], "foreshadowing": ["下一章回收未偿代价"],
                    "evidence_refs": [source_id], "unknowns": ["敌方后援规模"],
                }, ensure_ascii=False)
            return json.dumps({
                "action": "finish", "verdict": "insufficient", "reply": "目标章节正文缺失，无法判断章内战斗。",
                "alternatives": [], "foreshadowing": [], "evidence_refs": [], "unknowns": ["目标章节正文未提供"],
            }, ensure_ascii=False)
        # act 使用 RuntimeRunner 的正文出口；正文足量且包含唯一书籍哨兵。
        marker = "乙书" if "乙书" in joined else "甲书"
        return "《第2章》\n" + marker + "确认计划进入本章，主角在断桥前作出选择。" * 80


def _request(base, method, path, payload=None, posts=None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    record = None
    if posts is not None and method == "POST":
        record = {"path": path, "bytes": len(body or b""), "sha256": hashlib.sha256(body or b"").hexdigest(), "payload": payload}
        posts.append(record)
    connection = HTTPConnection(base.split("://", 1)[1], timeout=15)
    connection.request(method, path, body=body, headers={"Content-Type": "application/json"} if body is not None else {})
    response = connection.getresponse()
    raw = response.read()
    status = response.status
    connection.close()
    if record is not None:
        record["status"] = status
        assert record["bytes"] == len(body or b"")
        assert json.loads((body or b"{}").decode("utf-8")) == payload
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = raw.decode("utf-8", errors="replace")
    return status, value, raw


def _wait_job(base, project_id, job_id, *, chapter, posts):
    path = f"/p/{quote(project_id)}/api/agent/jobs/{job_id}?project_id={quote(project_id)}&chapter_number={chapter}&session_id="
    # Session id is filled by caller through retrying query from the public response.
    for _ in range(200):
        status, value, _ = _request(base, "GET", path)
        if status == 200 and value.get("status") in {"completed", "failed"}:
            return value
        time.sleep(0.03)
    raise AssertionError(f"job_timeout:{project_id}:{job_id}")


def _story_command(project_id, session_id, command_id, payload, key, base, posts):
    request = {"command_id": command_id, "request_id": key, "actor": "作者",
               "target": {"project_id": project_id, "scope": "story", "session_id": session_id},
               "payload": payload, "expected_version": None, "idempotency_key": key}
    return _request(base, "POST", f"/p/{quote(project_id)}/api/commands/{command_id.replace('_', '-')}", request, posts)


def _run_book(base, registry, project_id, title, *, output_dir, client, posts, missing_target=False):
    entry = registry.get(project_id, writable=True)
    runtime = entry["agent_runtime"]
    chapter_session = runtime.conversations.read(2)["session_id"]
    story_session = runtime.story.session_id
    # 目标正文是临时书的一部分；缺正文路径使用乙书第三章，仅用于未知断言。
    if not missing_target:
        final = entry["agent_runtime"].root / "production" / "final_chapters" / "chapter_002.md"
        final.write_text(f"{title}临时正文：断桥与谈判的证据。", encoding="utf-8")

    # 讨论链：普通讨论可完成，不把聊天认可当成确认。
    status, discussion, _ = _request(base, "POST", f"/p/{quote(project_id)}/api/story/intents",
        {"project_id": project_id, "scope": "story", "session_id": story_session, "instruction": f"{title}讨论战斗与代价"}, posts)
    assert status == 202
    while runtime.get(discussion["job_id"]).status not in {"completed", "failed"}:
        time.sleep(0.03)

    target_chapter = 3 if missing_target else 2
    chapter_session = runtime.conversations.read(target_chapter)["session_id"]
    if not missing_target:
        # 自主路径：未显式请求专家时可完成普通分析，且不产生 combat_results。
        status, autonomous, _ = _request(base, "POST", f"/p/{quote(project_id)}/api/agent/intents",
            {"project_id": project_id, "chapter_number": target_chapter, "session_id": chapter_session,
             "instruction": f"{title}自主普通分析", "mode": "analyze", "target_words": 1, "tolerance_words": 1000}, posts)
        assert status == 202, autonomous
        auto_job = runtime.get(autonomous["job_id"])
        runtime._futures[auto_job.job_id].result(timeout=15)
        auto_job = runtime.get(auto_job.job_id)
        assert auto_job.status == "completed" and not auto_job.combat_results
    instruction = "缺正文" if missing_target else f"{title}请专家研究本章"
    status, accepted, _ = _request(base, "POST", f"/p/{quote(project_id)}/api/agent/intents",
        {"project_id": project_id, "chapter_number": target_chapter, "session_id": chapter_session,
         "instruction": instruction, "mode": "analyze", "requested_expert": "combat", "target_words": 1, "tolerance_words": 1000}, posts)
    assert status == 202, accepted
    job = runtime.get(accepted["job_id"])
    runtime._futures[job.job_id].result(timeout=15)
    job = runtime.get(job.job_id)
    if job.status != "completed":
        (output_dir / f"debug-{project_id}.json").write_text(json.dumps(client.calls, ensure_ascii=False, indent=2), encoding="utf-8")
        raise AssertionError(job.error)
    combat = job.combat_results[-1]
    # 未确认候选不可进入显式战斗写作，普通写作仍能继续。
    if not missing_target:
        try:
            runtime.submit("显式采用计划但尚未确认", 2, mode="act", target_words=1, tolerance_words=1000,
                           session_id=chapter_session, require_confirmed_combat=True)
        except ValueError as error:
            assert str(error) == "story_confirmation_required"
        else:
            raise AssertionError("未确认计划不应受理显式战斗写作")
        ordinary = runtime.submit("普通写作可继续", 2, mode="act", target_words=1, tolerance_words=1000, session_id=chapter_session)
        runtime._futures[ordinary.job_id].result(timeout=15)
        assert runtime.get(ordinary.job_id).proposal_id
    if missing_target:
        assert combat["verdict"] == "insufficient" and combat["unknowns"]
        return {"project_id": project_id, "result_id": combat["result_id"], "verdict": combat["verdict"], "unknowns": combat["unknowns"]}

    # 采用仅传 result_id；随后作者编辑并确认候选。
    before = runtime.story.view()
    status, adopted, _ = _story_command(project_id, story_session, "adopt_combat_candidate",
        {"result_id": combat["result_id"], "expected_revision": before["candidate"]["revision"] if before["candidate"] else 0},
        f"adopt-{project_id}", base, posts)
    assert status == 202, adopted
    view = runtime.story.view()
    blocks = view["candidate"]["content"]["blocks"]
    for block in blocks:
        if block["key"].startswith("combat-plan:"):
            block["text"] += " 作者确认：保留谈判出口。"
    status, edited, _ = _story_command(project_id, story_session, "edit_story_candidate",
        {"blocks": blocks, "open_questions": view["candidate"]["content"]["open_questions"], "expected_revision": view["candidate"]["revision"]},
        f"edit-{project_id}", base, posts)
    assert status == 202, edited
    candidate = runtime.story.view()["candidate"]
    status, confirmed, _ = _story_command(project_id, story_session, "confirm_story_candidate",
        {"revision": candidate["revision"], "hash": candidate["hash"], "expected_confirmed_version": 0},
        f"confirm-{project_id}", base, posts)
    assert status == 202, confirmed
    frozen = runtime.story.view()["confirmed"]
    assert frozen and frozen["version"] == 1
    # 迟到/旧 revision 冲突必须拒绝，不产生第二版本。
    status, conflict, _ = _story_command(project_id, story_session, "adopt_combat_candidate",
        {"result_id": combat["result_id"], "expected_revision": 0}, f"stale-{project_id}", base, posts)
    assert status in {409, 422} and runtime.story.view()["confirmed"]["version"] == 1
    # 确认计划进入目标章节真实消息，Proposal 仍需接受。
    status, accepted, _ = _request(base, "POST", f"/p/{quote(project_id)}/api/agent/intents",
        {"project_id": project_id, "chapter_number": 2, "session_id": chapter_session,
         "instruction": f"{title}按已确认战斗计划写作", "mode": "act", "require_confirmed_combat": True,
         "target_words": 1, "tolerance_words": 1000}, posts)
    assert status == 202, accepted
    final_job = runtime.get(accepted["job_id"])
    runtime._futures[final_job.job_id].result(timeout=15)
    final_job = runtime.get(final_job.job_id)
    assert final_job.status == "completed" and final_job.proposal_id
    prompt = "\n".join(item["content"] for item in client.calls[-1])
    assert "未来创作计划，不是已发生事实" in prompt and "保留谈判出口" in prompt
    proposal = runtime.proposals.view(final_job.proposal_id)
    assert proposal["diff"]
    status, review, _ = _request(base, "POST", f"/p/{quote(project_id)}/api/commands/review-writer-proposal", {
        "command_id": "review_writer_proposal", "request_id": f"review-{project_id}", "actor": "作者",
        "target": {"project_id": project_id, "chapter_number": 2, "session_id": chapter_session, "proposal_id": final_job.proposal_id},
        "payload": {"action": "accept", "reason": "接受任务6验收候选"}, "expected_version": None, "idempotency_key": f"review-{project_id}"}, posts)
    assert status == 202, review
    draft = runtime.store.current(2)
    assert draft and title in draft[1]
    return {"project_id": project_id, "result_id": combat["result_id"], "verdict": combat["verdict"],
            "confirmed_version": frozen["version"], "proposal_id": final_job.proposal_id,
            "draft_version": draft[0].version, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "messages": client.calls[-1]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".backup" / "combat-task6")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="creative-os-combat-task6-"))
    client = FakeCombatClient()
    registry = ProjectRegistry(temporary, client_factory=lambda: client)
    project_a = registry.creator.create("任务6甲书", "甲书 Idea：断桥谈判", story_mode=False)
    project_b = registry.creator.create("任务6乙书", "乙书 Idea：无战斗正文", story_mode=False)
    ids = [project_a.name, project_b.name]
    posts = []
    server = create_server(EmptyWorkspace(None, "temporary-root"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True); worker.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    browser_errors = []
    screenshots = []
    books = {}
    try:
        books[project_a.name] = _run_book(base, registry, project_a.name, "甲书", output_dir=args.output_dir,
                                          client=client, posts=posts)
        books[project_b.name] = _run_book(base, registry, project_b.name, "乙书", output_dir=args.output_dir,
                                          client=client, posts=posts, missing_target=True)
        # 独立失败重试：首调用失败，重试沿用冻结输入且不重复产生候选版本。
        runtime_b = registry.get(project_b.name, writable=True)["agent_runtime"]
        session_b = runtime_b.conversations.read(2)["session_id"]
        status, failed, _ = _request(base, "POST", f"/p/{quote(project_b.name)}/api/agent/intents", {
            "project_id": project_b.name, "chapter_number": 2, "session_id": session_b, "instruction": "乙书故障重试",
            "mode": "analyze", "target_words": 1, "tolerance_words": 1000}, posts)
        assert status == 202
        runtime_b._futures[failed["job_id"]].result(timeout=15)
        old = runtime_b.get(failed["job_id"]); assert old.status == "failed" and old.error == "fake_retry_once"
        status, retried, _ = _request(base, "POST", f"/p/{quote(project_b.name)}/api/agent/jobs/{failed['job_id']}/retry", {
            "project_id": project_b.name, "chapter_number": 2, "session_id": session_b}, posts)
        assert status == 202
        runtime_b._futures[retried["job_id"]].result(timeout=15)
        assert runtime_b.get(retried["job_id"]).status == "completed"

        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-background-networking", "--disable-sync"])
            for width, height in ((1440, 1000), (390, 844)):
                context = browser.new_context(viewport={"width": width, "height": height}, service_workers="block")
                context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
                page = context.new_page()
                page.on("pageerror", lambda error: browser_errors.append(str(error)))
                page.goto(f"{base}/p/{quote(project_a.name)}/writer?chapter=2")
                # 390 布局通过面板切换按钮进入对话；桌面布局同样显式切到对话面板便于验收入口。
                page.evaluate("document.querySelector('[data-workspace-panel=agent]').click()")
                page.locator("#combat-expert-entry").wait_for(state="visible")
                assert page.locator("#combat-expert-entry").evaluate("el => el.tabIndex >= 0")
                assert "战斗专家" in page.locator("body").inner_text()
                page.screenshot(path=str(args.output_dir / f"combat-{width}.png"), full_page=True)
                screenshots.append(str(args.output_dir / f"combat-{width}.png"))
                if width == 390:
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                context.close()
            browser.close()
        # 纯 GET 刷新没有 POST，且消息与结果按书隔离。
        before_post_count = len(posts)
        _request(base, "GET", f"/p/{quote(project_a.name)}/api/story?project_id={quote(project_a.name)}&scope=story&session_id={registry.get(project_a.name, writable=True)['agent_runtime'].story.session_id}")
        assert len(posts) == before_post_count
        assert not browser_errors
        report = {"status": "passed", "temporary_projects_root": str(temporary), "port": server.server_address[1],
                  "projects": ids, "books": books, "screenshots": screenshots, "browser_errors": browser_errors,
                  "post_count": len(posts), "posts": posts, "fake_model_calls": len(client.calls),
                  "messages_sha256": [hashlib.sha256(json.dumps(call, ensure_ascii=False, sort_keys=True).encode()).hexdigest() for call in client.calls]}
        (args.output_dir / "messages.json").write_text(json.dumps(client.calls, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output_dir / "posts.json").write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "passed", "port": server.server_address[1], "post_count": len(posts), "output_dir": str(args.output_dir)}, ensure_ascii=False))
    finally:
        server.shutdown(); server.server_close(); worker.join(); registry.close()


if __name__ == "__main__":
    with fake_validation_guard():
        main()
