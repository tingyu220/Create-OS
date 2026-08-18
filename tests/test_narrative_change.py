from dataclasses import replace

from creative_os.domains.narrative_change import analyze_change_impact
from creative_os.domains.narrative_decision import (
    NarrativeChangeRequest,
    NarrativeChangeStatus,
    WrittenTextStrategy,
)
from tests.test_narrative_review import _decision


def _request() -> NarrativeChangeRequest:
    return NarrativeChangeRequest(
        id="change-001",
        reason="发送者身份改为未确认",
        old_plan="第九区日志直接指向周远",
        new_plan="第九区日志只保留周远的钥匙算法线索",
        affected_chapters=(7,),
        affected_state_subjects=("林子轩",),
        affected_hooks=("第九区发送者",),
        written_text_strategy=WrittenTextStrategy.LOCAL_REVISION,
    )


def test_change_impact_generates_written_future_and_state_tasks_without_applying():
    request = _request()
    base = _decision()
    future = replace(
        base,
        chapter=8,
        chapter_contract=replace(base.chapter_contract, foreshadow_actions=("第九区发送者",)),
    )

    report = analyze_change_impact(
        request,
        [future],
        written_chapters=(7,),
        state_snapshots=[{
            "kind": "character", "subject": "林子轩",
            "latest_change": "state-chapter-006-character-林子轩",
        }],
    )

    scopes = {(task.chapter, task.scope) for task in report.tasks}
    assert {(7, "written_text"), (8, "future_decision"), (6, "state_snapshot")} <= scopes
    assert request.status == NarrativeChangeStatus.PROPOSED


def test_change_impact_does_not_include_unrelated_future_decisions():
    request = _request()

    report = analyze_change_impact(request, [_decision()])

    assert {task.chapter for task in report.tasks} == {7}
