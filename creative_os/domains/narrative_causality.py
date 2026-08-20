from __future__ import annotations

from dataclasses import dataclass
from re import fullmatch

from creative_os.domains.contract_issue import ContractIssue, EvidenceCheck
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
    field_paths: tuple[str, ...] = CAUSAL_FIELD_PATHS_V1
    ruleset_version: str = CAUSAL_RULESET_VERSION_V1

    @property
    def is_resolved(self) -> bool:
        return not self.issues


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
            candidate.validate()
            self._validate_inputs(profile, fact_snapshots, previous_chapter, change_requests)
            resolutions = candidate.chapter_contract.optional_candidates
            issues = tuple(
                issue
                for resolution in resolutions
                for issue in self._analyze_resolution(candidate, resolution)
            )
            return CausalAnalysisResult(resolutions=resolutions, issues=issues)
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
        path = f"chapter_contract.optional_candidates[{resolution.candidate_id}]"
        if resolution.affects_current_chapter == CandidateImpact.UNDETERMINED:
            return (_issue("unresolved_causal_candidate", path, "由规则或人工明确裁决候选是否影响本章。"),)
        if resolution.affects_current_chapter == CandidateImpact.NO:
            if self._has_valid_decision(resolution):
                return ()
            return (_issue("unresolved_causal_candidate", path, "为不纳入本章的候选保留有效规则或人工裁决。"),)
        if resolution.value_state != CandidateValueState.KNOWN:
            return (_issue("unresolved_causal_candidate", path, "影响本章的候选必须给出确定值。"),)
        if not self._has_valid_decision(resolution):
            return (_issue("unresolved_causal_candidate", path, "为候选提供可追溯的规则或人工裁决。"),)
        if not self._is_formally_included(candidate, resolution):
            return (_issue("unresolved_causal_candidate", path, "将影响本章的候选值纳入其直接引用的正式因果字段。"),)
        return ()

    @staticmethod
    def _has_valid_decision(resolution: OptionalCandidateResolution) -> bool:
        if resolution.decided_by == CandidateDecisionBy.HUMAN:
            return bool(resolution.decision_ref.strip())
        return (
            resolution.decided_by == CandidateDecisionBy.RULE
            and resolution.decision_ref == CAUSAL_RULESET_VERSION_V1
            and CausalDependencyAnalyzer._is_explicit_direct_reference(resolution)
        )

    @staticmethod
    def _is_explicit_direct_reference(resolution: OptionalCandidateResolution) -> bool:
        return bool(resolution.dependency_inputs) and all(
            _is_causal_field_path(path) for path in resolution.dependency_inputs
        )

    @staticmethod
    def _is_formally_included(candidate: NarrativeDecision, resolution: OptionalCandidateResolution) -> bool:
        if resolution.proposed_value is None:
            return False
        return any(
            _is_causal_field_path(path) and _read_field(candidate, path) == resolution.proposed_value
            for path in resolution.dependency_inputs
        )


def _is_causal_field_path(path: str) -> bool:
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
