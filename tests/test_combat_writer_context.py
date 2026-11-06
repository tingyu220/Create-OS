"""战斗计划只由确认快照按章进入真实 Fake 模型消息，写稿仍经 Proposal。"""

from copy import deepcopy
from dataclasses import asdict
import importlib
import json
from threading import Event

import pytest

from creative_os.agent_conversation_store import AgentConversationStore
from creative_os.agent_runtime import AgentJob, WriterAgentRuntime
from creative_os.combat_context import build_combat_context
from creative_os.combat_model import CombatResult, CombatScope
from creative_os.combat_story_candidate import stage_combat_candidate
from creative_os.story_architecture_store import StoryArchitectureStore
from test_agent_proposal import finish, review
from test_combat_context import book, write
from test_writer_context_sources import details


@pytest.fixture
def runtimes():
    active = []
    yield active
    for runtime in active:
        runtime._pool.shutdown(wait=True)


def create_story(root, project_id="book", plans=(("selected", (2,), "本章确认战斗哨兵"),)):
    """经原结果存储与任务3采用接口建立完整领域数据，不伪造确认 DTO。"""
    write(root, "production/final_chapters/chapter_002.md", "正式来源正文")
    store = StoryArchitectureStore(root, project_id)
    store.propose(store.session_id, [{"key": "core", "title": "普通设定", "text": "普通设定哨兵"}], [],
                  expected_revision=0, actor="作者", operation_id="core")
    conversations = AgentConversationStore(root, project_id)
    for index, (result_id, chapters, text) in enumerate(plans, 1):
        session = conversations.read(2)
        job_id = "source-job-" + result_id
        frozen = build_combat_context(root, project_id, CombatScope(chapters, "冲突研究"),
            task_id=job_id, session_id=session["session_id"], instruction="研究")
        source = next(item for item in frozen.sources if item.get("text"))
        result = CombatResult(result_id, project_id, job_id, "noncombat", text, (), (),
                              (source["source_id"],), (), frozen.scope)
        job = AgentJob(job_id, "completed", "完成", 2, mode="analyze", project_id=project_id, session_id=session["session_id"],
                       combat_context=asdict(frozen), combat_results=(asdict(result),))
        session["jobs"][job_id] = asdict(job)
        conversations.write(session)
        stage_combat_candidate(store, result_id, expected_revision=index, actor="作者", operation_id="adopt-" + result_id)
    return store


def confirm(store, key="confirm"):
    candidate = store.view()["candidate"]
    return store.confirm(store.session_id, candidate["revision"], candidate["hash"],
        expected_confirmed_version=(store.view()["confirmed"] or {}).get("version", 0), actor="作者", operation_id=key)


def writer(root, runtimes, project_id="book", mode="act", callback=None):
    calls = []

    class FakeClient:
        def complete(self, messages, **kwargs):
            calls.append(messages)
            if callback:
                callback()
            return json.dumps({"action": "finish", "reply": "分析结论"}, ensure_ascii=False) if mode == "analyze" else "《第2章》\n候选写作正文"

    runtime = WriterAgentRuntime(root, project_id, client_factory=lambda: FakeClient())
    runtimes.append(runtime)
    return runtime, calls


@pytest.mark.parametrize("mode", ["analyze", "act"])
def test_actual_messages_include_only_applicable_confirmed_plan_and_provenance(tmp_path, runtimes, mode):
    root = book(tmp_path)
    store = create_story(root, plans=(("selected", (2,), "本章确认战斗哨兵"),
        ("other", (4,), "异章计划禁止泄漏哨兵"), ("research", (), "全书研究禁止应用哨兵")))
    frozen = confirm(store)
    blocks = deepcopy(frozen["content"]["blocks"])
    blocks[1]["text"] = "未确认候选禁止泄漏哨兵"
    store.propose(store.session_id, blocks, [], expected_revision=4, actor="作者", operation_id="candidate")
    runtime, calls = writer(root, runtimes, mode=mode)
    job = finish(runtime, runtime.submit("按确认内容处理本章", 2, mode=mode, require_confirmed_combat=mode == "act"))
    prompt = "\n".join(message.content for message in calls[0])
    assert "本章确认战斗哨兵" in prompt and "普通设定哨兵" in prompt
    assert all(text not in prompt for text in ("异章计划禁止泄漏哨兵", "全书研究禁止应用哨兵", "未确认候选禁止泄漏哨兵"))
    assert "未来创作计划，不是已发生事实" in prompt
    source = next(item for item in details(runtime, job) if item["label"] == "已确认战斗计划")
    assert source["version"] == 1 and source["story_hash"] == frozen["hash"]
    assert source["source_ref"] in prompt and frozen["hash"] in prompt and "version=1" in prompt
    assert source["combat_plan"]["result_id"] == "selected"
    assert source["combat_plan"]["source_hashes"] == frozen["content"]["combat_plans"][0]["source_hashes"]
    location = source["message_location"]
    assert calls[0][location["index"]].content[location["start"]:location["end"]] == source["content_snapshot"]
    assert "本章确认战斗哨兵" in source["content_snapshot"]
    assert job.story_context["content"] == frozen["content"]


