from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Protocol

from creative_os.domains.publication_migration_model import SourceFragment
from creative_os.domains.publication_source_snapshot import (
    ArchiveReceipt,
    VerifiedSourceArchiveView,
    load_verified_archive,
)


_HASH = re.compile(r"^[0-9a-f]{64}$")
_DRAMATIC_BOUNDARIES = frozenset({"dramatic_turn", "scene_resolution", "irreversible_action", "ending_hook"})
_REVIEW_RULESET_VERSION = "publication-split-review-v1"
_MAX_OMISSION_PARAGRAPHS = 5
_MAX_OMISSION_RATIO = 0.5
_UNRESOLVED_LANGUAGE = re.compile(
    r"(?:尚未(?:决定|选择)|未解决|等待(?:决定|选择)|仍未(?:决定|选择)|待定|unresolved|undecided|pending choice)",
    re.IGNORECASE,
)


class BoundaryStatus(Enum):
    RESOLVED = "resolved"
    OPEN = "open"


class ClosureDimension(Enum):
    DIALOGUE = "dialogue_closure"
    CONFLICT = "conflict_outcome"
    CHOICE = "choice_consequence"
    STATE = "state_shift"
    HOOK = "ending_hook"


@dataclass(frozen=True, slots=True)
class ClosureEvidence:
    """offset 使用 Python Unicode 码点索引，范围为段落内左闭右开区间。"""
    dimension: ClosureDimension
    source_chapter: int
    paragraph_ordinal: int
    paragraph_hash: str
    excerpt: str
    start_offset: int
    end_offset: int

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, ClosureDimension):
            raise TypeError("closure evidence dimension is required")
        if type(self.source_chapter) is not int or not 5 <= self.source_chapter <= 32:
            raise ValueError("closure evidence chapter must be 5..32")
        if type(self.paragraph_ordinal) is not int or self.paragraph_ordinal <= 0:
            raise ValueError("closure evidence paragraph ordinal is invalid")
        _require_hash(self.paragraph_hash, "closure evidence paragraph_hash")
        _require_text(self.excerpt, "closure evidence excerpt")
        if (
            type(self.start_offset) is not int or type(self.end_offset) is not int
            or self.start_offset < 0 or self.end_offset <= self.start_offset
        ):
            raise ValueError("closure evidence span is invalid")


class PublicationSourceAuthority(Protocol):
    def load(self, receipt: ArchiveReceipt, project_root: Path) -> VerifiedSourceArchiveView: ...


class Task3PublicationSourceAuthority:
    def load(self, receipt: ArchiveReceipt, project_root: Path) -> VerifiedSourceArchiveView:
        return load_verified_archive(receipt, project_root)


@dataclass(frozen=True, slots=True)
class DramaticUnit:
    function: str
    scene_scope: tuple[str, ...]
    conflict: str
    choice_or_discovery: str
    outcome: str
    information_reveal: str
    technology_state: str
    state_shift: str
    ending_hook: str
    source_fragments: tuple[SourceFragment, ...]
    estimated_chinese_chars: int
    boundary_basis: str
    dialogue_closed: bool
    conflict_status: BoundaryStatus
    choice_status: BoundaryStatus
    closure_evidence: tuple[ClosureEvidence, ...]

    def __post_init__(self) -> None:
        for name in (
            "function", "conflict", "choice_or_discovery", "outcome", "information_reveal",
            "technology_state", "state_shift", "ending_hook", "boundary_basis",
        ):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be a string")
        if not isinstance(self.source_fragments, tuple) or not all(
            isinstance(item, SourceFragment) for item in self.source_fragments
        ):
            raise TypeError("source_fragments must be a tuple of SourceFragment")
        if not isinstance(self.scene_scope, tuple) or not all(isinstance(item, str) for item in self.scene_scope):
            raise TypeError("scene_scope must be a tuple of strings")
        if not isinstance(self.closure_evidence, tuple) or not all(
            isinstance(item, ClosureEvidence) for item in self.closure_evidence
        ):
            raise TypeError("closure_evidence must be a tuple of ClosureEvidence")
        if type(self.estimated_chinese_chars) is not int or self.estimated_chinese_chars < 0:
            raise ValueError("estimated_chinese_chars must be non-negative")
        if type(self.dialogue_closed) is not bool:
            raise TypeError("dialogue_closed must be bool")
        if not isinstance(self.conflict_status, BoundaryStatus) or not isinstance(self.choice_status, BoundaryStatus):
            raise TypeError("boundary statuses are required")


