"""书架处理HTTP边界：临时根、真实文件、无创作Runtime。"""

from http.client import HTTPConnection
import json
import re
from threading import Thread, Event
from urllib.parse import quote

import pytest

from creative_os.project_registry import ProjectRegistry
from creative_os.web_workspace import create_server, WriterWebAdapter
from creative_os.project_directory import validated_project
from test_story_http import EmptyWorkspace
from test_project_migration import seed, snapshot, start_request
from creative_os.project_migration_contract import request_data


def assert_only_lease_artifacts_changed(workspace, before):
    """拒绝证明允许原协议锁产物，项目数据、迁移意图和备份均不能变化。"""
    after = snapshot(workspace)
    parents = {"projects", "projects/.creative_os", "projects/.creative_os/project-write-locks"}
    def lease_path(path):
        return re.fullmatch(r"projects/\.creative_os/project-write-locks/(?:workspace|[0-9a-f]{64})\.lock", path)
    for name, value in before.items():
        path = name.replace("\\", "/")
        if path not in parents and not lease_path(path):
            assert after.get(name) == value
    for name, value in after.items():
        path = name.replace("\\", "/")
        if lease_path(path):
            assert value[1] == b""
        elif name not in before:
            assert path in parents


@pytest.fixture
def api(tmp_path, monkeypatch):
    projects, source, backup = seed(tmp_path)
    formal = source / "production/final_chapters"
    formal.mkdir(parents=True)
    (formal / "chapter_001.md").write_text("第1章\n原书正式稿", encoding="utf-8")
    registry = ProjectRegistry(projects)
    calls = []
    def get(project_id, *, writable=False):
        calls.append((project_id, writable))
        assert not writable, "本轮HTTP拒绝不得装配可写Runtime"
        root, _ = validated_project(projects, project_id)
        return {"writer_adapter": WriterWebAdapter(root, project_id), "agent_runtime": None}
    monkeypatch.setattr(registry, "get", get)
    server = create_server(EmptyWorkspace(None, "stable-book"), project_registry=registry,
                           writer_adapter=WriterWebAdapter(source, "stable-book"), port=0)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    def request(method, path, body=None, raw=False, content_type="application/json"):
        conn = HTTPConnection(*server.server_address, timeout=10)
        conn.request(method, path, body=body.encode("utf-8") if raw and isinstance(body, str) else body if raw else json.dumps(body) if body is not None else None,
                     headers={"Content-Type": content_type})
        res = conn.getresponse()
        text = res.read().decode("utf-8")
        data = json.loads(text)
        conn.close()
        return res.status, data
    yield request, source, server, registry, calls
    server.shutdown(); server.server_close(); worker.join(); registry.close()


def preview(api):
    status, data = api[0]("GET", "/api/projects/migration-preview?project_id=stable-book")
    assert status == 200
    return data


def test_global_issues_and_preview_get_are_readonly_and_no_runtime(api):
    request, source, server, registry, calls = api
    before = snapshot(source.parent.parent)
    status, issues = request("GET", "/api/projects/issues?limit=20&offset=0")
    assert status == 200
    assert any(item["code"] == "directory_name_mismatch" for item in issues["items"])
    data = preview(api)
    assert data["available"] and data["target_directory"] == "中文故事"
    for query in ("limit=0", "limit=101", "offset=-1", "limit=x", "offset=0&offset=1", "path=../outside"):
        assert request("GET", "/api/projects/issues?" + query)[0] == 400
    assert snapshot(source.parent.parent) == before
    assert calls == []


def test_only_global_strict_commands_are_allowed_without_activation(api):
    request, source, server, registry, calls = api
    data = preview(api)
    raw = request_data(start_request(data))
    before = snapshot(source.parent.parent)
    for bad in ({**raw, "actor": "其他人"},
                {**raw, "payload": {**raw["payload"], "confirmed": 1}},
                {**raw, "payload": {**raw["payload"], "source_directory": "../outside"}},
                {**raw, "target": {"project_id": "foreign"}},
                {**raw, "idempotency_key": "client-key"},
                {**raw, "payload": {**raw["payload"], "operation_id": "fake-id"}}):
        assert request("POST", "/api/commands/migrate-project-directory", bad)[0] in {400, 409, 422}
    assert request("POST", "/p/stable-book/api/commands/migrate-project-directory", raw)[0] == 422
    assert request("POST", "/api/commands/reconcile-project-directory", raw)[0] == 422
    assert request("POST", "/api/commands/migrate-project-directory", "bad-json", raw=True)[0] == 400
    assert request("POST", "/api/commands/migrate-project-directory", "{}", raw=True, content_type="text/plain")[0] == 415
    assert snapshot(source.parent.parent) == before
    assert calls == []


