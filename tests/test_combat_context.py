"""战斗专家证据契约；全部读写仅发生在 pytest 临时书根。"""

import importlib
import json

import pytest


def api():
    try:
        return importlib.import_module("creative_os.combat_context"), importlib.import_module("creative_os.combat_model")
    except ModuleNotFoundError:
        pytest.fail("战斗上下文公共接口尚未实现")


def book(tmp_path, project_id="book"):
    root = tmp_path / project_id
    root.mkdir()
    write(root, "project.json", json.dumps({"id": project_id}))
    return root


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def build(root, numbers=(2,), project_id="book"):
    context, model = api()
    return context.build_combat_context(root, project_id, model.CombatScope(numbers, "研究战斗"),
                                        task_id="job-1", session_id="session-1", instruction="分析证据")


def test_target_draft_precedes_formal_and_adjacent(tmp_path):
    root = book(tmp_path)
    write(root, "production/final_chapters/chapter_001.md", "邻章")
    write(root, "production/final_chapters/chapter_002.md", "目标正式稿")
    write(root, ".creative_os/writer/drafts/chapter_002.jsonl", json.dumps({"version": 3, "content": "目标工作稿"}))
    request = build(root)
    bodies = [source for source in request.sources if source["usage"] == "included"]
    assert [(item["kind"], item["chapter_number"], item["text"]) for item in bodies] == [
        ("working_draft", 2, "目标工作稿"), ("written_chapter", 2, "目标正式稿"), ("written_chapter", 1, "邻章")]
    assert bodies[0]["version"] == 3
    assert bodies[0]["role"] == "target" and bodies[2]["role"] == "adjacent"


def test_missing_target_is_not_inferred(tmp_path):
    root = book(tmp_path)
    write(root, "production/final_chapters/chapter_001.md", "前文战斗不代表本章")
    request = build(root)
    target = [item for item in request.sources if item["chapter_number"] == 2]
    assert len(target) == 2 and all(item["usage"] == "missing" and "text" not in item for item in target)


def test_cross_book_source_rejected(tmp_path):
    first, second = book(tmp_path), book(tmp_path, "other")
    write(first, "production/final_chapters/chapter_002.md", "本书")
    write(second, "production/final_chapters/chapter_002.md", "别书")
    context, _ = api()
    own, foreign = build(first), build(second, project_id="other")
    foreign_id = next(item["source_id"] for item in foreign.sources if item.get("text"))
    with pytest.raises(ValueError, match="source"):
        context.read_combat_source(own, foreign_id)
    with pytest.raises(ValueError, match="scope"):
        build(first, project_id="other")


def tree(root):
    return {str(path.relative_to(root)): (path.is_dir(), path.stat().st_mtime_ns,
             None if path.is_dir() else path.read_bytes()) for path in [root, *root.rglob("*")]}


def test_query_does_not_write(tmp_path):
    root = book(tmp_path)
    write(root, "production/final_chapters/chapter_002.md", "冻结正文")
    before = tree(root)
    request = build(root)
    context, _ = api()
    for source in request.sources:
        assert context.read_combat_source(request, source["source_id"]) == source
    assert tree(root) == before


@pytest.mark.parametrize("numbers,size", [((2,), 12001), ((1, 2, 3, 4, 5), 10000)])
def test_required_context_over_budget(tmp_path, numbers, size):
    root = book(tmp_path)
    for number in numbers:
        write(root, f"production/final_chapters/chapter_{number:03d}.md", "文" * size)
    with pytest.raises(ValueError, match="required_combat_context_budget_exceeded.*缩小范围"):
        build(root, numbers)


def test_snapshot_survives_live_changes_and_returns_detached_source(tmp_path):
    root = book(tmp_path)
    write(root, "production/final_chapters/chapter_002.md", "冻结原文")
    request = build(root)
    context, _ = api()
    source = next(item for item in request.sources if item.get("text"))
    write(root, "production/final_chapters/chapter_002.md", "后来正文")
    result = context.read_combat_source(request, source["source_id"])
    assert result["text"] == "冻结原文"
    assert result["excerpt_start"] == 0 and result["excerpt_end"] == 4 and result["truncated"] is False
    result["text"] = "外部修改"
    assert context.read_combat_source(request, source["source_id"])["text"] == "冻结原文"
    with pytest.raises(ValueError, match="source"):
        context.read_combat_source(request, "../../project.json")


def test_empty_scope_does_not_load_chapters(tmp_path):
    root = book(tmp_path)
    write(root, "production/final_chapters/chapter_001.md", "不应无界读取" * 20000)
    assert all(source["chapter_number"] is None for source in build(root, ()).sources)


def test_confirmed_story_and_story_candidate_stay_separate(tmp_path):
    from creative_os.story_architecture_store import StoryArchitectureStore
    root = book(tmp_path)
    store = StoryArchitectureStore(root, "book")
    first = store.propose(store.session_id, [{"key": "world", "title": "世界", "text": "正式哨兵"}], [],
                          expected_revision=0, actor="作者", operation_id="first")
    store.confirm(store.session_id, 1, first["hash"], expected_confirmed_version=0, actor="作者", operation_id="confirm")
    store.propose(store.session_id, [{"key": "world", "title": "世界", "text": "未确认哨兵"}], [],
                  expected_revision=1, actor="作者", operation_id="second")
    request = build(root)
    assert "正式哨兵" in request.confirmed_story["text"]
    assert "未确认哨兵" not in request.confirmed_story["text"]
    assert next(source for source in request.sources if source["kind"] == "story_candidate")["semantics"].startswith("未确认")
    assert all(source["kind"] != "legacy_plan" for source in request.sources)


def test_required_story_over_budget(tmp_path):
    from creative_os.story_architecture_store import StoryArchitectureStore
    root = book(tmp_path)
    store = StoryArchitectureStore(root, "book")
    first = store.propose(store.session_id, [{"key": "world", "title": "世界", "text": "文" * 12001}], [],
                          expected_revision=0, actor="作者", operation_id="first")
    store.confirm(store.session_id, 1, first["hash"], expected_confirmed_version=0, actor="作者", operation_id="confirm")
    with pytest.raises(ValueError, match="required_combat_context_budget_exceeded"):
        build(root)


@pytest.mark.parametrize("numbers", [(True,), (0,), (1, 1), [1]])
def test_invalid_scope_rejected(numbers):
    _, model = api()
    with pytest.raises(ValueError, match="scope"):
        model.CombatScope(numbers, "研究")


def test_verdict_is_strict_but_reply_is_free_text():
    _, model = api()
    values = dict(result_id="result", project_id="book", job_id="job", reply="任意正文\n保持段落", alternatives=(),
                  foreshadowing=(), evidence_refs=(), unknowns=(), scope=model.CombatScope((), "全书研究"))
    for verdict in ("combat", "setup", "noncombat", "insufficient"):
        assert model.CombatResult(verdict=verdict, **values).reply == "任意正文\n保持段落"
    with pytest.raises(ValueError, match="verdict"):
        model.CombatResult(verdict="other", **values)
    with pytest.raises(ValueError, match="verdict"):
        model.CombatResult(verdict=[], **values)


def test_linked_source_cannot_escape_root(tmp_path):
    root = book(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("别书内容", encoding="utf-8")
    target = root / "production/final_chapters/chapter_002.md"
    target.parent.mkdir(parents=True)
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("当前 Windows 账号无符号链接权限")
    with pytest.raises(ValueError, match="scope"):
        build(root)