@dataclass(frozen=True, slots=True)
class SplitPlanOmission:
    """写前计划中的显式遗漏；不携带候选或审批哈希，避免自引用。"""
    source_fragments: tuple[SourceFragment, ...]
    snapshot_hash: str
    reason: str
    evidence: str
    impact: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_fragments, tuple) or not self.source_fragments or not all(
            isinstance(item, SourceFragment) for item in self.source_fragments
        ):
            raise ValueError("omission source fragments are required")
        positions = []
        for fragment in self.source_fragments:
            if fragment.paragraph_start != fragment.paragraph_end:
                raise ValueError("omission fragments must identify exact paragraphs")
            positions.append((fragment.source_chapter, fragment.paragraph_start))
        if tuple(positions) != tuple(sorted(set(positions))):
            raise ValueError("omission fragments must be unique and ordered")
        _require_hash(self.snapshot_hash, "omission snapshot_hash")
        for name in ("reason", "evidence", "impact"):
            _require_text(getattr(self, name), f"omission {name}")


@dataclass(frozen=True, slots=True)
class SourceChapterPlanningInput:
    source_chapter: int
    contract_hash: str
    pov_plan_hash: str
    scene_plan_hash: str
    units: tuple[DramaticUnit, ...]

    def __post_init__(self) -> None:
        if type(self.source_chapter) is not int or self.source_chapter <= 0:
            raise ValueError("invalid source chapter")
        for name in ("contract_hash", "pov_plan_hash", "scene_plan_hash"):
            _require_hash(getattr(self, name), name)
        if not isinstance(self.units, tuple) or not all(isinstance(item, DramaticUnit) for item in self.units):
            raise TypeError("units must be a tuple of DramaticUnit")


@dataclass(frozen=True, slots=True)
class SplitPlanningInputs:
    migration_id: str
    target_edition_id: str
    chapters: tuple[SourceChapterPlanningInput, ...]
    omissions: tuple[SplitPlanOmission, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.migration_id, "migration_id")
        _require_text(self.target_edition_id, "target_edition_id")
        if not isinstance(self.chapters, tuple) or not self.chapters or not all(
            isinstance(item, SourceChapterPlanningInput) for item in self.chapters
        ):
            raise ValueError("chapters are required")
        numbers = tuple(item.source_chapter for item in self.chapters)
        if numbers != tuple(sorted(set(numbers))):
            raise ValueError("source chapters must be unique and ordered")
        if not isinstance(self.omissions, tuple) or not all(
            isinstance(item, SplitPlanOmission) for item in self.omissions
        ):
            raise TypeError("omissions must be a tuple of SplitPlanOmission")


@dataclass(frozen=True, slots=True)
class SplitPlanCandidate:
    migration_id: str
    project_id: str
    source_edition_id: str
    target_edition_id: str
    source_snapshot_hash: str
    input_fingerprint: str
    units: tuple[DramaticUnit, ...]
    omissions: tuple[SplitPlanOmission, ...] = ()
    candidate_hash: str = ""

    def __post_init__(self) -> None:
        for name in ("migration_id", "project_id", "source_edition_id", "target_edition_id"):
            _require_text(getattr(self, name), name)
        _require_hash(self.source_snapshot_hash, "source_snapshot_hash")
        _require_hash(self.input_fingerprint, "input_fingerprint")
        if not isinstance(self.units, tuple) or not all(isinstance(item, DramaticUnit) for item in self.units):
            raise TypeError("units must be a tuple of DramaticUnit")
        if not isinstance(self.omissions, tuple) or not all(
            isinstance(item, SplitPlanOmission) for item in self.omissions
        ):
            raise TypeError("omissions must be a tuple of SplitPlanOmission")
        if self.candidate_hash:
            _require_hash(self.candidate_hash, "candidate_hash")
            if self.candidate_hash != split_plan_candidate_hash(self):
                raise ValueError("candidate_hash mismatch")


