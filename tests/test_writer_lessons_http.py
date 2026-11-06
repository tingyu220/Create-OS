"""复用真实 HTTP 服务验证经验 Query/Command 分层与作用域。"""

from test_agent_conversation_http import api
from test_agent_proposal import finish, review


def test_http_lesson_creation_review_and_refresh(api):
    runtime, request = api
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    assert review(runtime, job, "reject", "缺少动作支撑").status == "accepted"
    status, session = request("GET", "/api/agent/conversations/1?project_id=p")
    feedback = session["lesson_review"]["feedback"][0]
    command = {"command_id": "manage_writer_lesson", "request_id": "create", "actor": "作者",
               "target": {"project_id": "p", "chapter_number": 1, "session_id": job.session_id, "feedback_id": feedback["id"]},
               "payload": {"action": "create", "title": "动机", "content": "通过动作体现动机", "range": "chapter"},
               "expected_version": None, "idempotency_key": "create"}
    status, result = request("POST", "/api/commands/manage-writer-lesson", command)
    assert status == 202 and result["status"] == "accepted"
    assert request("POST", "/api/commands/manage-writer-lesson", command)[1] == result
    status, session = request("GET", "/api/agent/conversations/1?project_id=p")
    item, = session["lesson_review"]["lessons"]
    assert item["status"] == "candidate" and item["detail"]["feedback"] == feedback
    assert item["detail"]["base"]["hash"] and item["detail"]["result"]["hash"]
    approve = {**command, "request_id": "approve", "idempotency_key": "approve",
               "payload": {"action": "approve", "memory_id": item["id"], "version": item["version"], "note": "确认本章适用"}}
    assert request("POST", "/api/commands/manage-writer-lesson", {**approve, "actor": "system"})[0] == 422
    assert request("POST", "/api/commands/manage-writer-lesson", {**approve, "target": {**command["target"], "chapter_number": 2}})[0] == 422
    assert request("POST", "/api/commands/manage-writer-lesson", approve)[0] == 202
    restored = request("GET", "/api/agent/conversations/1?project_id=p")[1]
    assert restored["lesson_review"]["lessons"][0]["status"] == "active"
    assert request("GET", "/api/agent/conversations/2?project_id=p")[1]["lesson_review"]["lessons"] == []
    assert request("GET", "/api/agent/conversations/1?project_id=other")[0] == 422
    assert runtime.store.versions(1) == ()
