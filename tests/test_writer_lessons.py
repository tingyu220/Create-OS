"""作者经验闭环：临时项目、真实 Runtime 消息与持久恢复。"""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.memory.feedback import FeedbackStore
from creative_os.memory.model import MemoryStatus
from creative_os.memory.store import JsonMemoryStore
from creative_os.writer_experience_context import compile_writer_experience
from creative_os.workspace_command import CommandRequest
from test_agent_proposal import finish, model, review


def lesson(runtime, feedback, action="create", key="lesson-create", **payload):
    return runtime.lesson_commands.execute(CommandRequest(
        "manage_writer_lesson", key, "作者",
        {"project_id": runtime.project_id, "chapter_number": feedback.chapter_number,
         "session_id": feedback.session_id, "feedback_id": feedback.id},
        {"action": action, **payload}, idempotency_key=key))


def make_candidate(runtime, model):
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    assert review(runtime, job, "reject", "动机没有通过动作体现").status == "accepted"
    feedback = FeedbackStore(runtime.root).list()[0]
    result = lesson(runtime, feedback, title="动机表达", content="用可见动作承载人物动机", range="chapter")
    assert result.status == "accepted", result.error
    memory_id = result.emitted_event_refs[0].split(":")[1]
    return job, feedback, memory_id


def test_only_approved_relevant_experience_reaches_actual_model_messages(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, "p")
    _, feedback, memory_id = make_candidate(runtime, model)
    finish(runtime, runtime.submit("分析本章", 1))
    assert "用可见动作承载人物动机" not in model[-1][-1].content
    assert lesson(runtime, feedback, "approve", "approve", memory_id=memory_id, version=1, note="仅适用本章").status == "accepted"
    job = finish(runtime, runtime.submit("分析本章", 1))
    assert "用可见动作承载人物动机" in model[-1][-1].content
    trace = runtime.conversation(1)["jobs"][-1]["experience_context"]
    selected, = trace["selected"]
    assert selected["memory_id"] == memory_id and selected["content_hash"]
    assert selected["content_snapshot"] in model[-1][-1].content
    assert selected["evidence"][0]["source_id"] == feedback.id
    finish(runtime, runtime.submit("分析另一章", 2))
    assert "用可见动作承载人物动机" not in model[-1][-1].content
    restored = WriterAgentRuntime(tmp_path, "p")
    assert restored.conversation(1)["jobs"][-1]["experience_context"] == trace
    assert restored.store.versions(1) == ()


def test_empty_or_unowned_feedback_cannot_create_lesson(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, "p")
    job = finish(runtime, runtime.submit("写作", 1, mode="act"))
    assert review(runtime, job, "accept").status == "accepted"
    feedback = FeedbackStore(tmp_path).list()[0]
    assert lesson(runtime, feedback, title="", content="", range="project").status == "rejected"
    other = replace(feedback, project_id="other", id="foreign")
    FeedbackStore(tmp_path).append(other)
    assert lesson(runtime, other, title="错误", content="禁止泄漏", range="project", key="foreign").status == "rejected"
    assert runtime.lesson_query(1)["lessons"] == []


