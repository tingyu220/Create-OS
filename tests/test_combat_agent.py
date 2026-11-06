"""战斗委派只用临时书与 Fake；验证实际入模、只读权限及冻结重试。"""

from concurrent.futures import CancelledError
from copy import deepcopy
from dataclasses import asdict
import importlib
import json

import pytest

from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.combat_context import build_combat_context, read_combat_source
from creative_os.combat_model import CombatScope
from test_agent_conversation import finish
from test_combat_context import book, write, tree


def expert_api():
    try:
        return importlib.import_module("creative_os.combat_agent").run_combat_expert
    except ModuleNotFoundError:
        pytest.fail("战斗专家工具循环尚未实现")


def conclusion(verdict="noncombat", refs=(), reply="选择谈判冲突，保留技术代价。"):
    return {"action": "finish", "verdict": verdict, "reply": reply, "alternatives": [],
            "foreshadowing": [], "evidence_refs": list(refs), "unknowns": []}


def request(root):
    return build_combat_context(root, "book", CombatScope((2,), "研究本章冲突"),
                                task_id="job-1", session_id="session-1", instruction="检查本章")


@pytest.mark.parametrize("reverse", [False, True])
def test_expert_selects_read_order_and_evidence_only_from_actual_reads(tmp_path, reverse):
    root = book(tmp_path)
    write(root, "production/final_chapters/chapter_001.md", "邻章谈判")
    write(root, "production/final_chapters/chapter_002.md", "本章追逐")
    frozen = request(root)
    sources = [item for item in frozen.sources if item.get("text")]
    if reverse:
        sources.reverse()
    actions = iter([*({"action": "read_source", "source_id": item["source_id"]} for item in sources),
                    conclusion("setup", [item["source_id"] for item in sources], sources[0]["text"])])
    inputs = []

    def execute(messages, **kwargs):
        inputs.append(deepcopy(messages))
        return json.dumps(next(actions), ensure_ascii=False)

    before = tree(root)
    untouched = asdict(frozen)
    result = expert_api()(frozen, execute_step=execute, read_source=read_combat_source)
    assert result.reply == ("邻章谈判" if reverse else "本章追逐")
    assert result.evidence_refs == tuple(item["source_id"] for item in sources)
    assert result.project_id == "book" and result.job_id == "job-1"
    assert result.result_id and asdict(frozen) == untouched and tree(root) == before
    assert sources[0]["text"] not in inputs[0][-1].content
    assert sources[0]["text"] in inputs[1][-1].content


@pytest.mark.parametrize("verdict", ["noncombat", "insufficient"])
def test_expert_legal_free_text_verdicts(tmp_path, verdict):
    result = expert_api()(request(book(tmp_path)), execute_step=lambda *a, **k: json.dumps(conclusion(verdict)),
                          read_source=read_combat_source)
    assert result.verdict == verdict and result.reply == "选择谈判冲突，保留技术代价。"


@pytest.mark.parametrize("action", [{"action": "confirm"}, {"action": "publish"},
    {"action": "consult_combat"}, {"action": "read_source", "path": "../other"},
    {"action": "read_source", "source_id": "../../project.json"},
    {**conclusion(), "project_id": "other"}, conclusion(refs=["not-read"])])
def test_expert_rejects_authority_path_recursion_and_unread_refs(tmp_path, action):
    root = book(tmp_path)
    before = tree(root)
    with pytest.raises(ValueError):
        expert_api()(request(root), execute_step=lambda *a, **k: json.dumps(action), read_source=read_combat_source)
    assert tree(root) == before


def test_expert_budget_returns_unknown_without_invented_conclusion(tmp_path):
    frozen = request(book(tmp_path))
    source_id = frozen.sources[0]["source_id"]
    result = expert_api()(frozen, execute_step=lambda *a, **k: json.dumps({"action": "read_source", "source_id": source_id}),
                          read_source=read_combat_source)
    assert result.verdict == "insufficient" and result.unknowns
    assert "预算" in result.reply and result.evidence_refs == ()