def test_expired_preview_invalid_status_and_continuation_are_readonly(api, monkeypatch):
    import creative_os.project_migration_preview as previews
    request, source, server, registry, calls = api
    data = preview(api)
    before = snapshot(source.parent.parent)
    assert request("GET", "/api/projects/migrations/fake-operation")[0] == 400
    assert request("GET", "/api/projects/migrations/" + data["operation_id"])[0] == 404
    assert request("POST", "/api/commands/migrate-project-directory", '{"actor":"作者","actor":"伪造"}', raw=True)[0] == 400
    assert request("POST", "/api/commands/migrate-project-directory", '{"payload":NaN}', raw=True)[0] == 400
    raw = request_data(start_request(data))
    continuation = {**raw, "command_id": "continue_project_directory",
                    "target": {"project_id": "stable-book", "operation_id": data["operation_id"]},
                    "payload": {"plan_fingerprint": data["plan_fingerprint"], "confirmed": True, "continuation_no": 0},
                    "idempotency_key": "directory-continue:" + data["operation_id"] + ":0"}
    assert request("POST", "/api/commands/continue-project-directory", continuation)[0] == 422
    now = previews.time.time()
    monkeypatch.setattr(previews.time, "time", lambda: now + 3600)
    assert request("POST", "/api/commands/migrate-project-directory", raw)[0] == 409
    assert_only_lease_artifacts_changed(source.parent.parent, before)
    assert calls == []


def test_success_default_old_root_is_blocked_and_scoped_reads_new_root(api):
    request, source, server, registry, calls = api
    data = preview(api)
    raw = request_data(start_request(data))
    status, result = request("POST", "/api/commands/migrate-project-directory", raw)
    assert status == 202 and result["status"] == "accepted", result
    assert not source.exists()
    assert request("GET", "/api/author-home")[0] == 503
    assert request("GET", "/api/writer/chapters/1")[0] == 503
    assert request("POST", "/api/commands/save-writer-draft", {})[0] == 409
    assert request("GET", "/p/stable-book/api/writer/chapters/1")[0] == 200
    assert all(not writable for _project_id, writable in calls)
    persisted = snapshot(source.parent.parent)
    assert request("POST", "/api/commands/migrate-project-directory", raw)[1] == result
    state = request("GET", "/api/projects/migrations/" + data["operation_id"])[1]
    assert state["stage"] == "verified" and state["reload_required"]
    assert state["plan_fingerprint"] == data["plan_fingerprint"]
    assert snapshot(source.parent.parent) == persisted


def test_active_book_data_is_rejected_before_registry_or_writable_takeover(api, monkeypatch):
    request, source, server, registry, calls = api
    data = preview(api)
    ready, release = Event(), Event()
    import creative_os.project_migration as migration
    def pause(point, _record):
        if point == "after_backing_up":
            ready.set()
            assert release.wait(10)
    monkeypatch.setattr(migration, "checkpoint", pause)
    result = []
    worker = Thread(target=lambda: result.append(request("POST", "/api/commands/migrate-project-directory", request_data(start_request(data)))))
    worker.start()
    try:
        assert ready.wait(5)
        for path in ("/api/story", "/api/agent/conversations/1", "/p/stable-book/api/author-home", "/p/stable-book/"):
            assert request("GET", path)[0] == 503
        assert request("POST", "/p/stable-book/api/commands/save-writer-draft", {})[0] == 409
        state = request("GET", "/api/projects/migrations/" + data["operation_id"])[1]
        assert state["stage"] == "backing_up"
        assert calls == []
    finally:
        release.set(); worker.join(10)
    assert result[0][0] == 202


def test_move_during_default_summary_read_does_not_send_false_zero_counts(api, monkeypatch):
    from creative_os.author_home_query import AuthorHomeQuery
    request, source, server, registry, calls = api
    data = preview(api)
    original = AuthorHomeQuery.read
    def move_during_read(query):
        result = server.RequestHandlerClass.migration_service.commands.execute(start_request(data))
        assert result.status == "accepted"
        return original(query)
    monkeypatch.setattr(AuthorHomeQuery, "read", move_during_read)
    status, payload = request("GET", "/api/author-home")
    assert status == 503
    assert payload["error"]["code"] == "project_directory_reload_required"


