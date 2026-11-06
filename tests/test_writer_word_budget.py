import time

import pytest

from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.workspace_command import CommandRequest


def finish(runtime, job):
    for _ in range(300):
        current = runtime.get(job.job_id)
        if current.status in {"completed", "failed"}:
            assert current.status == "completed", current.error
            return current
        time.sleep(0.01)
    raise AssertionError("隔离任务未结束")


def client(monkeypatch, output):
    calls = []

    class FakeClient:
        def complete(self, messages, **kwargs):
            calls.append(messages)
            return output

    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: FakeClient())
    return calls


@pytest.mark.parametrize("input_words,remaining_target,remaining_max", [(0, 4500, 4800), (1200, 3300, 3600), (4700, 0, 100), (6045, 0, 0)])
def test_prompt_defines_final_chapter_total_and_frozen_input_budget(tmp_path, monkeypatch, input_words, remaining_target, remaining_max):
    calls = client(monkeypatch, "候" * 4500)
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    if input_words:
        runtime.store.save(81, "旧" * input_words, actor="作者")
    job = finish(runtime, runtime.submit("读取前文，继续写第81章。", 81, mode="act"))
    prompt = calls[0][-1].content
    assert "最终整章总字数" in prompt and "不是本次新增字数" in prompt
    assert f"冻结输入精确字数：{input_words} 字" in prompt
    assert f"目标新增预算：{remaining_target} 字" in prompt
    assert f"新增上限预算：{remaining_max} 字" in prompt
    if input_words > 4800:
        assert "整合、压缩" in prompt and "不要完整照抄原稿后再新增" in prompt
    elif input_words:
        assert "只输出最终完整章节" in prompt
    # 输入预算是可核对的真实请求，而非未入模的来源引用。
    assert any(item.get("content_snapshot") == prompt for item in job.context_snapshot["sources"])
    assert len(calls) == 1


def test_large_overshoot_keeps_exact_candidate_and_reports_optional_adjustments(tmp_path, monkeypatch):
    original = "# 第81章\n" + "旧" * 6040
    candidate = "#" + original + "新" * 4592
    calls = client(monkeypatch, candidate)
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    runtime.store.save(81, original, actor="作者")
    before = runtime.store.current(81)
    job = finish(runtime, runtime.submit("继续写第81章", 81, mode="act"))
    proposal = runtime.proposals.read(job.proposal_id)
    assert job.actual_words == 10638 and job.within_word_range is False
    assert proposal["status"] == "pending" and proposal["result"]["content"] == candidate
    assert runtime.store.current(81) == before
    assert job.word_assessment["input_words"] == 6045
    assert job.word_assessment["net_change_words"] == 4593
    assert job.word_assessment["severity"] == "significant"
    assert job.word_assessment["adjustment_options"]
    assert proposal["word_assessment"] == job.word_assessment
    assert "显著偏离" in job.message and "整章" in job.message
    restored = WriterAgentRuntime(tmp_path, project_id="p")
    assert restored.get(job.job_id).word_assessment == job.word_assessment
    assert restored.proposals.read(job.proposal_id)["word_assessment"] == job.word_assessment
    assert len(calls) == 1


def test_moderate_overshoot_stays_a_soft_warning(tmp_path, monkeypatch):
    calls = client(monkeypatch, "文" * 5000)
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    job = finish(runtime, runtime.submit("写作", 1, mode="act"))
    assert job.within_word_range is False and job.word_assessment["severity"] == "outside_range"
    assert runtime.proposals.read(job.proposal_id)["result"]["content"] == "文" * 5000
    assert runtime.store.current(1) is None and len(calls) == 1


def test_counting_includes_title_and_punctuation_but_excludes_all_whitespace(tmp_path, monkeypatch):
    calls = client(monkeypatch, " # 第1章\n甲，乙。\n丙！ ")
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    runtime.store.save(1, " # 第1章\n\n甲，乙。\t ", actor="作者")
    job = finish(runtime, runtime.submit("修改", 1, mode="act", target_words=10, tolerance_words=0))
    assert job.word_assessment["input_words"] == 8
    assert job.actual_words == 10 and job.word_assessment["net_change_words"] == 2
    assert job.word_assessment["count_method"] == "non_whitespace_characters"
    assert job.word_assessment["severity"] == "within_range"
    assert len(calls) == 1


@pytest.mark.parametrize("source,expected_input_words", [("candidate", 8000), ("base", 1000)])
def test_revision_budget_uses_selected_frozen_source_not_current_draft(tmp_path, monkeypatch, source, expected_input_words):
    calls = client(monkeypatch, "候" * 8000)
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    runtime.store.save(1, "原" * 1000, actor="作者")
    parent = finish(runtime, runtime.submit("创作", 1, mode="act"))
    runtime.store.save(1, "当前" * 3000, actor="作者", expected_version=1)
    request = CommandRequest("review_writer_proposal", "budget-revise", "作者",
                             {"project_id": "p", "chapter_number": 1, "session_id": parent.session_id, "proposal_id": parent.proposal_id},
                             {"action": "revise", "reason": "整合压缩为最终整章4500字", "source": source}, idempotency_key="budget-revise")
    result = runtime.proposal_commands.execute(request)
    assert result.status.value == "accepted", result.error
    child_id = next(ref.split(":", 1)[1] for ref in result.emitted_event_refs if ref.startswith("agent-job:"))
    child = finish(runtime, runtime.get(child_id))
    assert f"冻结输入精确字数：{expected_input_words} 字" in calls[-1][-1].content
    assert child.word_assessment["input_words"] == expected_input_words
    assert runtime.store.current(1)[1] == "当前" * 3000 and len(calls) == 2
