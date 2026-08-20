from __future__ import annotations

from dataclasses import dataclass, replace
from re import fullmatch

from creative_os.domains.contract_issue import ContractIssue, EvidenceCheck
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import (
    CandidateDecisionBy,
    CandidateImpact,
    CandidateValueState,
    NarrativeDecision,
    OptionalCandidateResolution,
)


CAUSAL_FIELD_PATHS_V1 = (
    "arc_phase",
    "arc_goal",
    "inherited_pressure",
    "future_pressures[*]",
    "chapter_contract.functions[*]",
    "chapter_contract.dramatic_question",
    "chapter_contract.protagonist_choice.status",
    "chapter_contract.protagonist_choice.actor",
    "chapter_contract.protagonist_choice.action",
    "chapter_contract.protagonist_choice.alternatives[*]",
    "chapter_contract.protagonist_choice.cost",
    "chapter_contract.protagonist_choice.consequence",
    "chapter_contract.reader_change.before",
    "chapter_contract.reader_change.after",
    "chapter_contract.information.reveal[*]",
    "chapter_contract.information.withhold[*]",
    "chapter_contract.information.misdirect.values[*]",
    "chapter_contract.pressure_curve.start",
    "chapter_contract.pressure_curve.turn",
    "chapter_contract.pressure_curve.end",
    "chapter_contract.foreshadow_actions.values[*]",
    "chapter_contract.ending_shift",
    "chapter_contract.forbidden.values[*]",
)

CAUSAL_RULESET_VERSION_V1 = "causal-rules-v1"


@dataclass(frozen=True, slots=True)
class CausalAnalysisResult:
    """Fail-closed causal analysis for one complete chapter-contract candidate."""

    resolutions: tuple[OptionalCandidateResolution, ...]
    issues: tuple[ContractIssue, ...]
    candidate_content_hash: str = ""
    field_paths: tuple[str, ...] = CAUSAL_FIELD_PATHS_V1
    ruleset_version: str = CAUSAL_RULESET_VERSION_V1

    @property
    def is_resolved(self) -> bool:
        return (
            not self.issues
            and fullmatch(r"[0-9a-f]{64}", self.candidate_content_hash) is not None
            and self.field_paths == CAUSAL_FIELD_PATHS_V1
            and self.ruleset_version == CAUSAL_RULESET_VERSION_V1
        )


