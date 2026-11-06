"""战斗建议采用与作者确认；只使用 guard 下临时项目和现有会话存储。"""

from copy import deepcopy
from dataclasses import asdict
import importlib
import json
import pytest

from creative_os.agent_conversation_store import AgentConversationStore
from creative_os.agent_runtime import AgentJob
from creative_os.combat_agent import run_combat_expert
from creative_os.combat_context import build_combat_context, read_combat_source
from creative_os.combat_model import CombatResult, CombatScope
from creative_os.story_architecture_command import story_commands
from creative_os.story_architecture_store import StoryArchitectureStore, atomic_json, content_hash, render_story
from creative_os.story_context import freeze_confirmed_story
from creative_os.workspace_command import CommandRequest
from test_combat_context import book, write


def stage(store, result_id="combat-result-one", **overrides):
    try:
        api = importlib.import_module("creative_os.combat_story_candidate").stage_combat_candidate
    except ModuleNotFoundError:
        pytest.fail("战斗建议尚不能进入故事候选")
    return api(store, result_id, **{"expected_revision": 0, "actor": "作者", "operation_id": "adopt", **overrides})


@pytest.fixture
def setup(tmp_path):
    root = book(tmp_path)
    write(root, "production/final_chapters/chapter_002.md", "冻结来源正文")
    conversations = AgentConversationStore(root, "book")
    session = conversations.read(2)
    frozen = build_combat_context(root, "book", CombatScope((2,), "第二章冲突研究"),
                                 task_id="job-one", session_id=session["session_id"], instruction="研究冲突")
    source = next(item for item in frozen.sources if item.get("text"))
    result = CombatResult("combat-result-one", "book", "job-one", "noncombat", "计划通过谈判打破僵局。",
                          ("也可撤退。",), ("提前展示代价。",), (source["source_id"],), ("结局尚待作者决定。",), frozen.scope)
    job = AgentJob("job-one", "completed", "完成", 2, mode="analyze", project_id="book",
                   session_id=session["session_id"], combat_context=asdict(frozen), combat_results=(asdict(result),))
    session["jobs"][job.job_id] = asdict(job)
    conversations.write(session)
    return StoryArchitectureStore(root, "book"), conversations, session, source


def command(store, action, payload, *, actor="作者", key="command"):
    return story_commands(store).execute(CommandRequest(action, key, actor,
        {"project_id": "book", "scope": "story", "session_id": store.session_id}, payload, idempotency_key=key))


def test_merge_preserves_other_blocks_questions_and_unconfirmed_source(setup):
    store, _, _, source = setup
    blocks = [{"key": "core", "title": "核心", "text": "原有设定"},
              {"key": "other-plan", "title": "另一方案", "text": "保留其他建议"}]
    store.propose(store.session_id, blocks, ["未决问题"], expected_revision=0, actor="agent", operation_id="base")
    candidate = stage(store, expected_revision=1)
    assert candidate["content"]["blocks"][:2] == blocks
    assert candidate["content"]["open_questions"] == ["未决问题"]
    block = candidate["content"]["blocks"][-1]
    assert block["key"] == "combat-plan:combat-result-one" and "未来" in block["text"]
    assert "谈判" in block["text"] and "撤退" in block["text"] and "结局尚待" in block["text"]
    plan = candidate["content"]["combat_plans"][0]
    assert plan["block_key"] == block["key"] and plan["project_id"] == "book"
    assert plan["scope"] == {"chapter_numbers": [2], "purpose": "第二章冲突研究"}
    assert plan["evidence_refs"] == [source["source_id"]]
    assert plan["source_hashes"] == {source["source_id"]: source["hash"]}
    assert plan["author_revised"] is False and plan["evidence_basis"] == "expert_original"
    assert store.view()["confirmed"] is None and freeze_confirmed_story(store.root, "book") is None


def test_cas_and_idempotency_survive_restart_and_other_edits(setup):
    store, _, _, _ = setup
    first = stage(store)
    assert stage(StoryArchitectureStore(store.root, "book")) == first
    with pytest.raises(ValueError, match="candidate_conflict"):
        stage(store, operation_id="stale")
    store.propose(store.session_id, first["content"]["blocks"], ["作者新增"], expected_revision=1, actor="作者", operation_id="edit")
    assert stage(store) == first and store.view()["candidate"]["revision"] == 2
    with pytest.raises(ValueError, match="idempotency_conflict"):
        stage(store, expected_revision=2)


@pytest.mark.parametrize("field,value", [("project_id", "foreign"), ("job_id", "forged"),
    ("result_id", "other-result"), ("evidence_refs", ["forged-source"]),
    ("evidence_refs", ["forged-source", "forged-source"]),
    ("scope", {"chapter_numbers": [3], "purpose": "伪造范围"})])
def test_rejects_foreign_or_forged_persisted_result_without_candidate(setup, field, value):
    store, conversations, session, _ = setup
    session["jobs"]["job-one"]["combat_results"][0][field] = value
    conversations.write(session)
    with pytest.raises(ValueError):
        stage(store)
    assert store.view()["candidate"] is None