@pytest.mark.parametrize("chapters", [(4,), ()])
def test_nonapplicable_and_book_research_never_enter_messages(tmp_path, runtimes, chapters):
    root = book(tmp_path)
    store = create_story(root, plans=(("excluded", chapters, "不适用战斗哨兵"),))
    confirm(store)
    runtime, calls = writer(root, runtimes)
    job = finish(runtime, runtime.submit("普通写作", 2, mode="act"))
    prompt = "\n".join(message.content for message in calls[0])
    assert "普通设定哨兵" in prompt and "不适用战斗哨兵" not in prompt
    assert not any(item["label"] == "已确认战斗计划" for item in details(runtime, job))


def test_queued_job_keeps_full_version_when_author_confirms_again(tmp_path, runtimes):
    root = book(tmp_path)
    store = create_story(root)
    first = confirm(store)
    runtime, calls = writer(root, runtimes)
    release = Event()
    runtime._pool.submit(lambda: release.wait(10))
    try:
        job = runtime.submit("按确认版本写作", 2, mode="act")
        blocks = deepcopy(first["content"]["blocks"])
        blocks[1]["text"] = "运行中新确认禁止泄漏哨兵"
        store.propose(store.session_id, blocks, [], expected_revision=2, actor="作者", operation_id="new")
        confirm(store, "confirm-new")
        release.set()
        job = finish(runtime, job)
    finally:
        release.set()
    prompt = "\n".join(message.content for message in calls[0])
    assert "本章确认战斗哨兵" in prompt and "运行中新确认禁止泄漏哨兵" not in prompt
    assert job.story_context["version"] == 1 and job.story_context["content"] == first["content"]
    source = next(item for item in details(runtime, job) if item["label"] == "已确认战斗计划")
    assert source["version"] == 1 and source["story_hash"] == first["hash"]


def test_two_books_never_share_plan_content_or_sources(tmp_path, runtimes):
    for project_id, sentinel in (("first", "甲书计划哨兵"), ("second", "乙书计划哨兵")):
        root = book(tmp_path, project_id)
        store = create_story(root, project_id, (("same-id", (2,), sentinel),))
        confirm(store)
        runtime, calls = writer(root, runtimes, project_id)
        job = finish(runtime, runtime.submit("写本书本章", 2, mode="act"))
        prompt = "\n".join(message.content for message in calls[0])
        assert sentinel in prompt
        assert ("乙书计划哨兵" if project_id == "first" else "甲书计划哨兵") not in prompt
        source = next(item for item in details(runtime, job) if item["label"] == "已确认战斗计划")
        assert source["combat_plan"]["project_id"] == project_id
        assert source["source_ref"].startswith("story-confirmed:" + project_id + ":")


def test_unconfirmed_adopted_plan_requires_confirmation_but_legacy_writing_works(tmp_path, runtimes):
    root = book(tmp_path)
    create_story(root)
    runtime, calls = writer(root, runtimes)
    ordinary = finish(runtime, runtime.submit("普通旧项目写作", 2, mode="act"))
    assert "本章确认战斗哨兵" not in "\n".join(message.content for message in calls[0])
    assert ordinary.proposal_id and runtime.store.current(2) is None
    with pytest.raises(ValueError, match="story_confirmation_required"):
        runtime.submit("按采用方案写作", 2, mode="act", require_confirmed_combat=True)
    assert len(calls) == 1 and runtime.store.current(2) is None
    legacy, legacy_calls = writer(book(tmp_path, "legacy"), runtimes, "legacy")
    job = finish(legacy, legacy.submit("普通旧项目写作", 1, mode="act"))
    assert job.proposal_id and legacy_calls and legacy.store.current(1) is None


