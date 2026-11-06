import json
from http.client import HTTPConnection
from threading import Thread

import pytest

from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.web_workspace import WorkspaceWebAdapter, create_server
from creative_os.workspace_query import WorkspaceQueryAdapter
from test_web_workspace import Reader
from test_agent_conversation import finish


@pytest.fixture
def api(tmp_path, monkeypatch):
    class FakeClient:
        def complete(self, messages, **kwargs):
            return "检查结果：保留开头，不要修改结尾。"

    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: FakeClient())
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    server = create_server(WorkspaceWebAdapter(WorkspaceQueryAdapter(Reader()), "p"), agent_runtime=runtime, port=0)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def request(method, path, payload=None):
        connection = HTTPConnection(*server.server_address, timeout=5)
        connection.request(method, path, body=json.dumps(payload) if payload is not None else None,
                           headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, json.loads(data)

    yield runtime, request
    server.shutdown()
    server.server_close()
    worker.join()
    runtime._pool.shutdown(wait=True)


def test_http_conversation_and_decision_keep_scope(api):
    runtime, request = api
    status, session = request("GET", "/api/agent/conversations/1?project_id=p")
    assert status == 200 and session["messages"] == []
    payload = {"project_id": "p", "chapter_number": 1, "session_id": session["session_id"], "instruction": "只分析这一章"}
    status, accepted = request("POST", "/api/agent/intents", payload)
    assert status == 202 and accepted["session_id"] == session["session_id"]
    job = finish(runtime, runtime.get(accepted["job_id"]))
    status, saved = request("GET", "/api/agent/conversations/1?project_id=p")
    assert len(saved["messages"]) == 2
    assert saved["jobs"][0]["job_id"] == job.job_id
    act = {**payload, "decision_id": job.decision_id}
    assert request("POST", "/api/agent/decisions/act", {**act, "chapter_number": 2})[0] == 422
    status, accepted = request("POST", "/api/agent/decisions/act", act)
    assert status == 202 and accepted["mode"] == "act"
    assert accepted["decision_id"] == job.decision_id
    assert finish(runtime, runtime.get(accepted["job_id"])).proposal_id
    assert runtime.store.current(1) is None


def test_http_rejects_wrong_project_chapter_and_request_shapes(api):
    runtime, request = api
    for payload in (
        {"project_id": "other", "chapter_number": 1, "instruction": "只分析"},
        {"project_id": "p", "chapter_number": True, "instruction": "只分析"},
        {"project_id": "p", "chapter_number": 0, "instruction": "只分析"},
        {"project_id": "p", "chapter_number": 1, "instruction": "只分析", "session_id": "wrong"},
        {"project_id": "p", "chapter_number": 1, "instruction": "只分析", "target_words": "4500"},
        {"project_id": "p", "chapter_number": 1, "instruction": "只分析", "mode": "unknown"},
        [],
    ):
        assert request("POST", "/api/agent/intents", payload)[0] == 422
    assert not runtime._jobs
    assert request("GET", "/api/agent/conversations/1?project_id=other")[0] == 422


def test_http_retry_keeps_original_failure_and_does_not_duplicate(api, monkeypatch):
    runtime, request = api
    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: (_ for _ in ()).throw(RuntimeError("测试故障原因")))
    failed = finish(runtime, runtime.submit("只分析", 1))
    status, job = request("GET", f"/api/agent/jobs/{failed.job_id}")
    assert job["error"] == "测试故障原因" and job["retryable"]
    payload = {"project_id": "p", "chapter_number": 1, "session_id": failed.session_id}
    status, retry = request("POST", f"/api/agent/jobs/{failed.job_id}/retry", payload)
    assert status == 202
    status, duplicate = request("POST", f"/api/agent/jobs/{failed.job_id}/retry", payload)
    assert retry["job_id"] == duplicate["job_id"]
    assert request("POST", f"/api/agent/jobs/{failed.job_id}/retry", {**payload, "chapter_number": 2})[0] == 422


def test_http_questions_default_readonly_and_explicit_mode_authorizes_act(api):
    runtime, request = api
    for instruction in ["为什么这样写？", "继续解释一下原因", "为什么建议修改结尾？"]:
        status, accepted = request("POST", "/api/agent/intents", {"project_id": "p", "chapter_number": 1, "instruction": instruction})
        assert status == 202 and accepted["mode"] == "analyze"
        assert finish(runtime, runtime.get(accepted["job_id"])).draft_version is None
    assert runtime.store.current(1) is None
    status, accepted = request("POST", "/api/agent/intents", {"project_id": "p", "chapter_number": 1, "instruction": "继续写这一章", "mode": "act"})
    assert status == 202 and accepted["mode"] == "act"
    assert finish(runtime, runtime.get(accepted["job_id"])).proposal_id
    assert runtime.store.current(1) is None


def test_http_frozen_proposal_read_review_scope_and_idempotency(api):
    runtime, request = api
    runtime.store.save(1, "当前工作稿", actor="作者")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    query = f"project_id=p&chapter_number=1&session_id={job.session_id}"
    path = f"/api/agent/proposals/{job.proposal_id}?{query}"
    status, proposal = request("GET", path)
    assert status == 200 and proposal["base"]["content"] == "当前工作稿"
    assert "当前工作稿" in proposal["diff"]
    assert request("GET", path.replace("chapter_number=1", "chapter_number=2"))[0] == 422
    payload = {"command_id": "review_writer_proposal", "request_id": "http-review", "actor": "作者",
               "target": {"project_id": "p", "chapter_number": 1, "session_id": job.session_id,
                          "proposal_id": job.proposal_id}, "payload": {"action": "accept", "reason": "采用"},
               "expected_version": None, "idempotency_key": "http-review"}
    status, result = request("POST", "/api/commands/review-writer-proposal", payload)
    assert status == 202 and result["status"] == "accepted"
    assert request("POST", "/api/commands/review-writer-proposal", payload)[1] == result
    assert len(runtime.store.versions(1)) == 2
    status, session = request("GET", "/api/agent/conversations/1?project_id=p")
    assert session["proposals"][0]["status"] == "accepted"
    wrong = {**payload, "request_id": "wrong", "idempotency_key": "wrong",
             "target": {**payload["target"], "chapter_number": 2}}
    status, result = request("POST", "/api/commands/review-writer-proposal", wrong)
    assert status != 202 and result["error"]["code"] == "proposal_scope_mismatch"
