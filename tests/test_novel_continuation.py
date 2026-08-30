import json

import pytest

from creative_os.domains.novel_continuation import ContinuationBlockedError, build_next_chapter


def _project(tmp_path):
    project = tmp_path / "文明升阶"
    (project / "production/final_chapters").mkdir(parents=True)
    (project / ".creative_os/import").mkdir(parents=True)
    (project / ".creative_os/knowledge").mkdir(parents=True)
    (project / "production/final_chapters/chapter_001.md").write_text("# 第1章\n第一章结尾。", encoding="utf-8")
    (project / "production/final_chapters/chapter_002.md").write_text("# 第2章\n第二章结尾。", encoding="utf-8")
    (project / "fix").mkdir()
    (project / "fix/第3章.md").write_text("废稿不得读取", encoding="utf-8")
    (project / ".creative_os/import/baseline.json").write_text(
        json.dumps(
            {
                "world_rules": [{"title": "物理现实", "content": "物理规则不可违背", "source_path": "核心框架.md"}],
                "characters": [{"title": "林子轩", "content": "天文系学生", "source_path": "01_Characters/林子轩.md"}],
                "plot_milestones": [{"title": "第一卷", "content": "林子轩进入龙渊", "source_path": "02_Plot/第一卷.md"}],
                "hooks": [{"title": "H-001", "content": "CMB来源未揭示", "source_path": "03_Hooks/Hooks.md"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project / ".creative_os/knowledge/imported_active.json").write_text("[]", encoding="utf-8")
    (project / ".creative_os/import/conflicts.json").write_text("[]", encoding="utf-8")
    (project / ".creative_os/import/approval.json").write_text('{"resolutions": {}}', encoding="utf-8")
    return project


def test_next_chapter_uses_last_canon_state_and_next_outline_goal(tmp_path):
    task, context = build_next_chapter(_project(tmp_path))

    assert task.chapter_number == 3
    assert task.previous_chapter == 2
    assert "林子轩进入龙渊" in task.narrative_goal
    assert context.contains_source("production/final_chapters/chapter_002.md")
    assert not context.contains_source("fix/第3章.md")


def test_continuation_blocks_when_required_conflict_is_unresolved(tmp_path):
    project = _project(tmp_path)
    (project / ".creative_os/import/conflicts.json").write_text(
        '[{"code":"volume_count_conflict","severity":"high"}]', encoding="utf-8"
    )

    with pytest.raises(ContinuationBlockedError):
        build_next_chapter(project)


def test_next_chapter_extracts_exact_table_row_instead_of_entire_outline(tmp_path):
    project = _project(tmp_path)
    baseline_path = project / ".creative_os/import/baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["plot_milestones"] = [
        {
            "title": "剧情大纲",
            "content": "| 章 | 标题 | 核心事件 | 字数 |\n|---|---|---|---|\n| 3 | 两张脸 | 与父母摊牌，得知大脑被改造 | 9000 |\n| 4 | 告别 | 搬入龙渊 | 8000 |",
            "source_path": "02_Plot/Plot_Outline.md",
        }
    ]
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

    task, _ = build_next_chapter(project)

    assert task.narrative_goal == "第 3 章《两张脸》：与父母摊牌，得知大脑被改造；目标字数 9000"


def test_continuation_uses_the_previous_chapter_ending_not_its_opener(tmp_path):
    project = _project(tmp_path)
    chapter = project / "production/final_chapters/chapter_002.md"
    chapter.write_text("# 第2章\n开头内容。\n" + "中段。" * 600 + "\n最后的收束。", encoding="utf-8")

    task, _ = build_next_chapter(project)

    assert "最后的收束。" in task.last_chapter_ending
    assert "开头内容。" not in task.last_chapter_ending


def test_continuation_uses_outline_target_for_length_gate(tmp_path):
    project = _project(tmp_path)
    baseline = json.loads((project / ".creative_os/import/baseline.json").read_text(encoding="utf-8"))
    baseline["plot_milestones"] = [{"title": "大纲", "content": "| 3 | 测试 | 推进 | 8000 |", "source_path": "outline.md"}]
    (project / ".creative_os/import/baseline.json").write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

    task, _ = build_next_chapter(project)

    assert task.target_chinese_chars == 8000
    assert task.min_chinese_chars == 6000


def test_continuation_allows_an_explicit_target_override(tmp_path):
    task, _ = build_next_chapter(_project(tmp_path), target_chinese_chars=9000)

    assert task.target_chinese_chars == 9000
    assert task.min_chinese_chars == 6750


def test_continuation_context_keeps_all_active_state_kinds(tmp_path):
    project = _project(tmp_path)
    from creative_os.domains.novel_chapter_memory import save_chapter_candidates
    from creative_os.memory.approval import approve_candidate
    from creative_os.memory.store import JsonMemoryStore
    from creative_os.domains.novel_state_store import materialize_active_state

    save_chapter_candidates(project, 2)
    store = JsonMemoryStore(project / ".creative_os/memory")
    for item in store.list():
        approve_candidate(store, item.id, actor="tingyu", note="测试批准")
    materialize_active_state(project)

    _, context = build_next_chapter(project)

    assert not any(source.source_id == "state:character:chapter_cast" for source in context.sources)