def test_explicit_plan_writing_needs_applicable_confirmed_plan(tmp_path, runtimes):
    root = book(tmp_path)
    store = create_story(root, plans=(("excluded", (4,), "异章计划"),))
    confirm(store)
    runtime, calls = writer(root, runtimes)
    with pytest.raises(ValueError, match="combat_plan_confirmation_required"):
        runtime.submit("采用计划", 2, mode="act", require_confirmed_combat=True)
    assert calls == []


def test_required_plan_budget_fails_without_model_or_draft(tmp_path, runtimes, monkeypatch):
    root = book(tmp_path)
    confirm(create_story(root))
    monkeypatch.setattr("creative_os.story_context.MAX_STORY_CONTEXT_CHARS", 50)
    runtime, calls = writer(root, runtimes)
    with pytest.raises(ValueError, match="required_story_context_budget_exceeded"):
        runtime.submit("必须完整使用确认计划", 2, mode="act")
    assert calls == [] and runtime.store.current(2) is None


def test_excluded_plan_does_not_consume_required_chapter_budget(tmp_path, runtimes, monkeypatch):
    root = book(tmp_path)
    store = create_story(root, plans=(("excluded", (4,), "异章大计划" * 100),))
    frozen = confirm(store)
    assert len(frozen["text"]) > 100
    monkeypatch.setattr("creative_os.story_context.MAX_STORY_CONTEXT_CHARS", 100)
    runtime, calls = writer(root, runtimes)
    job = finish(runtime, runtime.submit("普通本章写作", 2, mode="act"))
    assert "异章大计划" not in "\n".join(message.content for message in calls[0])
    assert "异章大计划" in job.story_context["text"]


@pytest.mark.parametrize("mode", ["analyze", "act"])
def test_total_input_budget_failure_is_explicit_and_never_calls_model(tmp_path, runtimes, mode):
    root = book(tmp_path)
    confirm(create_story(root))
    runtime, calls = writer(root, runtimes, mode=mode)
    job = runtime.submit("过长的作者指令" * 20000, 2, mode=mode)
    # 该任务必须失败；不使用要求成功的 finish 辅助函数。
    runtime._pool.shutdown(wait=True)
    job = runtime.get(job.job_id)
    assert job.status == "failed" and job.error == "required_story_context_budget_exceeded"
    assert calls == [] and runtime.store.current(2) is None


def test_confirmed_plan_still_requires_proposal_acceptance_to_write(tmp_path, runtimes):
    root = book(tmp_path)
    confirm(create_story(root))
    runtime, calls = writer(root, runtimes)
    rejected = finish(runtime, runtime.submit("写作第一份", 2, mode="act"))
    assert "本章确认战斗哨兵" in "\n".join(message.content for message in calls[0])
    assert runtime.store.current(2) is None
    assert review(runtime, rejected, "reject", "暂不采用").status == "accepted"
    assert runtime.store.current(2) is None
    accepted = finish(runtime, runtime.submit("再写一份", 2, mode="act"))
    assert review(runtime, accepted, "accept", key="accept").status == "accepted"
    assert runtime.store.current(2)[1] == "《第2章》\n候选写作正文"


def test_selection_uses_only_frozen_content_and_returns_independent_records(tmp_path):
    root = book(tmp_path)
    store = create_story(root, plans=(("selected", (2,), "本章确认战斗哨兵"), ("research", (), "全书研究哨兵")))
    frozen = confirm(store)
    try:
        select = importlib.import_module("creative_os.combat_context_selection").select_confirmed_combat
    except ModuleNotFoundError:
        pytest.fail("确认战斗范围选择接口尚未实现")
    selected = select(frozen, 2)
    assert isinstance(selected, tuple) and len(selected) == 1
    assert selected[0]["result_id"] == "selected" and "本章确认战斗哨兵" in selected[0]["text"]
    selected[0]["scope"]["chapter_numbers"].append(9)
    assert select(frozen, 9) == () and select(frozen, 4) == ()