class DelegationClient:
    def __init__(self, *, autonomous=False, error=None):
        self.autonomous, self.error, self.calls = autonomous, error, []

    def complete(self, messages, **kwargs):
        self.calls.append((deepcopy(messages), kwargs))
        expert = "你是战斗编排专家" in messages[0].content
        if expert:
            if self.error:
                raise self.error
            return json.dumps(conclusion("insufficient"), ensure_ascii=False)
        consulted = any("combat-result-" in item.content for item in messages)
        return json.dumps({"action": "consult_combat"} if self.autonomous and not consulted
                          else {"action": "finish", "reply": "讨论结果"}, ensure_ascii=False)


@pytest.mark.parametrize("chapter", [None, 2])
@pytest.mark.parametrize("selection", ["autonomous", "explicit", "none"])
def test_main_autonomous_explicit_and_no_delegation_capture_every_step(tmp_path, chapter, selection):
    root = book(tmp_path)
    client = DelegationClient(autonomous=selection == "autonomous")
    runtime = WriterAgentRuntime(root, "book", client_factory=lambda: client)
    try:
        options = {"requested_expert": "combat"} if selection == "explicit" else {}
        # 相同战斗字词，默认是否调用由模型决策，不走关键词分支。
        job = finish(runtime, runtime.submit("战斗技术与冲突讨论", chapter, **options))
        assert job.status == "completed", job.error
        results = job.combat_results
        assert len(results) == (0 if selection == "none" else 1)
        assert job.requested_expert == ("combat" if selection == "explicit" else None)
        assert len(job.step_snapshots) == len(client.calls)
        for snapshot, (messages, kwargs) in zip(job.step_snapshots, client.calls):
            actual = [item["content_snapshot"] for item in snapshot["sources"] if item["source_ref"].startswith("message:")]
            assert actual == [item.content for item in messages]
            assert snapshot["output"] and kwargs["max_tokens"] == 5000
        assert runtime.story.view()["candidate"] is None and runtime.store.current(2) is None
        if results:
            assert any(item["input"]["action"] == "consult_combat" for item in job.tool_trace)
            assert results[0]["job_id"] == job.job_id
    finally:
        runtime._pool.shutdown()


@pytest.mark.parametrize("error", [RuntimeError("provider failure"), CancelledError("cancelled")])
def test_failure_and_cancel_never_create_candidate_or_draft(tmp_path, error):
    root = book(tmp_path)
    client = DelegationClient(error=error)
    runtime = WriterAgentRuntime(root, "book", client_factory=lambda: client)
    try:
        job = finish(runtime, runtime.submit("请专家看", None, requested_expert="combat"))
        assert job.status == "failed" and job.retryable
        assert runtime.story.view()["candidate"] is None and runtime.story.view()["confirmed"] is None
        assert not list(root.rglob("*.md"))
    finally:
        runtime._pool.shutdown()


def test_retry_uses_original_sources_after_live_change_and_restart(tmp_path):
    root = book(tmp_path)
    write(root, "production/final_chapters/chapter_002.md", "冻结旧稿")
    client = DelegationClient(error=RuntimeError("retry me"))
    runtime = WriterAgentRuntime(root, "book", client_factory=lambda: client)
    failed = finish(runtime, runtime.submit("专家研究", 2, requested_expert="combat"))
    runtime._pool.shutdown()
    assert failed.status == "failed"
    write(root, "production/final_chapters/chapter_002.md", "最新哨兵")
    write(root, ".creative_os/writer/drafts/chapter_002.jsonl", "后来损坏的草稿 JSON，不应在冻结重试中读取")
    client = DelegationClient()
    runtime = WriterAgentRuntime(root, "book", client_factory=lambda: client)
    try:
        retried = finish(runtime, runtime.retry(failed.job_id, chapter_number=2, session_id=failed.session_id))
        assert retried.status == "completed", retried.error
        assert retried.combat_context == failed.combat_context
        assert "冻结旧稿" in json.dumps(retried.combat_context, ensure_ascii=False)
        assert "最新哨兵" not in "\n".join(item.content for messages, _ in client.calls for item in messages)
    finally:
        runtime._pool.shutdown()


def test_duplicate_project_identity_rejected_before_any_model(tmp_path):
    root = book(tmp_path)
    other = tmp_path / "alias"
    other.mkdir()
    write(other, "project.json", json.dumps({"id": "book"}))
    client = DelegationClient()
    runtime = WriterAgentRuntime(root, "book", client_factory=lambda: client)
    try:
        with pytest.raises(ValueError):
            runtime.submit("专家研究", None, requested_expert="combat")
        assert client.calls == []
    finally:
        runtime._pool.shutdown()


