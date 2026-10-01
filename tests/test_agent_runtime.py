from creative_os.agent_runtime import WriterAgentRuntime
import time
import pytest


def test_agent_runtime_submits_a_queued_job(tmp_path):
    job = WriterAgentRuntime(tmp_path).submit("继续写这一章", 79)
    assert job.status == "queued"
    assert job.job_id.startswith("agent-")
    assert job.updated_at
    assert job.target_words == 4500
    assert job.tolerance_words == 300
    assert job.min_words == 4200
    assert job.max_words == 4800


def test_agent_runtime_rejects_invalid_word_target(tmp_path):
    with pytest.raises(ValueError, match="word_target_invalid"):
        WriterAgentRuntime(tmp_path).submit("继续写这一章", 79, target_words=0)


def test_agent_runtime_classifies_read_only_analysis_without_writing_draft(tmp_path):
    job = WriterAgentRuntime(tmp_path).submit("这一章我觉得有问题，你自己检查一下，不要修改正文。", 79)

    assert job.mode == "analyze"


def test_analysis_intent_keeps_current_chapter_even_when_it_contains_write_word(tmp_path):
    runtime = WriterAgentRuntime(tmp_path)
    final = tmp_path / "production" / "final_chapters"
    final.mkdir(parents=True)
    (final / "chapter_080.md").write_text("上一章", encoding="utf-8")
    job = runtime.submit("这一章目前写得不对，你自己检查一下。", 79)

    assert job.chapter_number == 79


def test_agent_runtime_analysis_completes_without_creating_working_draft(tmp_path, monkeypatch):
    class FakeClient:
        def complete(self, messages, *, temperature, max_tokens):
            return "发现中段推进不足，建议保留开头并重写中段。"

    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: FakeClient())
    runtime = WriterAgentRuntime(tmp_path)
    job = runtime.submit("这一章我觉得有问题，不要修改正文。", 79)
    for _ in range(100):
        current = runtime.get(job.job_id)
        if current and current.status == "completed":
            break
        time.sleep(0.01)
    current = runtime.get(job.job_id)
    assert current is not None and current.status == "completed"
    assert current.decision_id
    assert not (tmp_path / ".creative_os" / "writer" / "drafts" / "chapter_079.jsonl").exists()
    assert runtime.get_decision(current.decision_id)["analysis"].startswith("发现")


def test_agent_runtime_analysis_prompt_includes_exact_formal_word_count(tmp_path, monkeypatch):
    captured = {}

    class FakeClient:
        def complete(self, messages, *, temperature, max_tokens):
            captured["prompt"] = messages[-1].content
            return "已完成精确字数检查。"

    final = tmp_path / "production" / "final_chapters"
    final.mkdir(parents=True)
    (final / "chapter_079.md").write_text("第一段\n\n第二段", encoding="utf-8")
    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: FakeClient())
    runtime = WriterAgentRuntime(tmp_path)
    job = runtime.submit("检查本章，不要修改正文。", 79)
    for _ in range(100):
        current = runtime.get(job.job_id)
        if current and current.status == "completed":
            break
        time.sleep(0.01)

    assert current is not None and current.status == "completed"
    assert "正式稿精确字数：6 字" in captured["prompt"]


def test_agent_runtime_requires_existing_decision_before_act(tmp_path):
    runtime = WriterAgentRuntime(tmp_path)
    try:
        runtime.submit_from_decision("decision-missing", actor="作者")
    except ValueError as error:
        assert str(error) == "decision_not_found"
    else:
        raise AssertionError("expected decision_not_found")


def test_agent_runtime_act_from_decision_creates_new_working_draft(tmp_path, monkeypatch):
    captured = {}
    class FakeClient:
        def complete(self, messages, *, temperature, max_tokens):
            captured["prompt"] = messages[-1].content
            return "按方案修改后的正文"

    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: FakeClient())
    runtime = WriterAgentRuntime(tmp_path)
    decision_dir = tmp_path / ".creative_os" / "agent" / "decisions"
    decision_dir.mkdir(parents=True)
    (decision_dir / "decision-test.json").write_text('{"decision_id":"decision-test","target_chapter":79,"analysis":"重写中段","target_words":9,"tolerance_words":0}', encoding="utf-8")
    job = runtime.submit_from_decision("decision-test", feedback="减少警句，增加人物动作")
    for _ in range(100):
        current = runtime.get(job.job_id)
        if current and current.status == "completed":
            break
        time.sleep(0.02)
    assert current is not None and current.status == "completed"
    assert runtime.store.current(current.chapter_number)[1] == "按方案修改后的正文"
    assert "减少警句，增加人物动作" in captured["prompt"]


def test_agent_runtime_saves_out_of_range_draft_with_soft_warning(tmp_path, monkeypatch):
    calls = []

    class FakeClient:
        def complete(self, messages, *, temperature, max_tokens):
            calls.append(messages[-1].content)
            return "超" * 30

    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: FakeClient())
    runtime = WriterAgentRuntime(tmp_path)
    job = runtime.submit("完成本章", 1, target_words=10, tolerance_words=2)
    for _ in range(100):
        current = runtime.get(job.job_id)
        if current and current.status in {"completed", "failed"}:
            break
        time.sleep(0.01)

    assert current is not None and current.status == "completed"
    assert current.actual_words == 30
    assert current.within_word_range is False
    assert len(calls) == 1
    assert "超出" in current.message
    assert runtime.store.current(current.chapter_number)[1] == "超" * 30