@pytest.mark.parametrize("boundary", ["validate_submit", "submit"])
@pytest.mark.parametrize("original", ["none", "other_chapter", "legacy_text"])
def test_explicit_retry_rejects_missing_plan_in_original_snapshot_even_after_latest_confirmation(tmp_path, runtimes, boundary, original):
    root = book(tmp_path)
    store = create_story(root, plans=(("selected", (4,) if original == "other_chapter" else (2,), "原计划哨兵"),))
    frozen = confirm(store) if original != "none" else None

    def fail_once():
        if len(calls) == 1:
            raise RuntimeError("第一次 Fake 调用失败")

    runtime, calls = writer(root, runtimes, callback=fail_once)
    failed = runtime.submit("普通旧任务", 2, mode="act")
    runtime._futures[failed.job_id].result(timeout=10)
    failed = runtime.get(failed.job_id)
    assert failed.status == "failed" and len(calls) == 1
    if original == "legacy_text":
        # 模拟旧持久任务仅保存纯文本；不能从最新确认记录补回历史结构。
        runtime._set(failed.job_id, story_context={key: failed.story_context[key]
            for key in ("text", "version", "hash", "project_id", "source_ref")})
    if frozen is None:
        confirm(store)
    else:
        blocks = deepcopy(frozen["content"]["blocks"])
        blocks[1]["text"] = "后来确认不可补历史哨兵"
        store.propose(store.session_id, blocks, [], expected_revision=2, actor="作者", operation_id="latest")
        confirm(store, "confirm-latest")
    error = "story_confirmation_required" if original == "none" else "combat_plan_confirmation_required"
    before_jobs = set(runtime.conversations.read(2)["jobs"])
    with pytest.raises(ValueError, match=error):
        getattr(runtime, boundary)("显式采用计划重试", 2, mode="act", retry_of=failed.job_id,
            session_id=failed.session_id, require_confirmed_combat=True)
    assert len(calls) == 1 and runtime.store.current(2) is None
    assert set(runtime.conversations.read(2)["jobs"]) == before_jobs


def test_explicit_retry_with_applicable_frozen_plan_uses_original_after_new_confirmation(tmp_path, runtimes):
    root = book(tmp_path)
    store = create_story(root)
    frozen = confirm(store)

    def fail_once():
        if len(calls) == 1:
            raise RuntimeError("第一次 Fake 调用失败")

    runtime, calls = writer(root, runtimes, callback=fail_once)
    failed = runtime.submit("按确认计划写作", 2, mode="act", require_confirmed_combat=True)
    runtime._futures[failed.job_id].result(timeout=10)
    failed = runtime.get(failed.job_id)
    assert failed.status == "failed"
    blocks = deepcopy(frozen["content"]["blocks"])
    blocks[1]["text"] = "后来确认禁止替换原快照哨兵"
    store.propose(store.session_id, blocks, [], expected_revision=2, actor="作者", operation_id="latest")
    confirm(store, "confirm-latest")
    runtime.validate_submit("重试", 2, mode="act", retry_of=failed.job_id,
        session_id=failed.session_id, require_confirmed_combat=True)
    retried = finish(runtime, runtime.submit("重试", 2, mode="act", retry_of=failed.job_id,
        session_id=failed.session_id, require_confirmed_combat=True))
    assert retried.story_context == failed.story_context and retried.story_context["version"] == 1
    prompt = "\n".join(message.content for message in calls[-1])
    assert "本章确认战斗哨兵" in prompt and "后来确认禁止替换原快照哨兵" not in prompt
    assert retried.proposal_id and runtime.store.current(2) is None


@pytest.mark.parametrize("requested_expert", [None, "combat"])
def test_protocol_appended_input_over_budget_fails_before_any_model_call(tmp_path, runtimes, requested_expert):
    # 两个独立集合中建立相同内容，先测得包装开销，再确定性构造100001字符输入。
    for name in ("probe", "target"):
        (tmp_path / name).mkdir()
    probe_root = book(tmp_path / "probe")
    confirm(create_story(probe_root))
    probe, _ = writer(probe_root, runtimes, mode="analyze")
    baseline = finish(probe, probe.submit("x", 2, mode="analyze"))
    baseline_chars = sum(len(message["content"]) for message in baseline.main_input)
    root = book(tmp_path / "target")
    confirm(create_story(root))
    runtime, calls = writer(root, runtimes, mode="analyze")
    submitted = runtime.submit("x" * (100002 - baseline_chars), 2, mode="analyze", requested_expert=requested_expert)
    runtime._futures[submitted.job_id].result(timeout=10)
    failed = runtime.get(submitted.job_id)
    assert failed.main_input == ()
    assert failed.status == "failed" and failed.error == "required_story_context_budget_exceeded"
    assert calls == [] and runtime.store.current(2) is None and failed.proposal_id is None