class CausalDependencyAnalyzer:
    """Checks only explicit direct references; every inference remains fail-closed."""

    def analyze(
        self,
        candidate: object,
        profile: object,
        fact_snapshots: object,
        previous_chapter: object,
        change_requests: object,
    ) -> CausalAnalysisResult:
        try:
            if not isinstance(candidate, NarrativeDecision):
                raise TypeError("candidate must be a NarrativeDecision")
            self._validate_inputs(profile, fact_snapshots, previous_chapter, change_requests)
            resolutions, validation_issues = self._validate_candidate(candidate)
            if validation_issues:
                return CausalAnalysisResult(resolutions=resolutions, issues=validation_issues)
            candidate.validate()
            candidate_content_hash = NarrativeDecisionCodec.content_hash(candidate)
            issues = tuple(
                issue
                for resolution in resolutions
                for issue in self._analyze_resolution(candidate, resolution)
            )
            return CausalAnalysisResult(
                resolutions=resolutions,
                issues=issues,
                candidate_content_hash=candidate_content_hash,
            )
        except Exception:
            return CausalAnalysisResult(
                resolutions=(),
                issues=(
                    _issue(
                        "causal_analysis_failed",
                        "chapter_contract.optional_candidates",
                        "恢复完整候选与权威输入后重新执行因果分析。",
                    ),
                ),
            )

    def validate_result(
        self,
        candidate: object,
        result: object,
    ) -> tuple[ContractIssue, ...]:
        path = "chapter_contract.optional_candidates"
        issues: list[ContractIssue] = []
        if not isinstance(result, CausalAnalysisResult):
            return (_issue("causal_analysis_failed", path, "恢复完整因果结果后重新分析。"),)
        if isinstance(result.issues, tuple) and all(isinstance(issue, ContractIssue) for issue in result.issues):
            issues.extend(result.issues)
        else:
            issues.append(_issue("causal_analysis_failed", path, "因果 issues 必须是 ContractIssue tuple。"))
        if not isinstance(candidate, NarrativeDecision):
            issues.append(_issue("causal_analysis_failed", path, "恢复完整候选后重新分析。"))
            return _deduplicate_issues(issues)

        try:
            resolutions, validation_issues = self._validate_candidate(candidate)
            issues.extend(validation_issues)
        except Exception:
            resolutions = ()
            issues.append(_issue("causal_analysis_failed", path, "恢复候选裁决集合后重新分析。"))

        if not isinstance(result.resolutions, tuple) or result.resolutions != resolutions:
            issues.append(_issue("causal_analysis_failed", path, "因果结果必须绑定当前候选的完整裁决集合。"))
        else:
            valid_resolutions: list[OptionalCandidateResolution] = []
            for resolution in resolutions:
                try:
                    resolution.validate()
                except Exception:
                    continue
                valid_resolutions.append(resolution)
            try:
                issues.extend(
                    issue
                    for resolution in valid_resolutions
                    for issue in self._analyze_resolution(candidate, resolution)
                )
            except Exception:
                issues.append(_issue("causal_analysis_failed", path, "重新验证候选因果语义。"))

        if result.ruleset_version != CAUSAL_RULESET_VERSION_V1:
            issues.append(_issue("causal_analysis_failed", path, "因果结果必须使用当前规则版本。"))
        if result.field_paths != CAUSAL_FIELD_PATHS_V1:
            issues.append(_issue("causal_analysis_failed", path, "因果结果必须使用完整字段闭包。"))
        try:
            candidate.validate()
            expected_hash = NarrativeDecisionCodec.content_hash(candidate)
        except Exception:
            issues.append(_issue("causal_analysis_failed", path, "修复候选后重新计算因果绑定哈希。"))
        else:
            if result.candidate_content_hash != expected_hash:
                issues.append(_issue("causal_analysis_failed", path, "因果结果必须绑定当前候选内容哈希。"))
        return _deduplicate_issues(issues)

    @staticmethod
    def _validate_candidate(
        candidate: NarrativeDecision,
    ) -> tuple[tuple[OptionalCandidateResolution, ...], tuple[ContractIssue, ...]]:
        raw_resolutions = candidate.chapter_contract.optional_candidates
        if not isinstance(raw_resolutions, tuple):
            return (), (
                _issue(
                    "invalid_causal_candidate",
                    "chapter_contract.optional_candidates",
                    "可选候选必须是不可变 tuple。",
                ),
            )
        try:
            replace(
                candidate,
                chapter_contract=replace(candidate.chapter_contract, optional_candidates=()),
            ).validate()
        except Exception:
            return (), (
                _issue(
                    "causal_analysis_failed",
                    "chapter_contract",
                    "恢复完整章节合同后重新执行因果分析。",
                ),
            )

        resolutions = tuple(
            resolution for resolution in raw_resolutions if isinstance(resolution, OptionalCandidateResolution)
        )
        issues: list[ContractIssue] = []
        for index, resolution in enumerate(raw_resolutions):
            field_path = CausalDependencyAnalyzer._resolution_path(resolution, index)
            if not isinstance(resolution, OptionalCandidateResolution):
                issues.append(
                    _issue(
                        "invalid_causal_candidate",
                        field_path,
                        "可选候选必须使用 OptionalCandidateResolution。",
                    )
                )
                continue
            try:
                resolution.validate()
            except Exception:
                issues.append(
                    _issue(
                        "invalid_causal_candidate",
                        field_path,
                        "修复可选候选的完整模型字段后重新分析。",
                    )
                )
        return resolutions, tuple(issues)

    @staticmethod
    def _resolution_path(resolution: object, index: int) -> str:
        candidate_id = getattr(resolution, "candidate_id", None)
        if isinstance(candidate_id, str) and candidate_id.strip():
            return f"chapter_contract.optional_candidates[{candidate_id}]"
        return f"chapter_contract.optional_candidates[{index}]"

    @staticmethod
    def _validate_inputs(
        profile: object,
        fact_snapshots: object,
        previous_chapter: object,
        change_requests: object,
    ) -> None:
        if not hasattr(profile, "validate"):
            raise TypeError("profile must be a narrative project profile")
        profile.validate()
        if not isinstance(fact_snapshots, tuple):
            raise TypeError("fact_snapshots must be a tuple")
        if previous_chapter is not None and not isinstance(previous_chapter, NarrativeDecision):
            raise TypeError("previous_chapter must be a NarrativeDecision or None")
        if not isinstance(change_requests, tuple):
            raise TypeError("change_requests must be a tuple")

    def _analyze_resolution(
        self,
        candidate: NarrativeDecision,
        resolution: OptionalCandidateResolution,
    ) -> tuple[ContractIssue, ...]:
        path = self._resolution_path(resolution, 0)
        if not self._has_resolvable_concrete_dependencies(candidate, resolution):
            return (_issue("unresolved_causal_candidate", path, "候选依赖必须使用存在的正式因果字段或稳定数组索引。"),)
        if resolution.affects_current_chapter == CandidateImpact.UNDETERMINED:
            return (_issue("unresolved_causal_candidate", path, "由规则或人工明确裁决候选是否影响本章。"),)
        if resolution.affects_current_chapter == CandidateImpact.NO:
            if self._has_valid_decision(candidate, resolution):
                return ()
            return (_issue("unresolved_causal_candidate", path, "为不纳入本章的候选保留有效规则或人工裁决。"),)
        if resolution.value_state != CandidateValueState.KNOWN:
            return (_issue("unresolved_causal_candidate", path, "影响本章的候选必须给出确定值。"),)
        if not self._has_valid_decision(candidate, resolution):
            return (_issue("unresolved_causal_candidate", path, "为候选提供可追溯的规则或人工裁决。"),)
        if not self._is_formally_included(candidate, resolution):
            return (_issue("unresolved_causal_candidate", path, "将影响本章的候选值纳入其直接引用的正式因果字段。"),)
        return ()

    @staticmethod
    def _has_valid_decision(candidate: NarrativeDecision, resolution: OptionalCandidateResolution) -> bool:
        if resolution.decided_by == CandidateDecisionBy.HUMAN:
            return bool(resolution.decision_ref.strip())
        return (
            resolution.decided_by == CandidateDecisionBy.RULE
            and resolution.decision_ref == CAUSAL_RULESET_VERSION_V1
            and CausalDependencyAnalyzer._is_explicit_direct_reference(candidate, resolution)
        )

    @staticmethod
    def _is_explicit_direct_reference(candidate: NarrativeDecision, resolution: OptionalCandidateResolution) -> bool:
        return CausalDependencyAnalyzer._has_resolvable_concrete_dependencies(candidate, resolution)

    @staticmethod
    def _has_resolvable_concrete_dependencies(
        candidate: NarrativeDecision,
        resolution: OptionalCandidateResolution,
    ) -> bool:
        return bool(resolution.dependency_inputs) and all(
            _is_concrete_causal_field_path(path) and _can_read_field(candidate, path)
            for path in resolution.dependency_inputs
        )

    @staticmethod
    def _is_formally_included(candidate: NarrativeDecision, resolution: OptionalCandidateResolution) -> bool:
        if resolution.proposed_value is None:
            return False
        return any(
            _is_concrete_causal_field_path(path)
            and _can_read_field(candidate, path)
            and _read_field(candidate, path) == resolution.proposed_value
            for path in resolution.dependency_inputs
        )


