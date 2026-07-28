import pytest

from creative_os.foundation.state import ProjectState, StateBoundaryError


def test_state_allows_only_current_work_fields_and_rejects_knowledge_content():
    state = ProjectState(
        current_phase="Draft",
        current_task_id="t1",
        current_goal="完成 Scene 1",
        active_domain="novel",
        risks=["缺少上一章摘要"],
    )

    assert state.compact() == {
        "current_phase": "Draft",
        "current_task_id": "t1",
        "current_goal": "完成 Scene 1",
        "active_domain": "novel",
        "risks": ["缺少上一章摘要"],
    }

    with pytest.raises(StateBoundaryError):
        ProjectState(
            current_phase="Draft",
            current_task_id="t2",
            current_goal="错误保存正文",
            active_domain="novel",
            manuscript="正文不能进入 State",
        )


def test_state_updates_are_explicit_and_keep_state_compact():
    state = ProjectState(
        current_phase="Outline",
        current_task_id="t1",
        current_goal="完成大纲",
        active_domain="novel",
    )

    updated = state.advance(current_phase="Draft", current_task_id="t2", current_goal="写第一章")

    assert updated.current_phase == "Draft"
    assert updated.current_task_id == "t2"
    assert updated.current_goal == "写第一章"
    assert state.current_phase == "Outline"


def test_state_limits_risk_count_to_keep_runtime_state_small():
    with pytest.raises(StateBoundaryError):
        ProjectState(
            current_phase="Draft",
            current_task_id="t1",
            current_goal="风险过多",
            active_domain="novel",
            risks=[f"risk-{index}" for index in range(11)],
        )
