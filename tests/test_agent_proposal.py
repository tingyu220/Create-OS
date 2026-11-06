"""临时项目与 Fake 模型验收：候选不写稿，审阅可恢复且不覆盖人工修改。"""

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.memory.feedback import FeedbackStore
from creative_os.workspace_command import CommandRequest


def finish(runtime, job):
    for _ in range(300):
        job = runtime.get(job.job_id)
        if job.status in {"completed", "failed"}:
            assert job.status == "completed", job.error
            return job
        time.sleep(0.01)
    raise AssertionError("任务未结束")


@pytest.fixture
def model(monkeypatch):
    calls = []

    class FakeClient:
        def complete(self, messages, **kwargs):
            calls.append(messages)
            return f"候选正文第{len(calls)}次"

    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: FakeClient())
    return calls


def review(runtime, job, action, reason="", key="r1", **extra):
    return runtime.proposal_commands.execute(CommandRequest(
        "review_writer_proposal", key, "作者",
        {"project_id": runtime.project_id, "chapter_number": job.chapter_number,
         "session_id": job.session_id, "proposal_id": job.proposal_id},
        {"action": action, "reason": reason, **extra}, idempotency_key=key))


def test_first_candidate_rejection_and_cancel_never_change_text_or_versions(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, project_id="logical-project")
    job = finish(runtime, runtime.submit("写第一章", 1, mode="act"))
    assert runtime.store.current(1) is None
    result = review(runtime, job, "reject", "人物动机不足")
    assert result.status == "accepted", result.error
    assert runtime.store.current(1) is None and runtime.store.versions(1) == ()
    proposal = runtime.proposals.read(job.proposal_id)
    assert proposal["status"] == "rejected" and proposal["base"]["source"] == "empty"
    second = finish(runtime, runtime.submit("另一份候选", 1, mode="act"))
    assert review(runtime, second, "cancel", "暂缓处理", "r2").status == "accepted"
    assert runtime.store.versions(1) == ()