@dataclass(frozen=True, slots=True)
class SplitPlanIssue:
    code: str
    message: str
    unit_index: int | None = None


@dataclass(frozen=True, slots=True)
class SplitPlanReviewRecord:
    candidate_hash: str
    snapshot_hash: str
    ruleset_version: str
    blocking_issues: tuple[SplitPlanIssue, ...]
    review_hash: str = ""

    def __post_init__(self) -> None:
        _require_hash(self.candidate_hash, "candidate_hash")
        _require_hash(self.snapshot_hash, "snapshot_hash")
        _require_text(self.ruleset_version, "ruleset_version")
        if not isinstance(self.blocking_issues, tuple) or not all(
            isinstance(item, SplitPlanIssue) for item in self.blocking_issues
        ):
            raise TypeError("blocking_issues must be a tuple")
        if self.review_hash:
            _require_hash(self.review_hash, "review_hash")
            if self.review_hash != split_plan_review_hash(self):
                raise ValueError("review_hash mismatch")


class PublicationSplitPlanner:
    """只审核显式结构化拆分输入，不推断正文事实。"""

    def review(
        self, candidate: SplitPlanCandidate, receipt: ArchiveReceipt, project_root: Path,
    ) -> tuple[SplitPlanIssue, ...]:
        source = Task3PublicationSourceAuthority().load(receipt, Path(project_root))
        return self._review_verified(candidate, source)

    def _review_verified(
        self, candidate: SplitPlanCandidate, source: VerifiedSourceArchiveView,
    ) -> tuple[SplitPlanIssue, ...]:
        if not isinstance(candidate, SplitPlanCandidate):
            raise TypeError("candidate is required")
        validate_archive_view(source)
        source.verify_current()
        issues: list[SplitPlanIssue] = []
        if (
            candidate.project_id != source.project_id
            or candidate.source_edition_id != source.source_edition_id
            or candidate.source_snapshot_hash != source.snapshot_hash
        ):
            issues.append(SplitPlanIssue("source_snapshot_mismatch", "候选与源快照身份不一致"))

        expected = {
            (paragraph.chapter_number, paragraph.paragraph_ordinal, paragraph.paragraph_ordinal): paragraph.paragraph_hash
            for paragraph in source.iter_paragraphs()
        }
        seen: set[tuple[int, int, int]] = set()
        previous: tuple[int, int, int] | None = None
        for index, unit in enumerate(candidate.units, start=1):
            required = (
                unit.function, unit.conflict, unit.choice_or_discovery, unit.outcome,
                unit.information_reveal, unit.technology_state, unit.state_shift,
            )
            if any(not value.strip() for value in required) or not unit.scene_scope or any(
                not value.strip() for value in unit.scene_scope
            ):
                issues.append(SplitPlanIssue("dramatic_unit_incomplete", "戏剧单元因果链未闭合", index))
            if unit.conflict_status is not BoundaryStatus.RESOLVED or unit.choice_status is not BoundaryStatus.RESOLVED:
                issues.append(SplitPlanIssue("dramatic_unit_incomplete", "冲突或选择尚未闭合", index))
            if any(_UNRESOLVED_LANGUAGE.search(value) for value in (
                unit.conflict, unit.choice_or_discovery, unit.outcome,
            )):
                issues.append(SplitPlanIssue("dramatic_unit_incomplete", "闭包状态与叙述语义矛盾", index))
            if not unit.ending_hook.strip():
                issues.append(SplitPlanIssue("ending_hook_missing", "戏剧单元缺少章末钩子", index))
            if unit.boundary_basis not in _DRAMATIC_BOUNDARIES:
                issues.append(SplitPlanIssue("mechanical_length_cut", "切点没有绑定戏剧节点", index))
            if not unit.dialogue_closed:
                issues.append(SplitPlanIssue("cut_inside_dialogue", "切点位于未闭合对话内", index))
            if not unit.source_fragments:
                issues.append(SplitPlanIssue("source_fragment_empty", "戏剧单元缺少来源片段", index))
            evidence_issues = _review_closure_evidence(unit, source)
            if evidence_issues:
                issues.append(SplitPlanIssue("boundary_evidence_invalid", "闭包证据未落在单元末端来源片段", index))
            for fragment in unit.source_fragments:
                key = (fragment.source_chapter, fragment.paragraph_start, fragment.paragraph_end)
                if not 5 <= fragment.source_chapter <= 32:
                    issues.append(SplitPlanIssue(
                        "frozen_source_fragment_forbidden", "迁移候选不得引用冻结章节", index,
                    ))
                if key in seen:
                    issues.append(SplitPlanIssue("source_fragment_duplicate", "来源片段跨单元重复", index))
                if previous is not None and key <= previous:
                    issues.append(SplitPlanIssue("source_fragment_out_of_order", "来源片段顺序颠倒", index))
                if expected.get(key) != fragment.text_hash:
                    issues.append(SplitPlanIssue("source_hash_mismatch", "来源片段哈希不匹配", index))
                seen.add(key)
                previous = key
        retained_by_chapter: dict[int, set[tuple[int, int, int]]] = {}
        for key in seen:
            retained_by_chapter.setdefault(key[0], set()).add(key)
        omitted_by_chapter: dict[int, set[tuple[int, int, int]]] = {}
        omission_previous: tuple[int, int, int] | None = None
        for omission_index, omission in enumerate(candidate.omissions, start=1):
            if omission.snapshot_hash != source.snapshot_hash:
                issues.append(SplitPlanIssue(
                    "omission_snapshot_mismatch", "遗漏记录未绑定当前权威快照", omission_index,
                ))
            for fragment in omission.source_fragments:
                key = (fragment.source_chapter, fragment.paragraph_start, fragment.paragraph_end)
                omitted_by_chapter.setdefault(fragment.source_chapter, set()).add(key)
                if not 5 <= fragment.source_chapter <= 32:
                    issues.append(SplitPlanIssue(
                        "omission_source_forbidden", "遗漏记录不得引用冻结或范围外章节", omission_index,
                    ))
                if expected.get(key) != fragment.text_hash:
                    issues.append(SplitPlanIssue(
                        "omission_source_mismatch", "遗漏段落定位或哈希不匹配", omission_index,
                    ))
                if key in seen:
                    issues.append(SplitPlanIssue(
                        "omission_source_overlap", "遗漏段落与戏剧单元或其他遗漏重叠", omission_index,
                    ))
                if omission_previous is not None and key <= omission_previous:
                    issues.append(SplitPlanIssue(
                        "omission_source_out_of_order", "遗漏段落顺序颠倒", omission_index,
                    ))
                seen.add(key)
                omission_previous = key
        for chapter, omitted in omitted_by_chapter.items():
            total = sum(1 for key in expected if key[0] == chapter)
            retained = len(retained_by_chapter.get(chapter, set()))
            omitted_count = len(omitted)
            if (retained == 0 or omitted_count == total
                    or omitted_count > _MAX_OMISSION_PARAGRAPHS
                    or (total > 0 and omitted_count / total >= _MAX_OMISSION_RATIO)):
                issues.append(SplitPlanIssue(
                    "omission_scope_requires_review", "章节累计遗漏范围过大或缺少保留戏剧单元",
                ))
        if seen != set(expected):
            issues.append(SplitPlanIssue("source_fragment_missing", "源段落未被候选完整覆盖"))
        return _deduplicate(issues)

    def review_record(
        self, candidate: SplitPlanCandidate, receipt: ArchiveReceipt, project_root: Path,
    ) -> SplitPlanReviewRecord:
        source = Task3PublicationSourceAuthority().load(receipt, Path(project_root))
        issues = self._review_verified(candidate, source)
        partial = SplitPlanReviewRecord(
            candidate_hash=candidate.candidate_hash,
            snapshot_hash=source.snapshot_hash,
            ruleset_version=_REVIEW_RULESET_VERSION,
            blocking_issues=issues,
        )
        return SplitPlanReviewRecord(
            candidate_hash=partial.candidate_hash,
            snapshot_hash=partial.snapshot_hash,
            ruleset_version=partial.ruleset_version,
            blocking_issues=partial.blocking_issues,
            review_hash=split_plan_review_hash(partial),
        )