def test_command_reads_server_result_and_rejects_client_result_payload(setup):
    store, _, _, _ = setup
    accepted = command(store, "adopt_combat_candidate", {"result_id": "combat-result-one", "expected_revision": 0})
    assert accepted.status.value == "accepted"
    assert store.view()["candidate"]["content"]["combat_plans"][0]["result_id"] == "combat-result-one"
    rejected = command(store, "adopt_combat_candidate", {"result_id": "combat-result-one", "expected_revision": 1, "reply": "伪造内容"}, key="forged")
    assert rejected.error.code == "story_payload_invalid" and store.view()["candidate"]["revision"] == 1


def test_author_edit_marks_revised_keeps_provenance_and_delete_removes_link(setup):
    store, _, _, _ = setup
    first = stage(store)
    blocks = deepcopy(first["content"]["blocks"])
    blocks[0]["text"] = "作者改为追逐，与原建议不同。"
    edited = command(store, "edit_story_candidate", {"blocks": blocks, "open_questions": [], "expected_revision": 1}, key="edit")
    assert edited.status.value == "accepted"
    second = store.view()["candidate"]
    old, new = first["content"]["combat_plans"][0], second["content"]["combat_plans"][0]
    assert second["hash"] != first["hash"] and new["author_revised"] is True
    assert new["source_hashes"] == old["source_hashes"] and new["evidence_basis"] == "expert_original"
    assert "作者修订" in second["text"] and "未来" in second["text"]
    assert command(store, "edit_story_candidate", {"blocks": [{"key": "core", "title": "核心", "text": "新设定"}],
        "open_questions": [], "expected_revision": 2}, key="delete").status.value == "accepted"
    assert store.view()["candidate"]["content"]["combat_plans"] == []


def test_confirmation_requires_author_current_revision_and_hash(setup):
    store, _, _, _ = setup
    first = stage(store)
    payload = {"revision": 1, "hash": first["hash"], "expected_confirmed_version": 0}
    assert command(store, "confirm_story_candidate", payload, actor="agent", key="model").error.code == "story_author_required"
    with pytest.raises(ValueError, match="story_author_required"):
        store.confirm(store.session_id, 1, first["hash"], expected_confirmed_version=0, actor="agent", operation_id="direct-model")
    assert command(store, "confirm_story_candidate", {**payload, "hash": "stale"}, key="wrong").error.code == "candidate_conflict"
    assert store.view()["confirmed"] is None
    assert command(store, "confirm_story_candidate", payload, key="confirm").status.value == "accepted"
    confirmed = store.view()["confirmed"]
    assert (confirmed["version"], confirmed["revision"], confirmed["hash"]) == (1, 1, first["hash"])
    assert confirmed["content"]["combat_plans"] == first["content"]["combat_plans"]


def test_chat_approval_does_not_confirm(setup):
    store, conversations, session, _ = setup
    stage(store)
    session["messages"].append({"role": "user", "content": "认可，就这样，确认吧"})
    conversations.write(session)
    assert store.view()["confirmed"] is None


@pytest.mark.parametrize("confirmed_only", [False, True])
def test_old_aggregate_baseline_and_empty_scope_are_explicit(setup, confirmed_only):
    store, conversations, session, _ = setup
    raw = session["jobs"]["job-one"]
    raw["combat_context"]["scope"] = {"chapter_numbers": [], "purpose": "全书研究"}
    raw["combat_results"][0]["scope"] = raw["combat_context"]["scope"]
    conversations.write(session)
    if confirmed_only:
        base = store.propose(store.session_id, [{"key": "core", "title": "核心", "text": "旧正式设定"}], ["旧问题"],
                             expected_revision=0, actor="作者", operation_id="base")
        store.confirm(store.session_id, 1, base["hash"], expected_confirmed_version=0, actor="作者", operation_id="confirm")
        data = store._read()
        data["revisions"] = []
        atomic_json(store.path, data)
    candidate = stage(store)
    assert candidate["content"]["combat_plans"][0]["scope"]["chapter_numbers"] == []
    if confirmed_only:
        assert candidate["content"]["blocks"][0]["text"] == "旧正式设定"
        assert candidate["content"]["open_questions"] == ["旧问题"]
    else:
        assert any("其他正式设定" in question for question in candidate["content"]["open_questions"])


def test_retry_result_uses_current_job_while_sources_keep_original_identity(setup):
    store, conversations, session, _ = setup
    original = session["jobs"]["job-one"]
    original["status"] = "failed"
    retried = deepcopy(original)
    original["combat_results"] = []
    retried.update(job_id="job-retry", retry_of="job-one", status="completed")
    retried["combat_results"][0]["job_id"] = "job-retry"
    session["jobs"]["job-retry"] = retried
    conversations.write(session)
    assert stage(store)["content"]["combat_plans"][0]["result_id"] == "combat-result-one"
    retried["combat_results"][0]["job_id"] = "job-one"
    conversations.write(session)
    with pytest.raises(ValueError):
        stage(store, expected_revision=1, operation_id="forged-retry")


