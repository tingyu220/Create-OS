import time
from dataclasses import asdict

import pytest

from creative_os.agent_runtime import WriterAgentRuntime


def finish(runtime, job):
    for _ in range(300):
        current = runtime.get(job.job_id)
        if current.status in {"completed", "failed"}:
            return current
        time.sleep(0.01)
    raise AssertionError("任务未结束")


@pytest.fixture
def model(monkeypatch):
    calls = []

    class FakeClient:
        def complete(self, messages, **kwargs):
            calls.append(messages)
            return "建议保留人物的犹豫。"

    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: FakeClient())
    return calls


def test_history_survives_restart_and_reaches_model_without_cross_chapter(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    runtime.store.save(1, "当前章节独特正文", actor="作者")
    first = finish(runtime, runtime.submit("只分析：人物为何犹豫", 1))
    second = finish(runtime, runtime.submit("再具体说明", 1, session_id=first.session_id))
    assert second.mode == "analyze" and runtime.store.current(1)[0].version == 1
    restored = WriterAgentRuntime(tmp_path, project_id="p")
    session = restored.conversation(1)
    assert session["session_id"] == first.session_id == second.session_id
    assert len(session["messages"]) == 4
    assert session["messages"][1]["content"] == "建议保留人物的犹豫。"
    assert restored.get(second.job_id).status == "completed"
    prompt = "\n".join(message.content for message in model[1])
    assert "当前章节独特正文" in prompt
    assert "人物为何犹豫" in prompt and "建议保留人物的犹豫。" in prompt
    finish(restored, restored.submit("只分析：另一章", 2))
    assert "人物为何犹豫" not in "\n".join(message.content for message in model[-1])
    with pytest.raises(ValueError, match="session_scope_mismatch"):
        restored.submit("只分析", 2, session_id=first.session_id)


def test_act_keeps_selected_chapter_and_detects_concurrent_edit(tmp_path, monkeypatch):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    final = tmp_path / "production" / "final_chapters"
    final.mkdir(parents=True)
    (final / "chapter_080.md").write_text("其他章节", encoding="utf-8")

    class FakeClient:
        def complete(self, messages, **kwargs):
            runtime.store.save(1, "作者刚修改的正文", actor="作者")
            return "模型生成的正文"

    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: FakeClient())
    job = finish(runtime, runtime.submit("继续写这一章", 1, mode="act"))
    assert job.chapter_number == 1
    assert job.status == "completed" and job.proposal_id
    assert runtime.proposals.read(job.proposal_id)["base"]["source"] == "empty"
    assert runtime.store.current(1)[1] == "作者刚修改的正文"
    assert runtime.store.current(81) is None


def test_failure_reason_and_retry_are_persistent_and_idempotent(tmp_path, monkeypatch, model):
    def fail():
        raise RuntimeError("测试服务拒绝：额度不足")

    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", fail)
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    failed = finish(runtime, runtime.submit("只分析这一章", 1))
    restored = WriterAgentRuntime(tmp_path, project_id="p")
    assert "额度不足" in restored.get(failed.job_id).error
    assert restored.get(failed.job_id).retryable
    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: type("Fake", (), {"complete": lambda *a, **kw: "重试结果"})())
    retry = restored.retry(failed.job_id, chapter_number=1, session_id=failed.session_id)
    same = restored.retry(failed.job_id, chapter_number=1, session_id=failed.session_id)
    assert same.job_id == retry.job_id
    assert finish(restored, retry).status == "completed"
    session = restored.conversation(1)
    assert len([m for m in session["messages"] if m["role"] == "user"]) == 1
    assert session["messages"][-1]["content"] == "重试结果"
    with pytest.raises(ValueError, match="session_scope_mismatch"):
        restored.retry(failed.job_id, chapter_number=2, session_id=failed.session_id)


def test_restart_marks_inflight_failed_and_preserves_messages(tmp_path, model, monkeypatch):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    monkeypatch.setattr(runtime._pool, "submit", lambda *args: None)
    queued = runtime.submit("只分析", 1)
    restored = WriterAgentRuntime(tmp_path, project_id="p")
    job = restored.get(queued.job_id)
    assert job.status == "failed" and job.retryable
    assert "中断" in job.error
    assert restored.conversation(1)["messages"][0]["content"] == "只分析"
    assert asdict(job)["project_id"] == "p"


def test_saving_interruption_is_not_retryable_and_busy_session_is_rejected(tmp_path, model, monkeypatch):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    monkeypatch.setattr(runtime._pool, "submit", lambda *args: None)
    queued = runtime.submit("修改本章", 1)
    with pytest.raises(ValueError, match="session_busy"):
        runtime.submit("又一次修改", 1)
    runtime._set(queued.job_id, status="saving")
    restored = WriterAgentRuntime(tmp_path, project_id="p")
    assert not restored.get(queued.job_id).retryable
    with pytest.raises(ValueError, match="job_not_retryable"):
        restored.retry(queued.job_id, chapter_number=1, session_id=queued.session_id)


def test_project_identity_cannot_read_another_projects_session(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    finish(runtime, runtime.submit("只分析", 1))
    with pytest.raises(ValueError, match="session_scope_mismatch"):
        WriterAgentRuntime(tmp_path, project_id="other")


@pytest.mark.parametrize("question", ["为什么这样写？", "继续解释一下原因", "为什么建议修改结尾？"])
@pytest.mark.parametrize("has_draft", [False, True])
def test_analysis_questions_never_authorize_draft_changes(tmp_path, model, question, has_draft):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    if has_draft:
        runtime.store.save(1, "作者原稿", actor="作者")
    before = runtime.store.current(1)
    finish(runtime, runtime.submit("只分析，不要修改", 1))
    job = finish(runtime, runtime.submit(question, 1))
    assert job.mode == "analyze" and job.draft_version is None
    assert runtime.store.current(1) == before


def test_explicit_act_command_and_decision_link_survive_restart(tmp_path, model):
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    analysis = finish(runtime, runtime.submit("请分析本章", 1))
    act = finish(runtime, runtime.submit_from_decision(analysis.decision_id, feedback="增加动作"))
    assert act.mode == "act" and act.decision_id == analysis.decision_id
    restored = WriterAgentRuntime(tmp_path, project_id="p")
    assert restored.get(act.job_id).decision_id == analysis.decision_id
    revised = finish(restored, restored.submit_from_decision(restored.get(act.job_id).decision_id, feedback="保留新结尾"))
    assert revised.mode == "act" and revised.decision_id == analysis.decision_id
    assert "保留新结尾" in model[-1][-1].content
    assert restored.store.current(1) is None
    assert restored.proposals.read(revised.proposal_id)["result"]["content"] == "建议保留人物的犹豫。"
    explicit = finish(restored, restored.submit("继续写这一章", 2, mode="act"))
    assert explicit.mode == "act" and explicit.draft_version is None and explicit.proposal_id