def plan_source_chapters(
    receipt: ArchiveReceipt, project_root: Path, contracts: SplitPlanningInputs,
) -> SplitPlanCandidate:
    """从显式合同结构生成确定性候选；不读取外部状态。"""
    source = Task3PublicationSourceAuthority().load(receipt, Path(project_root))
    validate_archive_view(source)
    source.verify_current()
    if not isinstance(contracts, SplitPlanningInputs):
        raise TypeError("contracts must be SplitPlanningInputs")
    omitted_chapters = {
        fragment.source_chapter for omission in contracts.omissions
        for fragment in omission.source_fragments
    }
    if any(not chapter.units and chapter.source_chapter in omitted_chapters for chapter in contracts.chapters):
        raise ValueError("omission chapter requires a retained dramatic unit")
    chapter_numbers = source.chapter_numbers
    if tuple(item.source_chapter for item in contracts.chapters) != chapter_numbers:
        raise ValueError("planning chapters do not match snapshot")
    fingerprint_payload = {
        "source_snapshot_hash": source.snapshot_hash,
        "chapters": [_chapter_input_payload(item) for item in contracts.chapters],
        "omissions": [_omission_payload(item) for item in contracts.omissions],
    }
    candidate = SplitPlanCandidate(
        migration_id=contracts.migration_id,
        project_id=source.project_id,
        source_edition_id=source.source_edition_id,
        target_edition_id=contracts.target_edition_id,
        source_snapshot_hash=source.snapshot_hash,
        input_fingerprint=_digest(fingerprint_payload),
        units=tuple(unit for chapter in contracts.chapters for unit in chapter.units),
        omissions=contracts.omissions,
    )
    return SplitPlanCandidate(
        migration_id=candidate.migration_id,
        project_id=candidate.project_id,
        source_edition_id=candidate.source_edition_id,
        target_edition_id=candidate.target_edition_id,
        source_snapshot_hash=candidate.source_snapshot_hash,
        input_fingerprint=candidate.input_fingerprint,
        units=candidate.units,
        omissions=candidate.omissions,
        candidate_hash=split_plan_candidate_hash(candidate),
    )