def test_frozen_draft_diff_survives_latest_edits_and_restart(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    runtime.store.save(1, "冻结的原工作稿\n", actor="作者")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    runtime.store.save(1, "作者新稿\n", actor="作者", expected_version=1)
    restored = WriterAgentRuntime(tmp_path, project_id="p")
    proposal = restored.proposals.view(job.proposal_id)
    assert proposal["base"]["version"] == 1
    assert proposal["base"]["content"] == "冻结的原工作稿\n"
    assert "冻结的原工作稿" in proposal["diff"] and "作者新稿" not in proposal["diff"]
    assert proposal["result"]["content"] == "候选正文第1次"
    assert proposal["result"]["hash"] == hashlib.sha256("候选正文第1次".encode()).hexdigest()
    assert review(restored, job, "accept").error.code == "proposal_base_conflict"
    assert restored.store.current(1)[1] == "作者新稿\n"


def test_accept_once_and_feedback_scoped_to_proposal_and_message(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    job = finish(runtime, runtime.submit("改写", 2, mode="act"))
    first = review(runtime, job, "accept", "保留这种叙述")
    assert first.status == "accepted", first.error
    assert review(runtime, job, "accept", "保留这种叙述") == first
    assert review(runtime, job, "accept", "保留这种叙述", "r2").status == "accepted"
    restored = WriterAgentRuntime(tmp_path, project_id="p")
    assert review(restored, job, "accept", "保留这种叙述", "r3").status == "accepted"
    assert len(runtime.store.versions(2)) == 1
    assert review(restored, job, "reject", "改主意", "r4").error.code == "proposal_already_reviewed"
    feedback, = FeedbackStore(tmp_path).list()
    assert feedback.project_id == "p" and feedback.task_id == job.job_id
    assert feedback.proposal_id == job.proposal_id and feedback.session_id == job.session_id
    proposal = restored.proposals.read(job.proposal_id)
    assert feedback.message_id == proposal["message_id"]
    assert feedback.result_ref == proposal["result"]["ref"] and feedback.chapter_number == 2
    assert not (tmp_path / ".creative_os" / "memory" / "items").exists()


def test_formal_baseline_change_and_wrong_chapter_are_rejected(tmp_path, model):
    final = tmp_path / "production" / "final_chapters" / "chapter_001.md"
    final.parent.mkdir(parents=True)
    final.write_text("正式原稿", encoding="utf-8")
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    final.write_text("正式稿新内容", encoding="utf-8")
    assert review(runtime, job, "accept").error.code == "proposal_base_conflict"
    assert review(runtime, job, "reject", "不采用", "r2").status == "accepted"
    assert final.read_text(encoding="utf-8") == "正式稿新内容"
    assert runtime.store.current(1) is None
    wrong = CommandRequest("review_writer_proposal", "wrong", "作者",
                           {"project_id": "p", "chapter_number": 2, "session_id": job.session_id,
                            "proposal_id": job.proposal_id}, {"action": "accept"})
    assert runtime.proposal_commands.execute(wrong).error.code == "proposal_scope_mismatch"


def test_revise_explicit_candidate_retains_baseline_and_is_idempotent(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    runtime.store.save(1, "原稿", actor="作者")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    result = review(runtime, job, "revise", "保留候选开头，重写结尾", source="candidate")
    assert result.status == "accepted", result.error
    assert review(runtime, job, "revise", "保留候选开头，重写结尾", "r2", source="candidate").status == "accepted"
    child_id = next(ref.split(":", 1)[1] for ref in result.emitted_event_refs if ref.startswith("agent-job:"))
    child = finish(runtime, runtime.get(child_id))
    candidate = runtime.proposals.read(child.proposal_id)
    assert candidate["parent_proposal_id"] == job.proposal_id
    assert candidate["base"]["content"] == "原稿"
    assert candidate["input"]["content"] == "候选正文第1次"
    assert "保留候选开头，重写结尾" in model[-1][-1].content
    assert "候选正文第1次" in model[-1][-1].content
    assert len(model) == 2 and len(runtime.store.versions(1)) == 1


def test_analyze_has_no_proposal_or_feedback(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    job = finish(runtime, runtime.submit("为什么这样写？", 1))
    assert job.proposal_id is None and runtime.store.versions(1) == ()
    assert not runtime.proposals.root.exists()


@pytest.mark.parametrize("restart", [False, True])
def test_restart_reconciles_accept_after_feedback_write_failure_without_duplicate(tmp_path, model, monkeypatch, restart):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    original = FeedbackStore.append_once

    def fail_after_append(store, feedback):
        original(store, feedback)
        raise OSError("模拟反馈已写入但响应失败")

    monkeypatch.setattr(FeedbackStore, "append_once", fail_after_append)
    result = review(runtime, job, "accept")
    assert result.status == "failed"
    assert len(runtime.store.versions(1)) == 1
    runtime.store.save(1, "之后人工修改", actor="作者", expected_version=1)
    monkeypatch.setattr(FeedbackStore, "append_once", original)
    restored = WriterAgentRuntime(tmp_path, project_id="p") if restart else runtime
    replay = review(restored, job, "accept")
    assert replay.status == "accepted", replay.error
    assert restored.store.current(1)[1] == "之后人工修改"
    assert len(FeedbackStore(tmp_path).list()) == 1
    assert restored.proposals.read(job.proposal_id)["status"] == "accepted"


def test_generation_uses_frozen_input_even_when_author_edits_during_model_call(tmp_path, model, monkeypatch):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    runtime.store.save(1, "冻结原工作稿", actor="作者")

    class FakeClient:
        def complete(self, messages, **kwargs):
            assert "冻结原工作稿" in messages[-1].content
            runtime.store.save(1, "作者并发修改", actor="作者", expected_version=1)
            return "独立生成结果"

    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: FakeClient())
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    assert runtime.proposals.read(job.proposal_id)["base"]["version"] == 1
    assert review(runtime, job, "accept").error.code == "proposal_base_conflict"
    assert runtime.store.current(1)[1] == "作者并发修改"


def test_revise_from_base_survives_restart_and_keeps_original_decision(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    runtime.store.save(2, "原稿唯一词", actor="作者")
    analysis = finish(runtime, runtime.submit("解释原因", 2))
    job = finish(runtime, runtime.submit_from_decision(analysis.decision_id))
    restored = WriterAgentRuntime(tmp_path, project_id="p")
    result = review(restored, job, "revise", "重写", source="base")
    child_id = next(ref.split(":", 1)[1] for ref in result.emitted_event_refs if ref.startswith("agent-job:"))
    child = finish(restored, restored.get(child_id))
    assert child.decision_id == analysis.decision_id and child.chapter_number == 2
    assert restored.proposals.read(child.proposal_id)["input"]["content"] == "原稿唯一词"
    feedback, = FeedbackStore(tmp_path).list()
    assert feedback.decision_id == analysis.decision_id


def test_restart_before_accept_write_rechecks_changed_formal_and_keeps_server_available(tmp_path, model, monkeypatch):
    formal = tmp_path / "production" / "final_chapters" / "chapter_001.md"
    formal.parent.mkdir(parents=True)
    formal.write_text("原正式稿", encoding="utf-8")
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    monkeypatch.setattr(runtime.store, "save", lambda *a, **kw: (_ for _ in ()).throw(OSError("落稿前中断")))
    assert review(runtime, job, "accept").status == "failed"
    formal.write_text("后来修改正式稿", encoding="utf-8")
    restored = WriterAgentRuntime(tmp_path, project_id="p")
    assert restored.store.current(1) is None
    assert review(restored, job, "accept").error.code == "proposal_base_conflict"
    assert review(restored, job, "reject", "保留新正式稿", "r2").status == "accepted"
    assert formal.read_text(encoding="utf-8") == "后来修改正式稿"


def test_duplicate_review_receipt_recovered_when_response_finalization_fails(tmp_path, model, monkeypatch):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    assert review(runtime, job, "reject", "不采用").status == "accepted"
    monkeypatch.setattr(runtime.proposal_commands._store, "complete", lambda *a: (_ for _ in ()).throw(OSError("回执中断")))
    assert review(runtime, job, "reject", "不采用", "duplicate").status == "failed"
    restored = WriterAgentRuntime(tmp_path, project_id="p")
    assert review(restored, job, "reject", "不采用", "duplicate").status == "accepted"
    assert len(FeedbackStore(tmp_path).list()) == 1


def test_accept_unchanged_candidate_feedback_failure_can_recover_after_later_edit(tmp_path, model, monkeypatch):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    runtime.store.save(1, "候选正文第1次", actor="作者")
    job = finish(runtime, runtime.submit("保持当前正文", 1, mode="act"))
    original = FeedbackStore.append_once
    monkeypatch.setattr(FeedbackStore, "append_once", lambda *a: (_ for _ in ()).throw(OSError("反馈暂不可写")))
    assert review(runtime, job, "accept").status == "failed"
    assert len(runtime.store.versions(1)) == 1
    runtime.store.save(1, "之后人工改稿", actor="作者", expected_version=1)
    monkeypatch.setattr(FeedbackStore, "append_once", original)
    restored = WriterAgentRuntime(tmp_path, project_id="p")
    assert review(restored, job, "accept").status == "accepted"
    assert restored.store.current(1)[1] == "之后人工改稿"
    assert len(FeedbackStore(tmp_path).list()) == 1


def test_revision_cannot_refresh_stale_base_to_bypass_author_edit(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    runtime.store.save(1, "提案原稿", actor="作者")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    runtime.store.save(1, "人工新稿", actor="作者", expected_version=1)
    result = review(runtime, job, "revise", "基于候选再修改", source="candidate")
    child_id = next(ref.split(":", 1)[1] for ref in result.emitted_event_refs if ref.startswith("agent-job:"))
    child = finish(runtime, runtime.get(child_id))
    assert review(runtime, child, "accept", key="child").error.code == "proposal_base_conflict"
    assert runtime.store.current(1)[1] == "人工新稿"


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("gap", ["after_reserve", "before_review_intent"])
def test_reserved_review_without_intent_can_replay_same_key_safely(tmp_path, model, monkeypatch, restart, gap):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    with monkeypatch.context() as fault:
        if gap == "after_reserve":
            fault.setattr(runtime.proposal_commands, "_execute", lambda *_: (_ for _ in ()).throw(RuntimeError("reserve_before_handler")))
            with pytest.raises(RuntimeError, match="reserve_before_handler"):
                review(runtime, job, "accept")
        else:
            original_write = runtime.proposals.write

            def fail_intent(proposal):
                if proposal["review"] is not None:
                    raise OSError("intent_write_interrupted")
                original_write(proposal)

            fault.setattr(runtime.proposals, "write", fail_intent)
            assert review(runtime, job, "accept").error.code == "command_outcome_unknown"
    assert runtime.proposals.read(job.proposal_id)["review"] is None
    assert runtime.proposal_commands._store.read("r1").state.value == "reserved"
    assert runtime.store.current(1) is None
    if restart:
        runtime = WriterAgentRuntime(tmp_path, project_id="p")
    assert review(runtime, job, "accept", "不同载荷").error.code == "idempotency_conflict"
    assert runtime.proposals.read(job.proposal_id)["review"] is None
    result = review(runtime, job, "accept")
    assert result.status == "accepted", result.error
    assert review(runtime, job, "accept") == result
    assert len(runtime.store.versions(1)) == 1 and len(model) == 1
    assert len(FeedbackStore(tmp_path).list()) == 1


@pytest.mark.parametrize("restart", [False, True])
def test_unchanged_accept_before_receipt_has_no_committed_acceptance_evidence(tmp_path, model, monkeypatch, restart):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    runtime.store.save(1, "候选正文第1次", actor="作者")
    job = finish(runtime, runtime.submit("保持当前正文", 1, mode="act"))
    original_write = runtime.proposals.write

    def fail_receipt(proposal):
        if (proposal.get("review") or {}).get("draft_version") is not None:
            raise OSError("accept_receipt_write_interrupted")
        original_write(proposal)

    with monkeypatch.context() as fault:
        fault.setattr(runtime.proposals, "write", fail_receipt)
        assert review(runtime, job, "accept").error.code == "command_outcome_unknown"
    assert runtime.store.saved_operation(1, job.proposal_id) is None
    assert "draft_version" not in runtime.proposals.read(job.proposal_id)["review"]
    runtime.store.save(1, "随后人工改稿", actor="作者", expected_version=1)
    restored = WriterAgentRuntime(tmp_path, project_id="p") if restart else runtime
    assert review(restored, job, "accept").error.code == "proposal_base_conflict"
    assert restored.proposals.read(job.proposal_id)["status"] == "pending"
    assert restored.store.current(1)[1] == "随后人工改稿"
    assert FeedbackStore(tmp_path).list() == []


def test_reserved_without_intent_but_with_unexplained_effect_stays_blocked(tmp_path, model, monkeypatch):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    with monkeypatch.context() as fault:
        fault.setattr(runtime.proposal_commands, "_execute", lambda *_: (_ for _ in ()).throw(RuntimeError("保留后中断")))
        with pytest.raises(RuntimeError, match="保留后中断"):
            review(runtime, job, "accept")
    # 模拟违反先记意图契约的外部残留；不能只因 review=None 就判定无副作用。
    runtime.store.save(1, "外部不明操作", actor="作者", operation_id=job.proposal_id)
    assert review(runtime, job, "accept").error.code == "command_outcome_unknown"
    assert len(runtime.store.versions(1)) == 1
    assert runtime.store.current(1)[1] == "外部不明操作"
    assert runtime.proposal_commands._store.read("r1").state.value == "reserved"
    assert FeedbackStore(tmp_path).list() == []


def test_reserved_review_with_unreadable_evidence_keeps_original_reservation(tmp_path, model, monkeypatch):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    with monkeypatch.context() as fault:
        fault.setattr(runtime.proposal_commands, "_execute", lambda *_: (_ for _ in ()).throw(RuntimeError("保留后中断")))
        with pytest.raises(RuntimeError):
            review(runtime, job, "accept")
    with monkeypatch.context() as fault:
        fault.setattr(runtime.store, "saved_operation", lambda *_: (_ for _ in ()).throw(OSError("证据不可读")))
        assert review(runtime, job, "accept").error.code == "command_outcome_unknown"
    assert runtime.proposal_commands._store.read("r1").state.value == "reserved"
    assert review(runtime, job, "accept").status == "accepted"


def test_simultaneous_same_key_waits_for_original_review_instead_of_restarting_it(tmp_path, model, monkeypatch):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    job = finish(runtime, runtime.submit("改写", 1, mode="act"))
    entered, release, duplicate_started = Event(), Event(), Event()
    original_write = runtime.proposals.write

    def hold_first_intent(proposal):
        if proposal["status"] == "reviewing" and not entered.is_set():
            entered.set()
            assert release.wait(3), "首个审阅未释放"
        original_write(proposal)

    def duplicate():
        duplicate_started.set()
        return review(runtime, job, "accept")

    monkeypatch.setattr(runtime.proposals, "write", hold_first_intent)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(review, runtime, job, "accept")
        assert entered.wait(3)
        second = pool.submit(duplicate)
        assert duplicate_started.wait(3)
        try:
            assert not second.done(), "原审阅未结束时不应另行续办"
        finally:
            release.set()
        assert first.result().status == "accepted"
        assert second.result() == first.result()
    assert len(runtime.store.versions(1)) == 1
    assert len(FeedbackStore(tmp_path).list()) == 1