def test_scoped_read_bound_before_move_is_rejected_but_new_request_reads_new_root(api, monkeypatch):
    from creative_os.author_home_query import AuthorHomeQuery
    request, source, server, registry, calls = api
    data = preview(api)
    original = AuthorHomeQuery.read
    moved = False
    def move_during_read(query):
        nonlocal moved
        if not moved:
            moved = True
            result = server.RequestHandlerClass.migration_service.commands.execute(start_request(data))
            assert result.status == "accepted"
        return original(query)
    monkeypatch.setattr(AuthorHomeQuery, "read", move_during_read)
    status, payload = request("GET", "/p/stable-book/api/author-home")
    assert status == 503
    assert payload["error"]["code"] == "project_directory_reload_required"
    assert not source.exists()
    status, payload = request("GET", "/p/stable-book/api/author-home")
    assert status == 200 and payload["counts"]["formal"] == 1
    assert all(not writable for _project_id, writable in calls)


def test_stale_preview_response_proves_this_operation_was_not_started(api):
    request, source, server, registry, calls = api
    data = preview(api)
    (source / "chapter.md").write_text("临时正文发生变化", encoding="utf-8")
    before = snapshot(source.parent.parent)
    status, payload = request("POST", "/api/commands/migrate-project-directory", request_data(start_request(data)))
    assert status == 409
    assert payload["error"] == {"code": "preview_stale", "message": "预览已过期或作品内容已变化，请重新检查。",
                                "operation_id": data["operation_id"], "project_id": "stable-book", "operation_created": False}
    assert request("GET", "/api/projects/migrations/" + data["operation_id"])[0] == 404
    assert_only_lease_artifacts_changed(source.parent.parent, before)
    assert calls == []


def test_concurrent_identical_posts_replay_completed_operation_never_prove_absence(api, monkeypatch):
    request, source, server, registry, calls = api
    data = preview(api)
    raw = request_data(start_request(data))
    entered, release = Event(), Event()
    service = server.RequestHandlerClass.migration_service
    validate = service.previews.validate
    paused = False
    def pause_first_validation(*args):
        nonlocal paused
        if not paused:
            paused = True
            entered.set()
            assert release.wait(10)
        return validate(*args)
    monkeypatch.setattr(service.previews, "validate", pause_first_validation)
    first = []
    worker = Thread(target=lambda: first.append(request("POST", "/api/commands/migrate-project-directory", raw)))
    worker.start()
    try:
        assert entered.wait(5)
        second = request("POST", "/api/commands/migrate-project-directory", raw)
        assert second[0] == 202
        assert service.status(data["operation_id"])["stage"] == "verified"
    finally:
        release.set(); worker.join(10)
    assert (first[0][1].get("error") or {}).get("operation_created") is not False
    assert first[0] == second
    assert not source.exists()
    assert len(list(service.backup_root.glob("*/project"))) == 1
    assert calls == []


def test_stale_preview_with_external_lease_busy_never_proves_absence(api):
    from creative_os.project_write_gate import operation_migration_lease
    request, source, server, registry, calls = api
    data = preview(api)
    (source / "chapter.md").write_text("临时书变化", encoding="utf-8")
    entered, release = Event(), Event()
    def hold_lease():
        with operation_migration_lease(source.parent, "stable-book"):
            entered.set()
            assert release.wait(10)
    worker = Thread(target=hold_lease)
    worker.start()
    try:
        assert entered.wait(5)
        status, payload = request("POST", "/api/commands/migrate-project-directory", request_data(start_request(data)))
        assert status == 409
        assert payload["error"]["code"] == "project_migration_busy"
        assert "operation_created" not in payload["error"]
        assert server.RequestHandlerClass.migration_service.operations.read_operation(data["operation_id"]) is None
        assert calls == []
    finally:
        release.set(); worker.join(10)


def test_stale_preview_record_read_unknown_never_proves_absence(api, monkeypatch):
    request, source, server, registry, calls = api
    data = preview(api)
    (source / "chapter.md").write_text("临时书变化", encoding="utf-8")
    service = server.RequestHandlerClass.migration_service
    reads = 0
    def unavailable_after_first_read(_operation):
        nonlocal reads
        reads += 1
        if reads > 1:
            raise RuntimeError("临时模拟记录不可读")
        return None
    before = snapshot(source.parent.parent)
    with monkeypatch.context() as patch:
        patch.setattr(service.operations, "read_operation", unavailable_after_first_read)
        status, payload = request("POST", "/api/commands/migrate-project-directory", request_data(start_request(data)))
    assert status == 503
    assert payload["error"]["code"] == "migration_evidence_unavailable"
    assert "operation_created" not in payload["error"]
    assert service.operations.read_operation(data["operation_id"]) is None
    assert_only_lease_artifacts_changed(source.parent.parent, before)
    assert calls == []