def split_plan_candidate_hash(candidate: SplitPlanCandidate) -> str:
    if not isinstance(candidate, SplitPlanCandidate):
        raise TypeError("candidate must be SplitPlanCandidate")
    return _digest(_candidate_payload(candidate, include_hash=False))


def split_plan_candidate_payload(candidate: SplitPlanCandidate) -> dict[str, object]:
    if candidate.candidate_hash != split_plan_candidate_hash(candidate):
        raise ValueError("candidate_hash mismatch")
    return _candidate_payload(candidate, include_hash=True)


def split_plan_candidate_from_payload(value: object) -> SplitPlanCandidate:
    fields = {
        "migration_id", "project_id", "source_edition_id", "target_edition_id",
        "source_snapshot_hash", "input_fingerprint", "units", "omissions", "candidate_hash",
    }
    if (not isinstance(value, dict) or set(value) != fields or not isinstance(value["units"], list)
            or not isinstance(value["omissions"], list)):
        raise ValueError("invalid candidate payload")
    units = tuple(_unit_from_payload(item) for item in value["units"])
    return SplitPlanCandidate(
        migration_id=value["migration_id"], project_id=value["project_id"],
        source_edition_id=value["source_edition_id"], target_edition_id=value["target_edition_id"],
        source_snapshot_hash=value["source_snapshot_hash"], input_fingerprint=value["input_fingerprint"],
        units=units, omissions=tuple(_omission_from_payload(item) for item in value["omissions"]),
        candidate_hash=value["candidate_hash"],
    )