def test_large_context_does_not_break_ordinary_analysis_but_delegation_fails(tmp_path):
    root = book(tmp_path)
    write(root, "production/final_chapters/chapter_002.md", "文" * 12001)
    client = DelegationClient()
    runtime = WriterAgentRuntime(root, "book", client_factory=lambda: client)
    try:
        ordinary = finish(runtime, runtime.submit("普通分析", 2))
        assert ordinary.status == "completed", ordinary.error
        delegated = finish(runtime, runtime.submit("专家分析", 2, requested_expert="combat"))
        assert delegated.status == "failed" and "required_combat_context_budget_exceeded" in delegated.error
        assert not delegated.combat_results and runtime.store.current(2) is None
    finally:
        runtime._pool.shutdown()


def test_repeat_delegation_is_rejected_without_writes(tmp_path):
    class RepeatClient(DelegationClient):
        def complete(self, messages, **kwargs):
            if "你是战斗编排专家" in messages[0].content:
                return super().complete(messages, **kwargs)
            return '{"action":"consult_combat"}'

    root = book(tmp_path)
    runtime = WriterAgentRuntime(root, "book", client_factory=RepeatClient)
    try:
        job = finish(runtime, runtime.submit("研究", None))
        assert job.status == "failed" and job.error == "combat_delegation_limit"
        assert len(job.combat_results) == 1 and runtime.story.view()["candidate"] is None
    finally:
        runtime._pool.shutdown()


@pytest.mark.parametrize("limit", ["source", "total", "reads", "input"])
def test_expert_each_budget_is_enforced(tmp_path, monkeypatch, limit):
    from dataclasses import replace
    expert = expert_api()
    module = importlib.import_module("creative_os.combat_agent")
    root = book(tmp_path)
    write(root, "production/final_chapters/chapter_002.md", "证据")
    frozen = request(root)
    source_id = next(item["source_id"] for item in frozen.sources if item.get("text"))
    if limit == "input":
        frozen = replace(frozen, instruction="长" * 100001)
    else:
        monkeypatch.setattr(module, {"source": "MAX_SOURCE_CHARS", "total": "MAX_TOTAL_CHARS", "reads": "MAX_READS"}[limit], 0)
    calls = []

    def execute(*args, **kwargs):
        calls.append(1)
        return json.dumps({"action": "read_source", "source_id": source_id})

    result = expert(frozen, execute_step=execute, read_source=read_combat_source)
    assert result.verdict == "insufficient" and result.unknowns
    assert result.evidence_refs == ()
    if limit == "input":
        assert calls == []


def test_actual_read_body_and_runtime_records_are_captured(tmp_path, monkeypatch):
    from creative_os.runtime.runner import RuntimeRunner
    root = book(tmp_path)
    write(root, "production/final_chapters/chapter_002.md", "只在读取后进入专家的哨兵")
    records = []

    class ReadingClient(DelegationClient):
        def complete(self, messages, **kwargs):
            if "你是战斗编排专家" not in messages[0].content:
                return super().complete(messages, **kwargs)
            self.calls.append((deepcopy(messages), kwargs))
            header = json.loads(messages[1].content)
            source_id = next(item["source_id"] for item in header["sources"] if item.get("usage") == "included")
            return json.dumps({"action": "read_source", "source_id": source_id} if len(messages) == 2
                              else conclusion("setup", [source_id]), ensure_ascii=False)

    client = ReadingClient()
    monkeypatch.setattr("creative_os.agent_runtime.RuntimeRunner", lambda: RuntimeRunner(record_sink=records.append))
    runtime = WriterAgentRuntime(root, "book", client_factory=lambda: client)
    try:
        job = finish(runtime, runtime.submit("分析", 2, requested_expert="combat"))
        assert job.status == "completed", job.error
        assert len(records) == 3 and all(record.status == "succeeded" for record in records)
        assert [record.capability for record in records] == ["combat-expert", "combat-expert", "chapter-analysis-agent"]
        expert_calls = [messages for messages, _ in client.calls if "你是战斗编排专家" in messages[0].content]
        assert "只在读取后进入专家的哨兵" not in str(expert_calls[0])
        assert "只在读取后进入专家的哨兵" in expert_calls[1][-1].content
        assert job.combat_results[0]["evidence_refs"]
        source = next(item for item in job.step_snapshots[1]["sources"] if item.get("reason") == "read")
        assert source["hash"] and source["evidence_ref"] == job.combat_results[0]["evidence_refs"][0]
        assert source["usage"] == "recorded"
    finally:
        runtime._pool.shutdown()


