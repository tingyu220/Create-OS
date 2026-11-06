"""registry 重启后的审阅事务核对；真实出口由测试入口默认拦截。"""

from copy import deepcopy
from contextlib import contextmanager
from http.client import HTTPConnection
import json
from threading import Thread
from urllib.parse import quote, urlencode

import pytest
from creative_os.memory.feedback import FeedbackStore
from creative_os.novel_project_command import NovelProjectCreator
from creative_os.project_registry import ProjectRegistry
from creative_os.web_workspace import create_server
from creative_os.workspace_command import FileCommandResultStore
from test_agent_conversation import finish
from test_story_agent import ScriptClient
from test_story_http import EmptyWorkspace, command


def files(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns) for path in root.rglob("*") if path.is_file()}


@contextmanager
def api_for(root, client):
    registry = ProjectRegistry(root.parent, client_factory=lambda: client)
    server = create_server(EmptyWorkspace(None, "none"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True); worker.start()
    def request(method, path, body=None):
        connection = HTTPConnection(*server.server_address, timeout=5)
        connection.request(method, "/p/" + quote(root.name) + "/api" + path, body=json.dumps(body) if body else None, headers={"Content-Type": "application/json"})
        response = connection.getresponse(); value = json.loads(response.read()); connection.close()
        return response.status, value
    try:
        yield registry, request
    finally:
        server.shutdown(); server.server_close(); worker.join(); registry.close()


@pytest.fixture
def interrupted_review(tmp_path, monkeypatch, request):
    client = ScriptClient(["候选原文", "修订候选"])
    root = NovelProjectCreator(tmp_path).create("review-book", "Idea", operation_id="create", story_mode=False)
    registry = ProjectRegistry(tmp_path, client_factory=lambda: client)
    runtime = registry.get(root.name, writable=True)["agent_runtime"]
    if getattr(request, "param", False):
        runtime.store.save(1, "候选原文", actor="作者")
    job = finish(runtime, runtime.submit("写一章", 1, mode="act"))
    target = {"project_id": root.name, "chapter_number": 1, "session_id": job.session_id, "proposal_id": job.proposal_id}
    accept = command("review_writer_proposal", target, {"action": "accept", "reason": "采用"}, "accept-one")

    def interrupt(window, *, action="accept"):
        if action != "accept":
            accept["payload"] = {"action": action, "reason": "原审阅决定", **({"source": "candidate"} if action == "revise" else {})}
        original_save, original_write = runtime.store.save, runtime.proposals.write
        original_feedback, original_complete = FeedbackStore.append_once, FileCommandResultStore.complete
        with monkeypatch.context() as fault:
            def save(*args, **kwargs):
                if window == "before_draft":
                    raise OSError("before_draft")
                result = original_save(*args, **kwargs)
                if window == "after_draft":
                    raise OSError("after_draft")
                return result
            def write(proposal):
                original_write(proposal)
                if window == "after_draft_receipt" and proposal["status"] == "reviewing" and proposal["review"].get("draft_version"):
                    raise OSError("after_draft_receipt")
                if window == "after_proposal" and proposal["status"] == "accepted":
                    raise OSError("after_proposal")
            def feedback(store, record):
                if window == "before_feedback":
                    raise OSError("before_feedback")
                original_feedback(store, record)
                if window == "after_feedback":
                    raise OSError("after_feedback")
            def complete(store, key, fingerprint, result):
                if window == "before_command_receipt" and key == "accept-one":
                    raise OSError("before_command_receipt")
                return original_complete(store, key, fingerprint, result)
            fault.setattr(runtime.store, "save", save)
            fault.setattr(runtime.proposals, "write", write)
            fault.setattr(FeedbackStore, "append_once", feedback)
            fault.setattr(FileCommandResultStore, "complete", complete)
            from creative_os.web_command_dto import decode_web_command
            result = runtime.proposal_commands.execute(decode_web_command(accept))
            assert result.error.code == "command_outcome_unknown"
        assert runtime.proposal_commands._store.read("accept-one").state.value == "reserved"
        registry.close()
        return root, client, job, target, accept
    yield interrupt
    registry.close()


@pytest.mark.parametrize("window", ["before_draft", "after_draft", "after_draft_receipt", "before_feedback", "after_feedback", "after_proposal", "before_command_receipt"])
@pytest.mark.parametrize("later_edit", [False, True])
def test_registry_explicit_reconcile_preserves_original_transaction(interrupted_review, window, later_edit):
    root, client, job, target, accept = interrupted_review(window)
    from creative_os.writer_draft_store import WriterDraftStore
    drafts = WriterDraftStore(root)
    if later_edit:
        current = drafts.current(1)
        drafts.save(1, "随后人工改稿", actor="作者", expected_version=current[0].version if current else None)
    before_version_count = len(drafts.versions(1))
    registry = ProjectRegistry(root.parent, client_factory=lambda: client)
    server = create_server(EmptyWorkspace(None, "none"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True); worker.start()
    api = "/p/" + quote(root.name) + "/api"
    def request(method, path, body=None):
        connection = HTTPConnection(*server.server_address, timeout=5)
        connection.request(method, api + path, body=json.dumps(body) if body else None, headers={"Content-Type": "application/json"})
        response = connection.getresponse(); value = json.loads(response.read()); connection.close()
        return response.status, value
    try:
        before = files(root)
        status, session = request("GET", "/agent/conversations/1?project_id=" + root.name)
        assert status == 200
        recovery = session["proposals"][0]["review_recovery"]
        assert recovery["required"] and recovery["actor"] == "作者"
        query = urlencode({key: target[key] for key in ("project_id", "chapter_number", "session_id")})
        assert request("GET", f"/agent/proposals/{job.proposal_id}?{query}")[1]["review_recovery"] == recovery
        assert files(root) == before and len(client.calls) == 1
        reconcile = command("reconcile_writer_proposal", target, recovery["payload"], "reconcile-one")
        status, result = request("POST", "/commands/reconcile-writer-proposal", reconcile)
        conflict = later_edit and window == "before_draft"
        assert status == (422 if conflict else 202), result
        assert request("POST", "/commands/reconcile-writer-proposal", reconcile)[1] == result
        again = {**reconcile, "request_id": "reconcile-two", "idempotency_key": "reconcile-two"}
        assert request("POST", "/commands/reconcile-writer-proposal", again)[0] == status
        old = request("POST", "/commands/review-writer-proposal", accept)[1]
        assert old["status"] == ("rejected" if conflict else "accepted")
        if not conflict:
            new_review = {**accept, "request_id": "accept-two", "idempotency_key": "accept-two"}
            assert request("POST", "/commands/review-writer-proposal", new_review)[0] == 202
        assert drafts.current(1)[1] == ("随后人工改稿" if later_edit else "候选原文")
        assert len(drafts.versions(1)) == max(1, before_version_count)
        assert len(FeedbackStore(root, initialize=False).list()) == (0 if conflict else 1)
        assert FileCommandResultStore(root).read("accept-one").state.value == "completed"
        assert len(client.calls) == 1
        assert not request("GET", "/agent/conversations/1?project_id=" + root.name)[1]["proposals"][0].get("review_recovery", {}).get("required")
    finally:
        server.shutdown(); server.server_close(); worker.join(); registry.close()


@pytest.mark.parametrize("bad", ["project_id", "chapter_number", "session_id", "proposal_id", "actor", "feedback_id", "review_hash", "extra_action"])
def test_reconcile_rejects_wrong_original_identity_without_writes(interrupted_review, bad):
    root, client, job, target, accept = interrupted_review("after_feedback")
    with api_for(root, client) as (registry, request):
        recovery = request("GET", "/agent/conversations/1?project_id=" + root.name)[1]["proposals"][0]["review_recovery"]
        body = command("reconcile_writer_proposal", deepcopy(target), deepcopy(recovery["payload"]), "reconcile")
        if bad in target:
            body["target"][bad] = 2 if bad == "chapter_number" else "foreign"
        elif bad == "actor":
            body["actor"] = "其他作者"
        elif bad == "extra_action":
            body["payload"]["action"] = "reject"
        else:
            body["payload"][bad] = "foreign"
        before = files(root)
        assert request("POST", "/commands/reconcile-writer-proposal", body)[0] in {400, 422}
        assert files(root) == before
        assert registry.get(root.name)["agent_runtime"].read_only
        assert len(client.calls) == 1


@pytest.mark.parametrize("window", ["reconcile_intent", "original_receipt", "reconcile_receipt"])
def test_reconcile_itself_can_resume_original_and_new_receipts(interrupted_review, monkeypatch, window):
    root, client, job, target, accept = interrupted_review("after_feedback")
    with api_for(root, client) as (registry, request):
        recovery = request("GET", "/agent/conversations/1?project_id=" + root.name)[1]["proposals"][0]["review_recovery"]
        body = command("reconcile_writer_proposal", target, recovery["payload"], "reconcile-one")
        with monkeypatch.context() as fault:
            original_complete = FileCommandResultStore.complete
            from creative_os.agent_proposal_store import AgentProposalStore
            original_write = AgentProposalStore.write
            def write(store, proposal):
                original_write(store, proposal)
                if window == "reconcile_intent" and any(row.get("command_id") == "reconcile_writer_proposal" for row in (proposal.get("review") or {}).get("commands", [])):
                    raise OSError("reconcile_intent_interrupted")
            def complete(store, key, fingerprint, result):
                if (window == "original_receipt" and key == "accept-one") or (window == "reconcile_receipt" and key == "reconcile-one"):
                    raise OSError("receipt_interrupted")
                return original_complete(store, key, fingerprint, result)
            fault.setattr(AgentProposalStore, "write", write)
            fault.setattr(FileCommandResultStore, "complete", complete)
            assert request("POST", "/commands/reconcile-writer-proposal", body)[1]["error"]["code"] == "command_outcome_unknown"
    with api_for(root, client) as (registry, request):
        before = files(root)
        assert request("GET", "/agent/conversations/1?project_id=" + root.name)[1]["proposals"][0]["review_recovery"]["required"]
        assert files(root) == before
        assert request("POST", "/commands/reconcile-writer-proposal", body)[0] == 202
        results = FileCommandResultStore(root)
        assert results.read("accept-one").state.value == "completed"
        assert results.read("reconcile-one").state.value == "completed"
        runtime = registry.get(root.name)["agent_runtime"]
        assert len(runtime.store.versions(1)) == 1 and len(FeedbackStore(root, initialize=False).list()) == 1
        assert len(client.calls) == 1


def test_reconcile_does_not_recover_unrelated_chapter(interrupted_review):
    from dataclasses import replace, asdict
    from creative_os.agent_conversation_store import AgentConversationStore
    root, client, job, target, accept = interrupted_review("after_feedback")
    store = AgentConversationStore(root, root.name)
    session = store.read(2)
    other = replace(job, job_id="agent-" + "f" * 32, chapter_number=2, session_id=session["session_id"], status="queued", proposal_id=None)
    session["jobs"][other.job_id] = asdict(other); store.write(session)
    path = store._path(2); before = (path.read_bytes(), path.stat().st_mtime_ns)
    with api_for(root, client) as (registry, request):
        recovery = request("GET", "/agent/conversations/1?project_id=" + root.name)[1]["proposals"][0]["review_recovery"]
        body = command("reconcile_writer_proposal", target, recovery["payload"], "reconcile")
        assert request("POST", "/commands/reconcile-writer-proposal", body)[0] == 202
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
        assert registry.get(root.name)["agent_runtime"].get(other.job_id).status == "queued"


@pytest.mark.parametrize("interrupted_review", [True], indirect=True)
@pytest.mark.parametrize("window", ["after_draft", "before_feedback"])
def test_unchanged_acceptance_requires_durable_receipt_before_later_edit(interrupted_review, window):
    from creative_os.writer_draft_store import WriterDraftStore
    root, client, job, target, accept = interrupted_review(window)
    drafts = WriterDraftStore(root)
    assert drafts.saved_operation(1, job.proposal_id) is None
    drafts.save(1, "后续人工稿", actor="作者", expected_version=1)
    with api_for(root, client) as (registry, request):
        recovery = request("GET", "/agent/conversations/1?project_id=" + root.name)[1]["proposals"][0]["review_recovery"]
        body = command("reconcile_writer_proposal", target, recovery["payload"], "reconcile")
        assert request("POST", "/commands/reconcile-writer-proposal", body)[0] == (422 if window == "after_draft" else 202)
        assert drafts.current(1)[1] == "后续人工稿" and len(drafts.versions(1)) == 2
        assert len(FeedbackStore(root, initialize=False).list()) == (0 if window == "after_draft" else 1)


@pytest.mark.parametrize("action", ["reject", "cancel", "revise"])
def test_reconcile_reuses_original_nonaccept_effect_identifiers(interrupted_review, action):
    root, client, job, target, accept = interrupted_review("after_feedback", action=action)
    with api_for(root, client) as (registry, request):
        runtime = registry.get(root.name)["agent_runtime"]
        original = runtime.proposals.read(job.proposal_id)["review"]
        before_calls = len(client.calls)
        recovery = request("GET", "/agent/conversations/1?project_id=" + root.name)[1]["proposals"][0]["review_recovery"]
        body = command("reconcile_writer_proposal", target, recovery["payload"], "reconcile")
        assert request("POST", "/commands/reconcile-writer-proposal", body)[0] == 202
        active = registry.get(root.name)["agent_runtime"]
        final = active.proposals.read(job.proposal_id)["review"]
        assert final["identity"] == original["identity"] and final["actor"] == original["actor"]
        assert final["job_id"] == original["job_id"] and final["feedback"] == original["feedback"]
        assert len(FeedbackStore(root, initialize=False).list()) == 1
        assert len(client.calls) == before_calls
        assert len(active._jobs) == (2 if action == "revise" else 1)


def test_lesson_operation_registry_replay_still_finishes_own_receipt(interrupted_review, monkeypatch):
    from creative_os.writer_lesson_command import WriterLessonCommandHandler
    root, client, job, target, accept = interrupted_review("after_feedback")
    with api_for(root, client) as (registry, request):
        recovery = request("GET", "/agent/conversations/1?project_id=" + root.name)[1]["proposals"][0]["review_recovery"]
        assert request("POST", "/commands/reconcile-writer-proposal", command("reconcile_writer_proposal", target, recovery["payload"], "reconcile"))[0] == 202
        lesson_target = {key: target[key] for key in ("project_id", "chapter_number", "session_id")} | {"feedback_id": recovery["payload"]["feedback_id"]}
        lesson = command("manage_writer_lesson", lesson_target, {"action": "create", "title": "经验", "content": "使用动作呈现犹豫", "range": "chapter"}, "lesson-one")
        original_write = WriterLessonCommandHandler._write
        def write(path, value):
            original_write(path, value)
            if value["done"]:
                raise OSError("lesson_receipt_window")
        with monkeypatch.context() as fault:
            fault.setattr(WriterLessonCommandHandler, "_write", staticmethod(write))
            assert request("POST", "/commands/manage-writer-lesson", lesson)[1]["error"]["code"] == "command_outcome_unknown"
    with api_for(root, client) as (registry, request):
        before = files(root)
        session = request("GET", "/agent/conversations/1?project_id=" + root.name)[1]
        assert len(session["lesson_review"]["lessons"]) == 1 and files(root) == before
        assert request("POST", "/commands/manage-writer-lesson", lesson)[0] == 202
        assert FileCommandResultStore(root).read("lesson-one").state.value == "completed"
        assert len(registry.get(root.name)["agent_runtime"].lesson_query(1)["lessons"]) == 1


def test_story_confirmation_registry_replay_uses_atomic_receipt_only(interrupted_review, monkeypatch):
    root, client, job, target, accept = interrupted_review("after_feedback")
    with api_for(root, client) as (registry, request):
        runtime = registry.get(root.name)["agent_runtime"]
        store = runtime.story
        candidate = store.propose(store.session_id, [{"key": "core", "title": "核心", "text": "正式设定"}], [], expected_revision=0, actor="作者", operation_id="candidate")
        story_target = {"project_id": root.name, "scope": "story", "session_id": store.session_id}
        confirm = command("confirm_story_candidate", story_target, {"revision": 1, "hash": candidate["hash"], "expected_confirmed_version": 0}, "story-confirm")
        original_complete = FileCommandResultStore.complete
        def complete(store, key, fingerprint, result):
            if key == "story-confirm":
                raise OSError("story_receipt_window")
            return original_complete(store, key, fingerprint, result)
        with monkeypatch.context() as fault:
            fault.setattr(FileCommandResultStore, "complete", complete)
            assert request("POST", "/commands/confirm-story-candidate", confirm)[1]["error"]["code"] == "command_outcome_unknown"
    with api_for(root, client) as (registry, request):
        before = files(root)
        view = request("GET", "/story?" + urlencode(story_target))[1]
        assert view["confirmed"]["version"] == 1 and files(root) == before
        assert request("POST", "/commands/confirm-story-candidate", confirm)[0] == 202
        runtime = registry.get(root.name)["agent_runtime"]
        assert runtime.story.view()["confirmed"]["version"] == 1
        assert runtime.proposals.read(job.proposal_id)["status"] == "reviewing"
        assert FileCommandResultStore(root).read("accept-one").state.value == "reserved"