def split_plan_review_hash(review: SplitPlanReviewRecord) -> str:
    if not isinstance(review, SplitPlanReviewRecord):
        raise TypeError("review must be SplitPlanReviewRecord")
    return _digest(_review_payload(review, include_hash=False))


def split_plan_review_payload(review: SplitPlanReviewRecord) -> dict[str, object]:
    if review.review_hash != split_plan_review_hash(review):
        raise ValueError("review_hash mismatch")
    return _review_payload(review, include_hash=True)


def split_plan_review_from_payload(value: object) -> SplitPlanReviewRecord:
    fields = {"candidate_hash", "snapshot_hash", "ruleset_version", "blocking_issues", "review_hash"}
    if not isinstance(value, dict) or set(value) != fields or not isinstance(value["blocking_issues"], list):
        raise ValueError("invalid review payload")
    issues = []
    for issue in value["blocking_issues"]:
        if not isinstance(issue, dict) or set(issue) != {"code", "message", "unit_index"}:
            raise ValueError("invalid review issue payload")
        issues.append(SplitPlanIssue(**issue))
    return SplitPlanReviewRecord(
        candidate_hash=value["candidate_hash"], snapshot_hash=value["snapshot_hash"],
        ruleset_version=value["ruleset_version"], blocking_issues=tuple(issues),
        review_hash=value["review_hash"],
    )


def _candidate_payload(candidate: SplitPlanCandidate, *, include_hash: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "migration_id": candidate.migration_id,
        "project_id": candidate.project_id,
        "source_edition_id": candidate.source_edition_id,
        "target_edition_id": candidate.target_edition_id,
        "source_snapshot_hash": candidate.source_snapshot_hash,
        "input_fingerprint": candidate.input_fingerprint,
        "units": [_unit_payload(unit) for unit in candidate.units],
        "omissions": [_omission_payload(item) for item in candidate.omissions],
    }
    if include_hash:
        payload["candidate_hash"] = candidate.candidate_hash
    return payload


def _chapter_input_payload(value: SourceChapterPlanningInput) -> dict[str, object]:
    return {
        "source_chapter": value.source_chapter,
        "contract_hash": value.contract_hash,
        "pov_plan_hash": value.pov_plan_hash,
        "scene_plan_hash": value.scene_plan_hash,
        "units": [_unit_payload(item) for item in value.units],
    }


def _omission_payload(value: SplitPlanOmission) -> dict[str, object]:
    return {
        "source_fragments": [_fragment_payload(item) for item in value.source_fragments],
        "snapshot_hash": value.snapshot_hash,
        "reason": value.reason,
        "evidence": value.evidence,
        "impact": value.impact,
    }


def _omission_from_payload(value: object) -> SplitPlanOmission:
    fields = {"source_fragments", "snapshot_hash", "reason", "evidence", "impact"}
    if not isinstance(value, dict) or set(value) != fields or not isinstance(value["source_fragments"], list):
        raise ValueError("invalid omission payload")
    return SplitPlanOmission(
        source_fragments=tuple(_fragment_from_payload(item) for item in value["source_fragments"]),
        snapshot_hash=value["snapshot_hash"], reason=value["reason"],
        evidence=value["evidence"], impact=value["impact"],
    )


def _unit_payload(unit: DramaticUnit) -> dict[str, object]:
    return {
        "function": unit.function,
        "scene_scope": list(unit.scene_scope),
        "conflict": unit.conflict,
        "choice_or_discovery": unit.choice_or_discovery,
        "outcome": unit.outcome,
        "information_reveal": unit.information_reveal,
        "technology_state": unit.technology_state,
        "state_shift": unit.state_shift,
        "ending_hook": unit.ending_hook,
        "source_fragments": [
            {
                "source_chapter": item.source_chapter,
                "paragraph_start": item.paragraph_start,
                "paragraph_end": item.paragraph_end,
                "text_hash": item.text_hash,
            }
            for item in unit.source_fragments
        ],
        "estimated_chinese_chars": unit.estimated_chinese_chars,
        "boundary_basis": unit.boundary_basis,
        "dialogue_closed": unit.dialogue_closed,
        "conflict_status": unit.conflict_status.value,
        "choice_status": unit.choice_status.value,
        "closure_evidence": [
            {
                "dimension": item.dimension.value,
                "source_chapter": item.source_chapter,
                "paragraph_ordinal": item.paragraph_ordinal,
                "paragraph_hash": item.paragraph_hash,
                "excerpt": item.excerpt,
                "start_offset": item.start_offset,
                "end_offset": item.end_offset,
            }
            for item in unit.closure_evidence
        ],
    }