@pytest.mark.parametrize("chapter", [None, 2])
def test_requested_expert_travels_actual_http_routes(tmp_path, chapter):
    from http.client import HTTPConnection
    from threading import Thread
    from creative_os.project_registry import ProjectRegistry
    from creative_os.web_workspace import create_server
    from test_story_http import EmptyWorkspace

    book(tmp_path)
    client = DelegationClient()
    registry = ProjectRegistry(tmp_path, client_factory=lambda: client)
    server = create_server(EmptyWorkspace(None, "none"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        runtime = registry.get("book")["agent_runtime"]
        scope = {"scope": "story"} if chapter is None else {"chapter_number": chapter}
        payload = {"project_id": "book", "session_id": runtime.conversations.read(chapter)["session_id"],
                   **scope, "instruction": "研究", "requested_expert": "combat"}
        path = "/p/book/api/story/intents" if chapter is None else "/p/book/api/agent/intents"
        connection = HTTPConnection(*server.server_address, timeout=5)
        connection.request("POST", path, json.dumps(payload), {"Content-Type": "application/json"})
        response = connection.getresponse()
        value = json.loads(response.read())
        connection.close()
        assert response.status == 202, value
        assert value["requested_expert"] == "combat"
        runtime = registry.get("book")["agent_runtime"]
        job = finish(runtime, runtime.get(value["job_id"]))
        assert job.status == "completed" and len(job.combat_results) == 1, job.error
        if chapter is None:
            from urllib.parse import urlencode
            query = {"project_id": "book", "scope": "story", "session_id": job.session_id,
                     "job_id": job.job_id, "step": job.step_snapshots[0]["step"]}
            connection = HTTPConnection(*server.server_address, timeout=5)
            connection.request("GET", "/p/book/api/story/sources?" + urlencode(query))
            response = connection.getresponse()
            snapshot = json.loads(response.read())
            connection.close()
            assert response.status == 200 and snapshot["output"], snapshot
    finally:
        server.shutdown(); server.server_close(); worker.join(); registry.close()


def test_story_retry_read_tools_do_not_replace_frozen_setting(tmp_path):
    from test_story_agent import ScriptClient
    root = book(tmp_path)
    client = ScriptClient([{"action": "read_confirmed"}, "坏包"])
    runtime = WriterAgentRuntime(root, "book", client_factory=lambda: client)
    try:
        store = runtime.story
        first = store.propose(store.session_id, [{"key": "world", "title": "世界", "text": "冻结设定"}], [],
                              expected_revision=0, actor="作者", operation_id="first")
        store.confirm(store.session_id, 1, first["hash"], expected_confirmed_version=0, actor="作者", operation_id="confirm1")
        failed = finish(runtime, runtime.submit("继续讨论", None))
        assert failed.status == "failed"
        second = store.propose(store.session_id, [{"key": "world", "title": "世界", "text": "最新设定哨兵"}], [],
                               expected_revision=1, actor="作者", operation_id="second")
        store.confirm(store.session_id, 2, second["hash"], expected_confirmed_version=1, actor="作者", operation_id="confirm2")
        client = ScriptClient([{"action": "read_confirmed"}, {"action": "finish", "reply": "旧材料重试"}])
        runtime.client_factory = lambda: client
        retried = finish(runtime, runtime.retry(failed.job_id, chapter_number=None, session_id=failed.session_id))
        assert retried.status == "completed", retried.error
        actual = "\n".join(item.content for messages in client.calls for item in messages)
        assert "冻结设定" in actual and "最新设定哨兵" not in actual
        assert store.view()["confirmed"]["version"] == 2
    finally:
        runtime._pool.shutdown()
