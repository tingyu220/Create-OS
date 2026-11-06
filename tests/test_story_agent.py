"""Fake 验证自主工具、多轮历史、正式设定冻结和真实消息注入。"""

import json
import pytest
from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.novel_project_command import NovelProjectCreator
from test_agent_conversation import finish
from test_story_architecture import BLOCKS


class ScriptClient:
    def __init__(self, actions):
        self.actions, self.calls = iter(actions), []

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        action = next(self.actions)
        return json.dumps(action, ensure_ascii=False) if isinstance(action, dict) else action


@pytest.mark.parametrize("idea,first,question", [("海城中交易记忆", "read_candidate", "先讨论牺牲与主题？"), ("沙漠里每夜重建的城市", "read_confirmed", "先选世界规则：迁徙城还是梦境城？")])
def test_model_selects_different_tools_and_history(tmp_path, idea, first, question):
    client = ScriptClient([{"action": first}, {"action": "finish_turn", "reply": question},
                           {"action": "propose_revision", "expected_revision": 0, "blocks": BLOCKS, "open_questions": ["结局？"]},
                           {"action": "finish_turn", "reply": "人物已补充，可以编辑候选。"}])
    runtime = WriterAgentRuntime(tmp_path, "p", client_factory=lambda: client)
    try:
        first_job = finish(runtime, runtime.submit(idea, None))
        assert first_job.status == "completed" and first_job.tool_trace[0]["input"]["action"] == first
        second = finish(runtime, runtime.submit("主角是修钟人", None, session_id=first_job.session_id))
        assert second.status == "completed", second.error
        assert runtime.story.view()["candidate"]["revision"] == 1
        assert runtime.story.view()["confirmed"] is None
        prompt = "\n".join(message.content for message in client.calls[-1])
        assert idea in prompt and "主角是修钟人" in prompt and question in prompt
        assert len(second.step_snapshots) == 2
    finally:
        runtime._pool.shutdown()


@pytest.mark.parametrize("bad", ["坏 JSON", {"action": "confirm"}, {"action": "propose_revision", "expected_revision": 0, "blocks": [], "open_questions": []}])
def test_bad_tool_cannot_modify_candidate(tmp_path, bad):
    client = ScriptClient([bad])
    runtime = WriterAgentRuntime(tmp_path, "p", client_factory=lambda: client)
    try:
        job = finish(runtime, runtime.submit("可以", None))
        assert job.status == "failed" and job.retryable
        assert runtime.story.view()["candidate"] is None and runtime.story.view()["confirmed"] is None
    finally:
        runtime._pool.shutdown()


def test_confirmed_text_actually_enters_first_chapter_and_sources(tmp_path):
    root = NovelProjectCreator(tmp_path).create("新书", "Idea", operation_id="create")
    client = ScriptClient(["《第1章》\n隔离候选正文"])
    runtime = WriterAgentRuntime(root, client_factory=lambda: client)
    try:
        with pytest.raises(ValueError, match="story_confirmation_required"):
            runtime.submit("写第一章", 1, mode="act")
        story = runtime.story
        candidate = story.propose(story.session_id, BLOCKS, [], expected_revision=0, actor="作者", operation_id="v1")
        confirmed = story.confirm(story.session_id, 1, candidate["hash"], expected_confirmed_version=0, actor="作者", operation_id="confirm")
        story.propose(story.session_id, [{**BLOCKS[0], "text": "未确认哨兵"}], [], expected_revision=1, actor="agent", operation_id="v2")
        job = finish(runtime, runtime.submit("按正式设定写第一章", 1, mode="act"))
        assert job.status == "completed", job.error
        prompt = "\n".join(message.content for message in client.calls[0])
        for block in BLOCKS:
            assert block["text"] in prompt
        assert "未确认哨兵" not in prompt
        assert confirmed["hash"] in prompt and "version=1" in prompt
        source = next(item for item in job.context_snapshot["sources"] if item["label"] == "已确认故事设定")
        assert source["usage"] == "included" and source["story_hash"] == confirmed["hash"]
        location = source["message_location"]
        assert client.calls[0][location["index"]].content[location["start"]:location["end"]] == confirmed["text"]
        assert job.proposal_id and runtime.store.current(1) is None
    finally:
        runtime._pool.shutdown()


def test_step_budget_can_continue_and_retry_keeps_history(tmp_path):
    client = ScriptClient([*({"action": "read_confirmed"} for _ in range(6)), {"action": "finish_turn", "reply": "继续后给出两条世界备选。"}, "坏包", {"action": "finish_turn", "reply": "已重试"}])
    runtime = WriterAgentRuntime(tmp_path, "p", client_factory=lambda: client)
    try:
        budget = finish(runtime, runtime.submit("Idea", None))
        assert budget.status == "completed" and len(budget.tool_trace) == 6
        continued = finish(runtime, runtime.submit("继续", None))
        assert continued.status == "completed"
        assert "达到工具步数预算" in "\n".join(item.content for item in client.calls[-1])
        failed = finish(runtime, runtime.submit("再次讨论", None))
        assert failed.status == "failed"
        retried = finish(runtime, runtime.retry(failed.job_id, chapter_number=None, session_id=failed.session_id))
        assert retried.status == "completed"
        assert sum(item["content"] == "再次讨论" for item in runtime.conversations.conversation(None)["messages"]) == 1
    finally:
        runtime._pool.shutdown()


def test_queued_chapter_freezes_confirmed_version_and_required_budget(tmp_path, monkeypatch):
    from threading import Event
    root = NovelProjectCreator(tmp_path).create("冻结测试", "Idea", operation_id="create")
    client = ScriptClient(["《第1章》\n使用旧确认版创作"])
    runtime = WriterAgentRuntime(root, client_factory=lambda: client)
    release = Event()
    try:
        store = runtime.story
        first = store.propose(store.session_id, BLOCKS, [], expected_revision=0, actor="作者", operation_id="v1")
        store.confirm(store.session_id, 1, first["hash"], expected_confirmed_version=0, actor="作者", operation_id="confirm1")
        runtime._pool.submit(lambda: release.wait(10))
        queued = runtime.submit("写第一章", 1, mode="act")
        second = store.propose(store.session_id, [{**BLOCKS[0], "text": "后确认哨兵"}], [], expected_revision=1, actor="作者", operation_id="v2")
        store.confirm(store.session_id, 2, second["hash"], expected_confirmed_version=1, actor="作者", operation_id="confirm2")
        release.set()
        completed = finish(runtime, queued)
        assert completed.status == "completed", completed.error
        prompt = "\n".join(message.content for message in client.calls[-1])
        assert first["text"] in prompt and "后确认哨兵" not in prompt
        assert completed.story_context["version"] == 1 and store.view()["confirmed"]["version"] == 2
        monkeypatch.setattr("creative_os.story_context.MAX_STORY_CONTEXT_CHARS", 2)
        with pytest.raises(ValueError, match="required_story_context_budget_exceeded"):
            runtime.submit("不能裁剪正式必需设定", 1, mode="act")
        assert len(client.calls) == 1
    finally:
        release.set(); runtime._pool.shutdown()
