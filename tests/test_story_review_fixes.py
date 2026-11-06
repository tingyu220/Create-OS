"""独立复审的四类反例；仅在临时项目验证拒绝、只读及恢复边界。"""

from http.client import HTTPConnection
import json
from threading import Thread
from urllib.parse import quote

import pytest
from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.novel_project_command import NovelProjectCreator
from creative_os.project_registry import ProjectRegistry
from creative_os.web_workspace import create_server
from test_story_http import EmptyWorkspace, command
from test_story_agent import ScriptClient
from test_agent_conversation import finish
from creative_os.story_architecture_store import content_hash


def files(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


def interrupted_project(tmp_path, monkeypatch, *, status="queued"):
    root = NovelProjectCreator(tmp_path).create("book-b", "Idea", operation_id="create", story_mode=False)
    runtime = WriterAgentRuntime(root, client_factory=lambda: ScriptClient([]))
    monkeypatch.setattr(runtime._pool, "submit", lambda *args: None)
    job = runtime.submit("原中断章节任务", 1)
    if status != "queued":
        runtime._set(job.job_id, status=status)
    runtime._pool.shutdown()
    return root, job


@pytest.mark.parametrize("case", ["foreign_story", "invalid_instruction", "invalid_budget", "foreign_command", "invalid_command", "invalid_proposal_action", "unknown_retry", "missing_chapter_session"])
def test_rejected_routed_post_has_no_recovery_or_file_write(tmp_path, monkeypatch, case):
    root, job = interrupted_project(tmp_path, monkeypatch)
    registry = ProjectRegistry(tmp_path, client_factory=lambda: ScriptClient([]))
    scope = {"project_id": root.name, "scope": "story", "session_id": "story-" + content_hash({"project_id": root.name})[:32]}
    original_get, accesses = registry.get, []
    def get(project_id, *, writable=False):
        accesses.append(writable)
        return original_get(project_id, writable=writable)
    monkeypatch.setattr(registry, "get", get)
    if case == "foreign_story":
        route, body = "/story/intents", {"project_id": "foreign", "scope": "story", "session_id": "foreign", "instruction": "被拒绝"}
    elif case == "invalid_instruction":
        route, body = "/story/intents", {**scope, "instruction": []}
    elif case == "invalid_budget":
        route, body = "/story/start-first-chapter", {**scope, "confirmed_version": 0, "confirmed_hash": "", "target_words": "bad", "tolerance_words": 300}
    elif case == "foreign_command":
        route = "/commands/save-writer-draft"
        body = command("save_writer_draft", {"project_id": "foreign", "chapter_number": 1}, {"content": "拒绝"}, "bad")
    elif case == "invalid_command":
        route = "/commands/edit-story-candidate"
        body = command("edit_story_candidate", scope, {"blocks": [], "open_questions": [], "expected_revision": "bad"}, "bad")
    elif case == "invalid_proposal_action":
        route = "/commands/review-writer-proposal"
        target = {"project_id": root.name, "chapter_number": 1, "session_id": job.session_id, "proposal_id": "proposal-" + "f" * 32}
        body = command("review_writer_proposal", target, {"action": {}}, "bad")
    elif case == "unknown_retry":
        route, body = f"/agent/jobs/{job.job_id}/retry", {"project_id": root.name, "chapter_number": 1, "session_id": "foreign"}
    else:
        route, body = "/agent/intents", {"project_id": root.name, "chapter_number": 2, "instruction": "缺少会话"}
    server = create_server(EmptyWorkspace(None, "none"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True); worker.start()
    before = files(root)
    try:
        connection = HTTPConnection(*server.server_address, timeout=5)
        connection.request("POST", "/p/" + quote(root.name) + "/api" + route, body=json.dumps(body), headers={"Content-Type": "application/json"})
        response = connection.getresponse(); response.read(); connection.close()
        assert response.status in {400, 422}
        assert files(root) == before
        assert not any(accesses)  # 参数/作用域拒绝前连可写装配都不能发生。
        assert registry.get(root.name)["agent_runtime"].read_only
    finally:
        server.shutdown(); server.server_close(); worker.join(); registry.close()


@pytest.mark.parametrize("feedback_exists", [False, True])
def test_chapter_query_preserves_all_files_and_feedback_mtime(tmp_path, monkeypatch, feedback_exists):
    root, job = interrupted_project(tmp_path, monkeypatch)
    if feedback_exists:
        path = root / ".creative_os/runtime/feedback.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text("", encoding="utf-8")
    readonly = WriterAgentRuntime(root, read_only=True, client_factory=lambda: ScriptClient([]))
    before = files(root)
    try:
        session = readonly.conversation(1)
        assert session["lesson_review"]["feedback"] == []
        assert files(root) == before
    finally:
        readonly._pool.shutdown()


@pytest.mark.parametrize("status,retryable", [("queued", True), ("thinking", True), ("saving", False)])
def test_chapter_restart_projection_and_explicit_retry_keep_frozen_context(tmp_path, monkeypatch, status, retryable):
    root, original = interrupted_project(tmp_path, monkeypatch, status=status)
    from creative_os.agent_conversation_store import AgentConversationStore
    store = AgentConversationStore(root, root.name)
    session = store.read(1)
    frozen = {"text": "冻结设定正文", "version": 7, "hash": "frozen-hash", "project_id": root.name, "source_ref": "story-confirmed:frozen"}
    session["jobs"][original.job_id]["story_context"] = frozen
    store.write(session)
    client = ScriptClient(["恢复后分析"])
    registry = ProjectRegistry(tmp_path, client_factory=lambda: client)
    try:
        readonly = registry.get(root.name)["agent_runtime"]
        before = files(root)
        projected = readonly.conversation(1)["jobs"][0]
        assert projected["status"] == "failed" and projected["recovery_required"]
        assert projected["retryable"] is retryable
        assert files(root) == before
        writable = registry.get(root.name, writable=True)["agent_runtime"]
        assert files(root) == before  # 仅装配不得恢复任何任务。
        if not retryable:
            with pytest.raises(ValueError, match="job_not_retryable"):
                writable.retry(original.job_id, chapter_number=1, session_id=original.session_id)
            assert files(root) == before
        else:
            retried = finish(writable, writable.retry(original.job_id, chapter_number=1, session_id=original.session_id))
            assert retried.status == "completed" and retried.story_context == frozen
            assert "冻结设定正文" in "\n".join(message.content for message in client.calls[0])
    finally:
        registry.close()


@pytest.mark.parametrize("tamper", [None, "foreign_content", "replaced_directory", "replaced_empty_directory", "missing_checkpoint"])
def test_marker_window_recovers_same_owner_and_refuses_foreign_content(tmp_path, monkeypatch, tamper):
    import creative_os.novel_project_command as module
    original = module.atomic_json
    def interrupt(path, payload):
        if path.name == "creation.json":
            path.parent.mkdir(parents=True, exist_ok=True)
            raise RuntimeError("marker_atomic_write_interrupted")
        return original(path, payload)
    monkeypatch.setattr(module, "atomic_json", interrupt)
    creator = NovelProjectCreator(tmp_path)
    with pytest.raises(RuntimeError, match="marker_atomic_write_interrupted"):
        creator.create("marker-window", "Idea", operation_id="same")
    monkeypatch.setattr(module, "atomic_json", original)
    partial = tmp_path / "marker-window"
    if tamper == "foreign_content":
        (partial / "author-notes.txt").write_text("作者内容不得认领", encoding="utf-8")
    elif tamper in {"replaced_directory", "replaced_empty_directory"}:
        backup = tmp_path / "marker-window-backup"
        partial.rename(backup)
        if tamper == "replaced_directory":
            (partial / ".creative_os").mkdir(parents=True)
        else:
            partial.mkdir()
    elif tamper == "missing_checkpoint":
        records = json.loads(creator.path.read_text(encoding="utf-8"))
        records["same"].pop("directory_identity")
        original(creator.path, records)
    if tamper:
        before = files(partial)
        with pytest.raises(ValueError, match="project_creation_owner_conflict"):
            creator.create("marker-window", "Idea", operation_id="same")
        assert files(partial) == before
        return
    result = creator.create("marker-window", "Idea", operation_id="same")
    assert (result / "project.json").is_file()


def test_http_chapter_recovery_only_takes_requested_job(tmp_path, monkeypatch):
    from dataclasses import asdict, replace
    from creative_os.agent_conversation_store import AgentConversationStore
    from urllib.parse import urlencode
    root, original = interrupted_project(tmp_path, monkeypatch)
    store = AgentConversationStore(root, root.name)
    second = store.read(2)
    other = replace(original, job_id="agent-" + "f" * 32, chapter_number=2, session_id=second["session_id"])
    second["jobs"][other.job_id] = asdict(other)
    store.write(second)
    other_path = store._path(2)
    untouched = (other_path.read_bytes(), other_path.stat().st_mtime_ns)
    client = ScriptClient(["恢复章节分析完成"])
    registry = ProjectRegistry(tmp_path, client_factory=lambda: client)
    server = create_server(EmptyWorkspace(None, "none"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True); worker.start()
    def request(method, path, body=None):
        connection = HTTPConnection(*server.server_address, timeout=5)
        connection.request(method, "/p/" + quote(root.name) + path, body=json.dumps(body) if body else None, headers={"Content-Type": "application/json"})
        response = connection.getresponse(); value = json.loads(response.read()); connection.close()
        return response.status, value
    before = files(root)
    try:
        status, view = request("GET", f"/api/agent/conversations/1?project_id={root.name}")
        assert status == 200 and view["jobs"][0]["status"] == "failed" and view["jobs"][0]["retryable"]
        scope = {"project_id": root.name, "chapter_number": 1, "session_id": original.session_id}
        status, job_view = request("GET", f"/api/agent/jobs/{original.job_id}?" + urlencode(scope))
        assert status == 200 and job_view["recovery_required"] and job_view["observed_status"] == "queued"
        assert files(root) == before and not client.calls
        status, accepted = request("POST", f"/api/agent/jobs/{original.job_id}/retry", scope)
        assert status == 202, accepted
        runtime = registry.get(root.name)["agent_runtime"]
        assert finish(runtime, runtime.get(accepted["job_id"])).status == "completed"
        assert (other_path.read_bytes(), other_path.stat().st_mtime_ns) == untouched
        assert runtime.get(other.job_id).status == "queued"
        assert runtime.conversation(2)["jobs"][0]["retryable"]
    finally:
        server.shutdown(); server.server_close(); worker.join(); registry.close()
