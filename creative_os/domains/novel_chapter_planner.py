from __future__ import annotations

from dataclasses import dataclass

from creative_os.domains.narrative_decision import NarrativeValidationError, ScenePlan
from creative_os.domains.novel_chapter_boundary import (
    ChapterBoundary,
    ChapterBoundaryAssessment,
    assess_boundary,
)


@dataclass(frozen=True, slots=True)
class ChapterPlanningRequest:
    scene_plan: ScenePlan
    boundary: ChapterBoundary
    target_min_chinese_chars: int = 2500
    target_max_chinese_chars: int = 5000


@dataclass(frozen=True, slots=True)
class ChapterPlanResult:
    assessment: ChapterBoundaryAssessment
    blocking_codes: tuple[str, ...]

    @property
    def approved(self) -> bool:
        return not self.blocking_codes


def plan_chapter(request: ChapterPlanningRequest) -> ChapterPlanResult:
    if not isinstance(request.scene_plan, ScenePlan):
        raise ValueError("chapter_planning_scene_plan_invalid")
    try:
        request.scene_plan.validate(required=True, novel_required=True)
    except NarrativeValidationError:
        assessment = ChapterBoundaryAssessment(("scene_contract_invalid",), ("scene_contract_invalid",))
        return ChapterPlanResult(assessment, assessment.blocking_codes)
    assessment = assess_boundary(
        request.boundary,
        target_min_chinese_chars=request.target_min_chinese_chars,
        target_max_chinese_chars=request.target_max_chinese_chars,
    )
    return ChapterPlanResult(assessment, assessment.blocking_codes)


class NovelChapterPlanner:
    def plan(self, request: ChapterPlanningRequest) -> ChapterPlanResult:
        return plan_chapter(request)
