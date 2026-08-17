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
