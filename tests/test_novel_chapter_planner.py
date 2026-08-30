from dataclasses import replace
import json
from pathlib import Path

from creative_os.domains.novel_chapter_boundary import ChapterBoundary
from creative_os.domains.novel_chapter_planner import (
    ChapterPlanningRequest,
    plan_chapter,
)
from tests.test_novel_scene_contract import _complete_scene
from tests.test_narrative_director import _v2_decision


def _request(boundary: ChapterBoundary) -> ChapterPlanningRequest:
    plan = _v2_decision().chapter_contract.scene_plan
    plan = replace(plan, scenes=(_complete_scene(),))
    return ChapterPlanningRequest(scene_plan=plan, boundary=boundary)


def test_real_fragment_regressions_are_blocked():
    path = Path("tests/fixtures/novel_domain/civilization_regressions.json")
    cases = json.loads(path.read_text(encoding="utf-8"))

    for case in cases:
        boundary = ChapterBoundary(
            entry_state="继承上一章问题",
            exit_state="当前片段尚未形成独立结果",
            ending_function="hook",
            dialogue_closed=case["dialogue_closed"],
            dramatic_unit_closed=case["dramatic_unit_closed"],
            estimated_chinese_chars=case["estimated_chinese_chars"],
        )
        result = plan_chapter(_request(boundary))
        assert set(case["expected_codes"]) <= set(result.blocking_codes), case["case_id"]


def test_complete_scene_and_boundary_are_approved():
    boundary = ChapterBoundary(
        entry_state="主角进入现场",
        exit_state="主角停机并获得旧图缺失证据",
        ending_function="reveal",
        dialogue_closed=True,
        dramatic_unit_closed=True,
        estimated_chinese_chars=3600,
    )

    result = plan_chapter(_request(boundary))

    assert result.approved
    assert result.blocking_codes == ()