def _is_concrete_causal_field_path(path: object) -> bool:
    if not isinstance(path, str) or "[*]" in path:
        return False
    if path in CAUSAL_FIELD_PATHS_V1:
        return True
    for stable_path in CAUSAL_FIELD_PATHS_V1:
        if not stable_path.endswith("[*]"):
            continue
        prefix = stable_path[:-3]
        index = path[len(prefix) :] if path.startswith(prefix) else ""
        if fullmatch(r"\[0\]|\[[1-9][0-9]*\]", index):
            return True
    return False


def _can_read_field(value: object, path: str) -> bool:
    try:
        _read_field(value, path)
    except (AttributeError, IndexError, TypeError, ValueError):
        return False
    return True


def _read_field(value: object, path: str) -> object:
    current = value
    for segment in path.split("."):
        match = fullmatch(r"([a-z_]+)(?:\[([0-9]+)\])?", segment)
        if match is None:
            raise ValueError(f"unsupported causal field path: {path}")
        current = getattr(current, match.group(1))
        if match.group(2) is not None:
            current = current[int(match.group(2))]
    return current


def _issue(code: str, field_path: str, repair_hint: str) -> ContractIssue:
    return ContractIssue(
        code=code,
        severity="error",
        blocking=True,
        field_path=field_path,
        evidence_checks=(EvidenceCheck(code=code, passed=False, detail=repair_hint),),
        repair_hint=repair_hint,
    )


def _deduplicate_issues(issues: list[ContractIssue]) -> tuple[ContractIssue, ...]:
    result: list[ContractIssue] = []
    seen: set[ContractIssue] = set()
    for issue in issues:
        if issue not in seen:
            seen.add(issue)
            result.append(issue)
    return tuple(result)