def test_legacy_operation_receipt_still_replays_without_new_metadata(tmp_path):
    store = StoryArchitectureStore(tmp_path, "legacy")
    content = {"blocks": [{"key": "core", "title": "核心", "text": "旧设定"}], "open_questions": []}
    candidate = {"revision": 1, "hash": content_hash(content), "content": content,
                 "text": render_story(content), "actor": "作者", "created_at": "old-time"}
    data = store._read()
    data["revisions"] = [candidate]
    data["operations"]["old-propose"] = {"fingerprint": content_hash({"action": "propose", "content": content,
        "expected_revision": 0, "actor": "作者"}), "result": candidate}
    atomic_json(store.path, data)
    assert store.propose(store.session_id, content["blocks"], [], expected_revision=0,
                         actor="作者", operation_id="old-propose") == candidate


def test_replacing_same_plan_keeps_other_plan_and_its_provenance(setup):
    store, conversations, session, _ = setup
    first = stage(store)
    other = deepcopy(session["jobs"]["job-one"]["combat_results"][0])
    other.update(result_id="combat-result-two", reply="另一条未来建议")
    session["jobs"]["job-one"]["combat_results"] = [*session["jobs"]["job-one"]["combat_results"], other]
    conversations.write(session)
    second = stage(store, "combat-result-two", expected_revision=1, operation_id="other")
    replaced = stage(store, expected_revision=2, operation_id="replace")
    assert len(replaced["content"]["blocks"]) == 2
    assert replaced["content"]["blocks"][1] == second["content"]["blocks"][1]
    plans = {plan["result_id"]: plan for plan in replaced["content"]["combat_plans"]}
    assert plans["combat-result-two"] == second["content"]["combat_plans"][1]
    assert plans["combat-result-one"] == first["content"]["combat_plans"][0]


def test_failed_atomic_save_leaves_candidate_and_operation_uncommitted(setup, monkeypatch):
    store, _, _, _ = setup
    module = importlib.import_module("creative_os.story_architecture_store")
    original = module.atomic_json
    monkeypatch.setattr(module, "atomic_json", lambda *args: (_ for _ in ()).throw(OSError("模拟保存失败")))
    with pytest.raises(OSError, match="模拟保存失败"):
        stage(store)
    assert store.view()["candidate"] is None and store._read()["operations"] == {}
    monkeypatch.setattr(module, "atomic_json", original)
    candidate = stage(store)
    assert candidate["revision"] == 1
    assert (store.root / "production/final_chapters/chapter_002.md").read_text(encoding="utf-8") == "冻结来源正文"
    assert not (store.root / ".creative_os/writer").exists()


def test_metadata_is_inside_integrity_hash_and_confirmed_snapshot(setup):
    store, _, _, _ = setup
    candidate = stage(store)
    confirmed = store.confirm(store.session_id, 1, candidate["hash"], expected_confirmed_version=0,
                              actor="作者", operation_id="confirm")
    data = store._read()
    data["revisions"][-1]["content"]["combat_plans"][0]["author_revised"] = True
    atomic_json(store.path, data)
    with pytest.raises(ValueError, match="story_integrity_error"):
        store.view()
    assert confirmed["content"]["combat_plans"][0]["author_revised"] is False


def test_real_expert_duplicate_refs_adopt_in_first_seen_order_without_changing_result(setup):
    store, conversations, session, _ = setup
    write(store.root, "production/final_chapters/chapter_001.md", "邻章冻结来源")
    frozen = build_combat_context(store.root, "book", CombatScope((2,), "第二章冲突研究"),
                                 task_id="job-one", session_id=session["session_id"], instruction="研究冲突")
    target, adjacent = [source for source in frozen.sources if source.get("text")]
    refs = [adjacent["source_id"], target["source_id"], adjacent["source_id"], target["source_id"]]
    actions = iter([{"action": "read_source", "source_id": adjacent["source_id"]},
                    {"action": "read_source", "source_id": target["source_id"]},
                    {"action": "finish", "verdict": "noncombat", "reply": "未来建议通过谈判化解冲突。",
                     "alternatives": [], "foreshadowing": [], "evidence_refs": refs, "unknowns": []}])
    result = run_combat_expert(frozen,
        execute_step=lambda *args, **kwargs: json.dumps(next(actions), ensure_ascii=False),
        read_source=read_combat_source)
    assert result.evidence_refs == tuple(refs)
    session["jobs"]["job-one"].update(combat_context=asdict(frozen), combat_results=[asdict(result)])
    conversations.write(session)
    persisted = conversations.read(2)["jobs"]["job-one"]["combat_results"][0]

    candidate = stage(store, result.result_id)
    plan = candidate["content"]["combat_plans"][0]
    assert plan["evidence_refs"] == [adjacent["source_id"], target["source_id"]]
    assert plan["source_hashes"] == {adjacent["source_id"]: adjacent["hash"], target["source_id"]: target["hash"]}
    assert plan["result_hash"] == content_hash(persisted)
    assert plan["result_hash"] != content_hash({**persisted, "evidence_refs": plan["evidence_refs"]})
    assert conversations.read(2)["jobs"]["job-one"]["combat_results"][0] == persisted
    assert stage(StoryArchitectureStore(store.root, "book"), result.result_id) == candidate
