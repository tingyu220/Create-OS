"""临时 projects 根完整 HTTP 闭环与项目隔离，不触及生产根。"""

from copy import deepcopy
from http.client import HTTPConnection
import json
from threading import Thread
from urllib.parse import quote, urlencode

import pytest
from creative_os.project_registry import ProjectRegistry
from creative_os.web_workspace import WorkspaceWebAdapter, create_server
from test_agent_conversation import finish
from test_story_architecture import BLOCKS
from test_story_agent import ScriptClient


class EmptyWorkspace(WorkspaceWebAdapter):
    def read_json(self):
        return b'{"project_id":"none","snapshot":{},"operations":{}}'


@pytest.fixture
def story_api(tmp_path):
    client = ScriptClient([
        {"action": "read_candidate"}, {"action": "finish_turn", "reply": "你想先谈主题还是人物？"},
        {"action": "propose_revision", "expected_revision": 0, "blocks": BLOCKS, "open_questions": []},
        {"action": "finish_turn", "reply": "候选已形成，请编辑或确认。"},
        {"action": "read_confirmed"},
        {"action": "propose_revision", "expected_revision": 2, "blocks": [{**BLOCKS[0], "text": "未确认哨兵"}], "open_questions": []},
        {"action": "finish_turn", "reply": "保留正式版，继续讨论新候选。"},
        "《第1章》\n修钟人乘船出发。",
    ])
    registry = ProjectRegistry(tmp_path, client_factory=lambda: client)
    server = create_server(EmptyWorkspace(None, "none"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def request(method, path, payload=None):
        connection = HTTPConnection(*server.server_address, timeout=8)
        body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, json.loads(data)
    yield registry, client, request
    server.shutdown(); server.server_close(); worker.join(); registry.close()


def create(request, name="海城"):
    status, created = request("POST", "/api/projects/create", {"title": name, "idea": "记忆交易", "operation_id": name})
    assert status == 201, created
    return created, "/p/" + quote(name) + "/api"


def command(identifier, target, payload, key):
    return {"command_id": identifier, "request_id": key, "actor": "作者", "target": target, "payload": payload,
            "expected_version": None, "idempotency_key": key}


def test_full_http_idea_edit_confirm_rediscuss_chapter_accept(story_api):
    registry, client, request = story_api
    scope, api = create(request)
    root = registry.root / scope["project_id"]
    before = {str(path): (path.stat().st_mtime_ns, path.read_bytes()) for path in root.rglob("*") if path.is_file()}
    status, view = request("GET", api + "/story?" + urlencode(scope))
    assert status == 200 and not view["messages"]
    after = {str(path): (path.stat().st_mtime_ns, path.read_bytes()) for path in root.rglob("*") if path.is_file()}
    assert after == before
    assert registry.get(scope["project_id"])["agent_runtime"].read_only
    status, accepted = request("POST", api + "/story/intents", {**scope, "instruction": "Idea：记忆交易"})
    assert status == 202, accepted
    runtime = registry.get(scope["project_id"])["agent_runtime"]
    assert finish(runtime, runtime.get(accepted["job_id"])).status == "completed"
    status, accepted = request("POST", api + "/story/intents", {**scope, "instruction": "主角修钟人，冲突是救人与守约"})
    assert status == 202
    assert finish(runtime, runtime.get(accepted["job_id"])).status == "completed"
    status, view = request("GET", api + "/story?" + urlencode(scope))
    assert view["candidate"]["revision"] == 1 and view["confirmed"] is None
    blocks = deepcopy(BLOCKS); blocks[2]["text"] = "作者改为盲眼修钟人"
    edit = command("edit_story_candidate", scope, {"expected_revision": 1, "blocks": blocks, "open_questions": []}, "edit")
    assert request("POST", api + "/commands/edit-story-candidate", edit)[0] == 202
    candidate = runtime.story.view()["candidate"]
    assert candidate["revision"] == 2
    confirm = command("confirm_story_candidate", scope, {"revision": 2, "hash": candidate["hash"], "expected_confirmed_version": 0}, "confirm")
    status, result = request("POST", api + "/commands/confirm-story-candidate", confirm)
    assert status == 202, result
    assert request("POST", api + "/commands/confirm-story-candidate", confirm)[1] == result
    confirmed = runtime.story.view()["confirmed"]
    status, accepted = request("POST", api + "/story/intents", {**scope, "instruction": "再考虑另一个核心"})
    assert status == 202
    assert finish(runtime, runtime.get(accepted["job_id"])).status == "completed"
    assert runtime.story.view()["confirmed"] == confirmed and runtime.story.view()["candidate"]["revision"] == 3
    status, accepted = request("POST", api + "/story/start-first-chapter", {**scope, "confirmed_version": confirmed["version"], "confirmed_hash": confirmed["hash"], "target_words": 4500, "tolerance_words": 300})
    assert status == 202, accepted
    chapter = finish(runtime, runtime.get(accepted["job_id"]))
    assert chapter.status == "completed", chapter.error
    assert chapter.proposal_id and runtime.store.current(1) is None
    prompt = "\n".join(message.content for message in client.calls[-1])
    assert confirmed["text"] in prompt and "未确认哨兵" not in prompt
    for block in blocks:
        assert block["text"] in prompt
    target = {"project_id": scope["project_id"], "chapter_number": 1, "session_id": chapter.session_id, "proposal_id": chapter.proposal_id}
    accept = command("review_writer_proposal", target, {"action": "accept", "reason": "采用首章"}, "accept")
    status, result = request("POST", api + "/commands/review-writer-proposal", accept)
    assert status == 202, result
    assert runtime.store.current(1)[1] == "《第1章》\n修钟人乘船出发。"
    assert not list((root / "production/final_chapters").iterdir())


def test_cross_project_invalid_scope_and_unconfirmed_blocked(story_api):
    registry, client, request = story_api
    first, api = create(request)
    other, other_api = create(request, "另一书")
    assert request("GET", other_api + "/story?" + urlencode(first))[0] == 422
    assert request("POST", other_api + "/story/intents", {**first, "instruction": "跨项目"})[0] == 422
    assert request("GET", api + "/story?" + urlencode({**first, "session_id": "wrong"}))[0] == 422
    assert request("POST", api + "/story/start-first-chapter", {**first, "confirmed_version": 0, "confirmed_hash": "", "target_words": 4500, "tolerance_words": 300})[0] == 422
    assert not client.calls


def test_story_query_sources_require_project_session_and_step(story_api):
    registry, client, request = story_api
    scope, api = create(request)
    status, accepted = request("POST", api + "/story/intents", {**scope, "instruction": "Idea"})
    runtime = registry.get(scope["project_id"])["agent_runtime"]
    job = finish(runtime, runtime.get(accepted["job_id"]))
    query = {**scope, "job_id": job.job_id, "step": 1}
    status, snapshot = request("GET", api + "/story/sources?" + urlencode(query))
    assert status == 200 and snapshot["scope"] == "story" and snapshot["step"] == 1
    source = next(item for item in snapshot["sources"] if item["label"] == "本步故事候选与正式设定")
    assert source["usage"] == "included" and source["message_location"]["start"] >= 0
    assert request("GET", api + "/story/sources?" + urlencode({**query, "session_id": "wrong"}))[0] == 422
    assert request("GET", api + "/agent/jobs/" + job.job_id)[0] == 422
    assert request("GET", api + "/agent/jobs/" + job.job_id + "?" + urlencode(scope))[0] == 200


def test_default_project_route_reuses_single_runtime(tmp_path):
    from creative_os.agent_runtime import WriterAgentRuntime
    from creative_os.novel_project_command import NovelProjectCreator
    root = NovelProjectCreator(tmp_path).create("默认书", "Idea", operation_id="default")
    runtime = WriterAgentRuntime(root, client_factory=lambda: ScriptClient([]))
    registry = ProjectRegistry(tmp_path, client_factory=lambda: ScriptClient([]))
    server = create_server(EmptyWorkspace(None, root.name), agent_runtime=runtime, project_registry=registry, port=0)
    try:
        assert registry.get(root.name)["agent_runtime"] is runtime
        assert registry.get(root.name, writable=True)["agent_runtime"] is runtime
    finally:
        server.server_close(); registry.close()


def test_registry_restart_query_is_readonly_but_allows_explicit_recovery(tmp_path):
    from creative_os.novel_project_command import NovelProjectCreator
    root = NovelProjectCreator(tmp_path).create("恢复书", "Idea", operation_id="restart")
    registry = ProjectRegistry(tmp_path, client_factory=lambda: ScriptClient(["坏包"]))
    runtime = registry.get(root.name, writable=True)["agent_runtime"]
    job = finish(runtime, runtime.submit("Idea", None))
    runtime._set(job.job_id, status="thinking", retryable=False)
    registry.close()
    before = {str(path): (path.stat().st_mtime_ns, path.read_bytes()) for path in root.rglob("*") if path.is_file()}
    restored = ProjectRegistry(tmp_path, client_factory=lambda: ScriptClient([{"action": "finish_turn", "reply": "恢复成功"}]))
    try:
        readonly = restored.get(root.name)["agent_runtime"]
        visible = readonly.conversation(None)["jobs"][-1]
        assert visible["recovery_required"] and visible["observed_status"] == "thinking" and visible["retryable"]
        after = {str(path): (path.stat().st_mtime_ns, path.read_bytes()) for path in root.rglob("*") if path.is_file()}
        assert after == before
        writable = restored.get(root.name, writable=True)["agent_runtime"]
        retried = finish(writable, writable.retry(job.job_id, chapter_number=None, session_id=job.session_id))
        assert retried.status == "completed"
    finally:
        restored.close()