def test_candidate_and_approval_replays_conflicts_and_archive(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, "p")
    _, feedback, memory_id = make_candidate(runtime, model)
    assert lesson(runtime, feedback, title="动机表达", content="用可见动作承载人物动机", range="chapter").status == "accepted"
    assert lesson(runtime, feedback, title="变更", content="变更", range="chapter").error.code == "idempotency_conflict"
    approved = lesson(runtime, feedback, "approve", "a", memory_id=memory_id, version=1, note="确认")
    assert approved.status == "accepted"
    restored = WriterAgentRuntime(tmp_path, "p")
    assert lesson(restored, feedback, "approve", "a2", memory_id=memory_id, version=1, note="确认").status == "accepted"
    assert lesson(restored, feedback, "reject", "r", memory_id=memory_id, version=1, note="改变决定").status == "rejected"
    assert lesson(restored, feedback, "archive", "archive", memory_id=memory_id, version=1, note="停止使用").status == "accepted"
    finish(restored, restored.submit("分析", 1))
    assert "用可见动作承载人物动机" not in model[-1][-1].content
    assert len(restored.lesson_query(1)["lessons"]) == 1
    audits = [json.loads(line) for line in (tmp_path / ".creative_os/memory/audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [entry["action"] for entry in audits] == ["create_lesson", "approve", "archive"]


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("failure", ["intent", "audit", "receipt"])
def test_lesson_approval_recovers_each_checkpoint_once(tmp_path, model, monkeypatch, restart, failure):
    runtime = WriterAgentRuntime(tmp_path, "p")
    _, feedback, memory_id = make_candidate(runtime, model)
    if failure == "audit":
        original = JsonMemoryStore.append_audit

        def broken(store, *args, **kwargs):
            if args[0] == "approve":
                raise OSError("审计写入前中断")
            return original(store, *args, **kwargs)

        monkeypatch.setattr(JsonMemoryStore, "append_audit", broken)
    elif failure == "intent":
        handler = runtime.lesson_commands._handler
        original = handler._write

        def broken(path, value):
            if path.stem.endswith("-review"):
                raise OSError("首份审批意图前中断")
            return original(path, value)

        monkeypatch.setattr(handler, "_write", broken)
    else:
        commands = runtime.lesson_commands._store
        original = commands.complete
        monkeypatch.setattr(commands, "complete", lambda *args: (_ for _ in ()).throw(OSError("命令回执前中断")))
    result = lesson(runtime, feedback, "approve", "a", memory_id=memory_id, version=1, note="确认")
    assert result.error.code == "command_outcome_unknown"
    monkeypatch.undo()
    if restart:
        runtime = WriterAgentRuntime(tmp_path, "p")
    assert lesson(runtime, feedback, "approve", "a", memory_id=memory_id, version=1, note="确认").status == "accepted"
    assert runtime.lessons.store.get(memory_id).status == MemoryStatus.ACTIVE
    audits = [json.loads(line) for line in runtime.lessons.store.audit_path.read_text(encoding="utf-8").splitlines()]
    assert [entry["action"] for entry in audits] == ["create_lesson", "approve"]


def test_project_scope_never_leaks_even_if_foreign_memory_file_is_present(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path / "one", "p")
    _, feedback, memory_id = make_candidate(runtime, model)
    assert lesson(runtime, feedback, "approve", "a", memory_id=memory_id, version=1, note="确认").status == "accepted"
    other = WriterAgentRuntime(tmp_path / "two", "q")
    other.lessons.store.add_immutable(runtime.lessons.store.get(memory_id))
    finish(other, other.submit("分析第一章", 1))
    assert "用可见动作承载人物动机" not in model[-1][-1].content
    assert other.lesson_query(1)["lessons"] == []


def test_rejected_lessons_are_not_retrieved_and_budget_exclusions_are_recorded(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, "p")
    _, feedback, memory_id = make_candidate(runtime, model)
    assert lesson(runtime, feedback, "reject", "r", memory_id=memory_id, version=1, note="不通用").status == "accepted"
    assert compile_writer_experience(tmp_path, "p", 1, "t")[0] == ""
    for index in range(4):
        result = lesson(runtime, feedback, key=f"create-{index}", title=f"项目经验{index}", content=f"方法{index}。" * 350, range="project")
        item_id = result.emitted_event_refs[0].split(":")[1]
        assert lesson(runtime, feedback, "approve", f"approve-{index}", memory_id=item_id, version=1, note="适用项目").status == "accepted"
    job = finish(runtime, runtime.submit("分析另一章", 2))
    trace = runtime.get(job.job_id).experience_context
    assert trace["rendered_chars"] <= trace["budget_chars"] == 4000
    assert trace["selected"] and trace["truncated"]
    assert any(item["reason"] == "budget_exceeded" for item in trace["excluded"])
    for selected in trace["selected"]:
        assert selected["content_snapshot"] in model[-1][-1].content
        assert not selected["truncated"]


def test_unreviewed_proposal_and_forged_feedback_evidence_are_rejected(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, "p")
    _, feedback, memory_id = make_candidate(runtime, model)
    proposal = runtime.proposals.read(feedback.proposal_id)
    proposal["result"]["content"] = "不一致的候选正文"
    runtime.proposals.write(proposal)
    result = lesson(runtime, feedback, "approve", "forged", memory_id=memory_id, version=1, note="确认")
    assert result.error.code == "feedback_evidence_mismatch"
    assert runtime.lessons.store.get(memory_id).status == MemoryStatus.CANDIDATE


def test_recovery_conflict_preserves_new_revision_and_keeps_runtime_available(tmp_path, model, monkeypatch):
    runtime = WriterAgentRuntime(tmp_path, "p")
    _, feedback, memory_id = make_candidate(runtime, model)
    original = JsonMemoryStore.append_audit

    def broken(store, *args, **kwargs):
        if args[0] == "approve":
            raise OSError("状态写入后中断")
        return original(store, *args, **kwargs)

    monkeypatch.setattr(JsonMemoryStore, "append_audit", broken)
    assert lesson(runtime, feedback, "approve", "a", memory_id=memory_id, version=1, note="确认").error.code == "command_outcome_unknown"
    monkeypatch.setattr(JsonMemoryStore, "append_audit", original)
    runtime.lessons.store.save_revision(memory_id, content=runtime.lessons.store.get(memory_id).content, actor="作者")
    restored = WriterAgentRuntime(tmp_path, "p")
    assert restored.lessons.store.get(memory_id).version == 2
    assert restored.lessons.store.get(memory_id).status == MemoryStatus.CANDIDATE
    assert lesson(restored, feedback, "approve", "a", memory_id=memory_id, version=1, note="确认").error.code == "lesson_version_conflict"
    assert compile_writer_experience(tmp_path, "p", 1, "t")[0] == ""


def test_parallel_approval_produces_one_transition_and_one_audit(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, "p")
    _, feedback, memory_id = make_candidate(runtime, model)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: lesson(runtime, feedback, "approve", "a", memory_id=memory_id, version=1, note="确认"), range(2)))
    assert all(result.status == "accepted" for result in results)
    assert results[0] == results[1]
    audits = [json.loads(line) for line in runtime.lessons.store.audit_path.read_text(encoding="utf-8").splitlines()]
    assert [item["action"] for item in audits] == ["create_lesson", "approve"]


