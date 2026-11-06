"""来源 Query 的真实 HTTP 边界。"""

from urllib.parse import urlencode

from test_agent_conversation_http import api
from test_agent_conversation import finish


def test_http_source_index_and_detail_require_full_scope(api):
    runtime, request = api
    job = finish(runtime, runtime.submit("分析本章", 1))
    scope = dict(project_id="p", chapter_number=1, session_id=job.session_id)
    path = f"/api/agent/jobs/{job.job_id}/context-sources"
    status, index = request("GET", f"{path}?{urlencode(scope)}")
    assert status == 200 and index["job_id"] == job.job_id
    assert index["sources"] and all("content_snapshot" not in source for source in index["sources"])
    selected = index["sources"][-1]["source_id"]
    status, detail = request("GET", f"{path}?{urlencode(scope | {'source_id': selected})}")
    assert status == 200 and detail["source"]["source_id"] == selected
    assert "分析本章" in detail["source"]["content_snapshot"]
    assert "context_snapshot" not in request("GET", f"/api/agent/jobs/{job.job_id}")[1]
    assert "context_snapshot" not in request("GET", "/api/agent/conversations/1?project_id=p")[1]["jobs"][0]
    for invalid in [scope | {"project_id": "q"}, scope | {"chapter_number": 2},
                    scope | {"session_id": "other"}, {"project_id": "p"},
                    scope | {"path": "../../secret"}, scope | {"source_id": "../../secret"},
                    scope | {"source_id": "/etc/passwd"}, scope | {"source_id": "C:\\secret"},
                    scope | {"source_id": "source-9999"}, scope | {"source_id": ""}]:
        assert request("GET", f"{path}?{urlencode(invalid)}")[0] == 422
    assert request("GET", f"{path}?{urlencode(scope)}&project_id=q")[0] == 422
    unknown = path.replace(job.job_id, "agent-" + "0" * 32)
    assert request("GET", f"{unknown}?{urlencode(scope)}")[0] == 422
    other_job = finish(runtime, runtime.submit("别章", 2))
    assert request("GET", f"{path.replace(job.job_id, other_job.job_id)}?{urlencode(scope)}")[0] == 422


def test_http_legacy_reports_unavailable(api):
    runtime, request = api
    job = finish(runtime, runtime.submit("分析本章", 1))
    runtime._set(job.job_id, context_snapshot=None)
    path = f"/api/agent/jobs/{job.job_id}/context-sources?" + urlencode(dict(project_id="p", chapter_number=1, session_id=job.session_id))
    status, data = request("GET", path)
    assert status == 200 and data["delivery"] == "unavailable"
    assert data["sources"][0]["usage"] == "unavailable"
    assert runtime.store.current(1) is None