def _unit_from_payload(value: object) -> DramaticUnit:
    fields = {
        "function", "scene_scope", "conflict", "choice_or_discovery", "outcome",
        "information_reveal", "technology_state", "state_shift", "ending_hook",
        "source_fragments", "estimated_chinese_chars", "boundary_basis", "dialogue_closed",
        "conflict_status", "choice_status", "closure_evidence",
    }
    if (
        not isinstance(value, dict) or set(value) != fields
        or not isinstance(value["source_fragments"], list)
        or not isinstance(value["closure_evidence"], list)
        or not isinstance(value["scene_scope"], list)
    ):
        raise ValueError("invalid dramatic unit payload")
    fragments = tuple(_fragment_from_payload(item) for item in value["source_fragments"])
    closure_evidence = tuple(_closure_evidence_from_payload(item) for item in value["closure_evidence"])
    return DramaticUnit(
        function=value["function"], scene_scope=tuple(value["scene_scope"]), conflict=value["conflict"],
        choice_or_discovery=value["choice_or_discovery"], state_shift=value["state_shift"],
        outcome=value["outcome"], information_reveal=value["information_reveal"],
        technology_state=value["technology_state"],
        ending_hook=value["ending_hook"], source_fragments=tuple(fragments),
        estimated_chinese_chars=value["estimated_chinese_chars"],
        boundary_basis=value["boundary_basis"], dialogue_closed=value["dialogue_closed"],
        conflict_status=BoundaryStatus(value["conflict_status"]),
        choice_status=BoundaryStatus(value["choice_status"]), closure_evidence=closure_evidence,
    )


def validate_archive_view(source: VerifiedSourceArchiveView) -> None:
    if not isinstance(source, VerifiedSourceArchiveView):
        raise TypeError("verified archive view is required")
    if source.chapter_numbers != tuple(range(5, 33)):
        raise ValueError("verified archive must contain exact source range 5..32")
    positions = tuple((item.chapter_number, item.paragraph_ordinal) for item in source.iter_paragraphs())
    if not positions or any(not 5 <= chapter <= 32 for chapter, _ in positions):
        raise ValueError("verified archive paragraph range invalid")
    for chapter in source.chapter_numbers:
        ordinals = tuple(item.paragraph_ordinal for item in source.load_paragraphs(chapter))
        if ordinals != tuple(range(1, len(ordinals) + 1)):
            raise ValueError("verified archive paragraphs must be contiguous and ordered")