@pytest.mark.parametrize("failure", ["intent", "audit"])
def test_candidate_creation_recovers_without_duplicate_memory(tmp_path, model, monkeypatch, failure):
    runtime = WriterAgentRuntime(tmp_path, "p")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    assert review(runtime, job, "reject", "动作不足").status == "accepted"
    feedback = FeedbackStore(tmp_path).list()[0]
    handler = runtime.lesson_commands._handler
    if failure == "intent":
        original = handler._write
        monkeypatch.setattr(handler, "_write", lambda *args: (_ for _ in ()).throw(OSError("候选意图前中断")))
    else:
        original = JsonMemoryStore.append_audit
        monkeypatch.setattr(JsonMemoryStore, "append_audit", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("候选审计前中断")))
    result = lesson(runtime, feedback, title="动作", content="本章通过动作承载动机", range="chapter")
    assert result.error.code == "command_outcome_unknown"
    if failure == "intent":
        monkeypatch.setattr(handler, "_write", original)
    else:
        monkeypatch.setattr(JsonMemoryStore, "append_audit", original)
    restored = WriterAgentRuntime(tmp_path, "p")
    assert lesson(restored, feedback, title="动作", content="本章通过动作承载动机", range="chapter").status == "accepted"
    assert lesson(restored, feedback, key="same-new-key", title="动作", content="本章通过动作承载动机", range="chapter").status == "accepted"
    assert len(restored.lessons.store.list()) == 1
    assert len(restored.lessons.store.audit_path.read_text(encoding="utf-8").splitlines()) == 1
