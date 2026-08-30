from __future__ import annotations

from dataclasses import dataclass


ENDING_FUNCTIONS = frozenset({"resolve", "escalate", "reveal", "decision", "hook"})


@dataclass(frozen=True, slots=True)
class ChapterBoundary:
    """章节出口的领域证据；字数不能替代戏剧闭合。"""

    entry_state: str
    exit_state: str
    ending_function: str
    dialogue_closed: bool
    dramatic_unit_closed: bool
    estimated_chinese_chars: int

    def validate(self) -> None:
        if not self.entry_state.strip() or not self.exit_state.strip():
            raise ValueError("chapter_boundary_state_required")
        if self.ending_function not in ENDING_FUNCTIONS:
            raise ValueError("chapter_boundary_ending_function_invalid")
        if type(self.dialogue_closed) is not bool or type(self.dramatic_unit_closed) is not bool:
            raise ValueError("chapter_boundary_closure_must_be_bool")
        if type(self.estimated_chinese_chars) is not int or self.estimated_chinese_chars <= 0:
            raise ValueError("chapter_boundary_length_invalid")


@dataclass(frozen=True, slots=True)
class ChapterBoundaryAssessment:
    issue_codes: tuple[str, ...]
    blocking_codes: tuple[str, ...]

    @property
    def approved(self) -> bool:
        return not self.blocking_codes


def assess_boundary(
    boundary: ChapterBoundary,
    *,
    target_min_chinese_chars: int = 2500,
    target_max_chinese_chars: int = 5000,
) -> ChapterBoundaryAssessment:
    boundary.validate()
    if target_min_chinese_chars <= 0 or target_max_chinese_chars < target_min_chinese_chars:
        raise ValueError("chapter_length_target_invalid")
    issues: list[str] = []
    blocking: list[str] = []
    if not boundary.dialogue_closed:
        issues.append("dialogue_cut")
        blocking.append("dialogue_cut")
    if not boundary.dramatic_unit_closed:
        issues.append("dramatic_unit_incomplete")
        blocking.append("dramatic_unit_incomplete")
    if boundary.estimated_chinese_chars < target_min_chinese_chars:
        issues.append("chapter_length_below_target")
        if not boundary.dialogue_closed or not boundary.dramatic_unit_closed:
            issues.append("fragment_chapter")
            blocking.append("fragment_chapter")
    if boundary.estimated_chinese_chars > target_max_chinese_chars:
        issues.append("chapter_length_above_target")
        blocking.append("chapter_length_above_target")
    return ChapterBoundaryAssessment(tuple(issues), tuple(blocking))

