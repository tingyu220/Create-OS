from __future__ import annotations

from dataclasses import dataclass

from creative_os.domains.narrative_decision import ChapterContract
from creative_os.domains.novel_chapter_boundary import ChapterBoundary


NOVEL_CONSISTENCY_CODES = frozenset({
    "character_state_drift",
    "timeline_conflict",
    "foreshadow_lifecycle_break",
})


@dataclass(frozen=True, slots=True)
class CharacterStateProposal:
    subject: str
    change: str
    evidence: tuple[str, ...]

    def validate(self) -> None:
        if not self.subject.strip() or not self.change.strip():
            raise ValueError("character_state_proposal_invalid")
        if any(not item.strip() for item in self.evidence):
            raise ValueError("character_state_evidence_invalid")


@dataclass(frozen=True, slots=True)
class ConsistencyFinding:
    code: str
    scope: str
    evidence: str

    def validate(self) -> None:
        if self.code not in NOVEL_CONSISTENCY_CODES:
            raise ValueError("novel_consistency_code_invalid")
        if not self.scope.strip() or not self.evidence.strip():
            raise ValueError("novel_consistency_finding_invalid")


@dataclass(frozen=True, slots=True)
class NovelReviewIssue:
    code: str
    severity: str
    scope: str
    evidence: tuple[str, ...]
    repair_kind: str
    blocking: bool

    def validate(self) -> None:
        if not self.code.strip() or self.severity not in {"warning", "error"}:
            raise ValueError("novel_review_issue_invalid")
        if not self.scope.strip() or not self.repair_kind.strip() or not self.evidence:
            raise ValueError("novel_review_issue_evidence_required")
        if any(not item.strip() for item in self.evidence):
            raise ValueError("novel_review_issue_evidence_invalid")


@dataclass(frozen=True, slots=True)
class NovelReviewRequest:
    draft: str
    chapter_contract: ChapterContract
    boundary: ChapterBoundary
    adjacent_drafts: tuple[str, ...] = ()
    character_changes: tuple[CharacterStateProposal, ...] = ()
    consistency_findings: tuple[ConsistencyFinding, ...] = ()


@dataclass(frozen=True, slots=True)
class NovelReviewResult:
    issues: tuple[NovelReviewIssue, ...]
    blocking_codes: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.blocking_codes

