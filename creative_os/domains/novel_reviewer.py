from __future__ import annotations

from collections import Counter
import re

from creative_os.domains.novel_chapter_boundary import assess_boundary
from creative_os.domains.novel_review_model import (
    NovelReviewIssue,
    NovelReviewRequest,
    NovelReviewResult,
)


_REPAIR_BY_CODE = {
    "dialogue_cut": "move_chapter_boundary",
    "dramatic_unit_incomplete": "complete_dramatic_unit",
    "fragment_chapter": "merge_or_expand_scene",
    "chapter_length_above_target": "repartition_complete_units",
    "duplicate_long_paragraph": "remove_duplicate_copy",
    "character_state_drift": "restore_or_evidence_character_change",
    "timeline_conflict": "repair_timeline",
    "foreshadow_lifecycle_break": "repair_foreshadow_lifecycle",
    "essential_information_missing": "restore_essential_information",
}


class NovelReviewer:
    """统一小说审查入口，所有阻断结论必须附带正文或状态证据。"""

    def review(self, request: NovelReviewRequest) -> NovelReviewResult:
        if not request.draft.strip():
            raise ValueError("novel_review_draft_required")
        request.chapter_contract.scene_plan.validate(required=True, novel_required=True)
        assessment = assess_boundary(request.boundary)
        issues: list[NovelReviewIssue] = []
        for code in assessment.issue_codes:
            blocking = code in assessment.blocking_codes
            if code == "chapter_length_below_target" and not blocking:
                issues.append(self._issue(
                    code, "chapter", f"当前预计字数：{request.boundary.estimated_chinese_chars}",
                    "review_short_complete_chapter", False,
                ))
            elif blocking:
                issues.append(self._issue(
                    code, "chapter_boundary", self._boundary_evidence(request, code),
                    _REPAIR_BY_CODE[code], True,
                ))

        duplicate = self._duplicate_long_paragraph(request)
        if duplicate:
            issues.append(self._issue(
                "duplicate_long_paragraph", "draft", duplicate,
                _REPAIR_BY_CODE["duplicate_long_paragraph"], True,
            ))

        for proposal in request.character_changes:
            proposal.validate()
            if not proposal.evidence:
                issues.append(self._issue(
                    "character_state_drift", f"character:{proposal.subject}", proposal.change,
                    _REPAIR_BY_CODE["character_state_drift"], True,
                ))

        for finding in request.consistency_findings:
            finding.validate()
            issues.append(self._issue(
                finding.code, finding.scope, finding.evidence,
                _REPAIR_BY_CODE[finding.code], True,
            ))

        for scene in request.chapter_contract.scene_plan.scenes:
            for information in scene.essential_information:
                if information not in request.draft:
                    issues.append(self._issue(
                        "essential_information_missing", f"scene:{scene.id}", information,
                        _REPAIR_BY_CODE["essential_information_missing"], True,
                    ))

        for issue in issues:
            issue.validate()
        blocking_codes = tuple(dict.fromkeys(issue.code for issue in issues if issue.blocking))
        return NovelReviewResult(tuple(issues), blocking_codes)

    @staticmethod
    def _issue(
        code: str,
        scope: str,
        evidence: str,
        repair_kind: str,
        blocking: bool,
    ) -> NovelReviewIssue:
        return NovelReviewIssue(
            code=code,
            severity="error" if blocking else "warning",
            scope=scope,
            evidence=(evidence,),
            repair_kind=repair_kind,
            blocking=blocking,
        )

    @staticmethod
    def _boundary_evidence(request: NovelReviewRequest, code: str) -> str:
        boundary = request.boundary
        return (
            f"{code}: entry={boundary.entry_state}; exit={boundary.exit_state}; "
            f"dialogue_closed={boundary.dialogue_closed}; "
            f"dramatic_unit_closed={boundary.dramatic_unit_closed}; "
            f"chars={boundary.estimated_chinese_chars}"
        )

    @staticmethod
    def _duplicate_long_paragraph(request: NovelReviewRequest) -> str | None:
        current = _paragraphs(request.draft)
        adjacent = [paragraph for draft in request.adjacent_drafts for paragraph in _paragraphs(draft)]
        counts = Counter(current)
        for paragraph in current:
            if len(paragraph) >= 40 and (counts[paragraph] > 1 or paragraph in adjacent):
                return paragraph
        return None


def _paragraphs(text: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in re.split(r"\n\s*\n", text) if item.strip() and not item.startswith("#"))