def _review_closure_evidence(
    unit: DramaticUnit, source: VerifiedSourceArchiveView,
) -> tuple[str, ...]:
    expected_dimensions = set(ClosureDimension)
    dimensions = tuple(item.dimension for item in unit.closure_evidence)
    errors: list[str] = []
    if set(dimensions) != expected_dimensions or len(dimensions) != len(expected_dimensions):
        errors.append("closure_dimensions_invalid")
    fragment_keys = {
        (item.source_chapter, item.paragraph_start) for item in unit.source_fragments
        if item.paragraph_start == item.paragraph_end
    }
    evidence_identities: set[tuple[int, int, int, int]] = set()
    locator_keys: set[tuple[int, int]] = set()
    occupied: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for evidence in unit.closure_evidence:
        locator = (evidence.source_chapter, evidence.paragraph_ordinal)
        try:
            paragraph = source.load_paragraph(*locator)
        except Exception:
            errors.append("closure_locator_invalid")
            continue
        if locator not in fragment_keys or paragraph.paragraph_hash != evidence.paragraph_hash:
            errors.append("closure_hash_or_fragment_invalid")
        if (
            evidence.end_offset > len(paragraph.text)
            or paragraph.text[evidence.start_offset:evidence.end_offset] != evidence.excerpt
        ):
            errors.append("closure_excerpt_invalid")
        identity = (*locator, evidence.start_offset, evidence.end_offset)
        if identity in evidence_identities:
            errors.append("closure_evidence_reused")
        evidence_identities.add(identity)
        locator_keys.add(locator)
        prior_spans = occupied.setdefault(locator, [])
        if any(
            max(evidence.start_offset, start) < min(evidence.end_offset, end)
            for start, end in prior_spans
        ):
            errors.append("closure_evidence_overlap")
        prior_spans.append((evidence.start_offset, evidence.end_offset))
    if len(locator_keys) < 2:
        errors.append("closure_evidence_not_distinct")
    if unit.source_fragments:
        last = unit.source_fragments[-1]
        dialogue = next(
            (item for item in unit.closure_evidence if item.dimension is ClosureDimension.DIALOGUE), None,
        )
        if dialogue is None or (dialogue.source_chapter, dialogue.paragraph_ordinal) != (
            last.source_chapter, last.paragraph_end,
        ):
            errors.append("dialogue_evidence_not_at_boundary")
    try:
        text = "\n".join(
            source.load_paragraph(item.source_chapter, item.paragraph_start).text
            for item in unit.source_fragments
        )
        if not _quotes_balanced(text):
            errors.append("dialogue_unbalanced")
    except Exception:
        errors.append("fragment_text_unavailable")
    return tuple(errors)


def _quotes_balanced(text: str) -> bool:
    pairs = {"“": "”", "‘": "’"}
    closing = set(pairs.values())
    stack: list[str] = []
    escaped = False
    for char in text:
        if char == "\\" and not escaped:
            escaped = True
            continue
        if not escaped:
            if char in pairs:
                stack.append(pairs[char])
            elif char in closing:
                if not stack or stack[-1] != char:
                    return False
                stack.pop()
            elif char == '"':
                if stack and stack[-1] == '"':
                    stack.pop()
                else:
                    stack.append('"')
        escaped = False
    return not stack


def _review_payload(review: SplitPlanReviewRecord, *, include_hash: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_hash": review.candidate_hash,
        "snapshot_hash": review.snapshot_hash,
        "ruleset_version": review.ruleset_version,
        "blocking_issues": [
            {"code": item.code, "message": item.message, "unit_index": item.unit_index}
            for item in review.blocking_issues
        ],
    }
    if include_hash:
        payload["review_hash"] = review.review_hash
    return payload


def _fragment_payload(item: SourceFragment) -> dict[str, object]:
    return {
        "source_chapter": item.source_chapter, "paragraph_start": item.paragraph_start,
        "paragraph_end": item.paragraph_end, "text_hash": item.text_hash,
    }


def _fragment_from_payload(value: object) -> SourceFragment:
    fields = {"source_chapter", "paragraph_start", "paragraph_end", "text_hash"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("invalid source fragment payload")
    return SourceFragment(**value)


def _closure_evidence_from_payload(value: object) -> ClosureEvidence:
    fields = {
        "dimension", "source_chapter", "paragraph_ordinal", "paragraph_hash", "excerpt",
        "start_offset", "end_offset",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("invalid closure evidence payload")
    return ClosureEvidence(
        dimension=ClosureDimension(value["dimension"]),
        source_chapter=value["source_chapter"], paragraph_ordinal=value["paragraph_ordinal"],
        paragraph_hash=value["paragraph_hash"], excerpt=value["excerpt"],
        start_offset=value["start_offset"], end_offset=value["end_offset"],
    )


def _deduplicate(issues: list[SplitPlanIssue]) -> tuple[SplitPlanIssue, ...]:
    seen: set[tuple[str, int | None]] = set()
    result = []
    for issue in issues:
        key = (issue.code, issue.unit_index)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return tuple(result)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


def _require_hash(value: object, name: str) -> None:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256")
