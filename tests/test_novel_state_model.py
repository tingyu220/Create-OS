import json

from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.memory.store import JsonMemoryStore
from creative_os.domains.novel_state_model import STATE_KINDS, build_state_changes


def test_state_model_does_not_infer_story_facts_from_chapter_number(tmp_path):
    project = tmp_path / "文明升阶"
    chapter = project / "production/final_chapters/chapter_003.md"
    chapter.parent.mkdir(parents=True)
    chapter.write_text("# 第3章：两张脸\n林子轩在龙渊见到林正弘。\n他问：你们改造了我的大脑吗？", encoding="utf-8")
    (project / ".creative_os/import").mkdir(parents=True)
    (project / ".creative_os/import/active_baseline.json").write_text(
        json.dumps({"characters": [{"title": "林子轩"}, {"title": "林正弘"}]}), encoding="utf-8"
    )

    changes = build_state_changes(project, 3)

    assert {change.kind for change in changes} <= set(STATE_KINDS)
    assert not any("D-7" in json.dumps(change.fields, ensure_ascii=False) for change in changes)
    assert all(change.status == "candidate" for change in changes)
    assert all(change.evidence[0].source_chapter.endswith("chapter_003.md") for change in changes)
    assert {change.kind for change in changes} == {"event", "timeline"}


def test_chapter_six_state_is_entity_level_and_preserves_information_boundaries(tmp_path):
    project = tmp_path / "文明升阶"
    chapter = project / "production/final_chapters/chapter_006.md"
    chapter.parent.mkdir(parents=True)
    chapter.write_text("# 第6章\n林子轩收到短信，林正弘确认来源是内部服务器。", encoding="utf-8")

    changes = build_state_changes(project, 6)

    assert {change.kind for change in changes} == {"event", "timeline"}


def test_state_model_loads_structured_compiler_candidate_instead_of_parsing_chapter_number(tmp_path):
    project = tmp_path / "文明升阶"
    chapter = project / "production/final_chapters/chapter_003.md"
    chapter.parent.mkdir(parents=True)
    chapter.write_text("# 第3章\n林子轩进入未知地点。", encoding="utf-8")
    store = JsonMemoryStore(project / ".creative_os/memory")
    payload = {
        "schema_version": 2,
        "id": "state-chapter-003-character-林子轩",
        "kind": "character",
        "subject": "林子轩",
        "status": "candidate",
        "fields": {"location": "未知地点", "emotional_state": ["警惕"]},
        "evidence": [{"source_chapter": "production/final_chapters/chapter_003.md", "excerpt": "进入未知地点"}],
    }
    item = MemoryItem.new_candidate(
        id=payload["id"], kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
        scope_id=project.name, title="人物状态", content=json.dumps(payload, ensure_ascii=False),
        evidence=[MemoryEvidence("chapter", "chapter_003")],
    )
    store.add_candidate(item)

    changes = build_state_changes(project, 3)

    assert changes[0].subject == "林子轩"
    assert changes[0].fields["location"] == "未知地点"
