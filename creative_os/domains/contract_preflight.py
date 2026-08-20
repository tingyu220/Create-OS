from __future__ import annotations

from dataclasses import dataclass
from re import fullmatch
from typing import Callable

from creative_os.domains.contract_issue import ContractIssue, EvidenceCheck
from creative_os.domains.narrative_causality import CAUSAL_FIELD_PATHS_V1, CausalAnalysisResult
from creative_os.domains.narrative_decision import (
    ArcPhase,
    CandidateImpact,
    CandidateValueState,
    ChoiceStatus,
    NarrativeDecision,
    NullablePlan,
)
from creative_os.domains.narrative_evidence import (
    EvidenceIntegrityValidator,
    EvidenceRef,
    EvidenceRole,
    ResolvedEvidenceSource,
)


_REQUIRED_NON_EMPTY_ARRAYS = frozenset(
    {
        "future_pressures",
        "chapter_contract.functions",
        "chapter_contract.protagonist_choice.alternatives",
        "chapter_contract.information.reveal",
        "chapter_contract.information.withhold",
    }
)

_CONTROL_FIELDS = (
    "contract_id",
    "contract_version",
    "chapter",
    "profile_id",
    "volume_id",
    "arc_id",
    "schema_version",
    "kind",
    "chapter_contract.chapter_id",
    "chapter_contract.target_chinese_chars",
)

_NULLABLE_PLANS = (
    (
        "chapter_contract.information.misdirect",
        "chapter_contract.information.misdirect.not_applicable_reason",
    ),
    ("chapter_contract.foreshadow_actions", "chapter_contract.foreshadow_actions.not_applicable_reason"),
    ("chapter_contract.forbidden", "chapter_contract.forbidden.not_applicable_reason"),
)


@dataclass(frozen=True, slots=True)
class PreflightResult:
    issues: tuple[ContractIssue, ...]

    @property
    def is_ready(self) -> bool:
        return not any(issue.blocking for issue in self.issues)


class ContractPreflightValidator:
    """Pure, fail-closed validation for one chapter-contract candidate."""

    def validate(
        self,
        candidate: object,
        sources: object,
        causal_result: object,
    ) -> PreflightResult:
        if not isinstance(candidate, NarrativeDecision):
            return PreflightResult(
                (_issue("contract_preflight_failed", "contract", "恢复完整候选后重新执行预检。"),)
            )

        issues: list[ContractIssue] = []
        try:
            candidate.validate()
        except Exception:
            issues.append(_issue("incomplete_contract", "contract", "修复合同 schema 和字段类型。"))

        try:
            required_roles, field_issues = _required_evidence_roles(candidate)
            issues.extend(field_issues)
        except Exception:
            required_roles = {}
            issues.append(_issue("contract_preflight_failed", "contract", "恢复可读取的合同字段后重新预检。"))

        try:
            integrity_validator = _integrity_validator(sources)
        except Exception:
            integrity_validator = None
            issues.append(
                _issue(
                    "evidence_source_unavailable",
                    "chapter_contract.intent_evidence_bindings",
                    "恢复权威证据来源集合后重新预检。",
                )
            )

        try:
            issues.extend(_validate_evidence(candidate, required_roles, integrity_validator))
        except Exception:
            issues.append(
                _issue(
                    "contract_preflight_failed",
                    "chapter_contract.intent_evidence_bindings",
                    "修复字段证据绑定后重新预检。",
                )
            )

        try:
            issues.extend(_validate_causality(candidate, causal_result))
        except Exception:
            issues.append(
                _issue(
                    "causal_analysis_failed",
                    "chapter_contract.optional_candidates",
                    "重新执行完整因果分析。",
                )
            )

        return PreflightResult(_deduplicate_issues(issues))


def _required_evidence_roles(
    candidate: NarrativeDecision,
) -> tuple[dict[str, EvidenceRole], tuple[ContractIssue, ...]]:
    required: dict[str, EvidenceRole] = {}
    issues: list[ContractIssue] = []

    for path in _CONTROL_FIELDS:
        try:
            value = _read_field(candidate, path)
        except Exception:
            issues.append(_issue("incomplete_contract", path, "补全必填控制字段。"))
            continue
        if _invalid_control(path, value, candidate):
            issues.append(_issue("incomplete_contract", path, "补全有效的必填控制字段。"))

    for stable_path in CAUSAL_FIELD_PATHS_V1:
        if not stable_path.endswith("[*]"):
            required[stable_path] = EvidenceRole.INTENT
            try:
                value = _read_field(candidate, stable_path)
            except Exception:
                issues.append(_issue("incomplete_contract", stable_path, "补全因果字段。"))
                continue
            if _invalid_intent_value(stable_path, value):
                issues.append(_issue("incomplete_contract", stable_path, "将 unknown 字段补充为确定值。"))
            continue

        parent_path = stable_path[:-3]
        try:
            values = _read_field(candidate, parent_path)
        except Exception:
            issues.append(_issue("incomplete_contract", parent_path, "恢复可读取的数组字段。"))
            continue
        if not isinstance(values, tuple):
            issues.append(_issue("incomplete_contract", parent_path, "数组字段必须使用稳定 tuple。"))
            continue
        if not values and parent_path in _REQUIRED_NON_EMPTY_ARRAYS:
            issues.append(_issue("incomplete_contract", parent_path, "补全至少一个数组元素。"))
        for index, value in enumerate(values):
            concrete_path = f"{parent_path}[{index}]"
            required[concrete_path] = EvidenceRole.INTENT
            if _invalid_intent_value(concrete_path, value):
                issues.append(_issue("incomplete_contract", concrete_path, "将 unknown 数组元素补充为确定值。"))

    choice = candidate.chapter_contract.protagonist_choice
    status_path = "chapter_contract.protagonist_choice.status"
    if choice.status != ChoiceStatus.COMPLETE:
        issues.append(_issue("incomplete_contract", status_path, "人物选择必须为 complete。"))
    if not isinstance(choice.missing_fields, tuple):
        issues.append(
            _issue(
                "incomplete_contract",
                "chapter_contract.protagonist_choice.missing_fields",
                "missing_fields 必须使用稳定 tuple。",
            )
        )
    else:
        for index, missing_field in enumerate(choice.missing_fields):
            path = f"chapter_contract.protagonist_choice.missing_fields[{index}]"
            required[path] = EvidenceRole.INTENT
            issues.append(_issue("incomplete_contract", path, f"补全人物选择字段 {missing_field}。"))

    for plan_path, reason_path in _NULLABLE_PLANS:
        try:
            plan = _read_field(candidate, plan_path)
        except Exception:
            issues.append(_issue("invalid_not_applicable_reason", reason_path, "恢复可读取的可空计划。"))
            continue
        if not isinstance(plan, NullablePlan):
            issues.append(_issue("invalid_not_applicable_reason", reason_path, "可空计划必须使用 NullablePlan。"))
            continue
        reason = plan.not_applicable_reason
        if plan.values:
            if reason is not None:
                issues.append(
                    _issue(
                        "invalid_not_applicable_reason",
                        reason_path,
                        "非空数组不得携带 not_applicable_reason。",
                    )
                )
            continue
        if not isinstance(reason, str) or not reason.strip():
            issues.append(
                _issue(
                    "invalid_not_applicable_reason",
                    reason_path,
                    "空数组必须提供非空 not_applicable_reason。",
                )
            )
            continue
        required[reason_path] = EvidenceRole.NON_APPLICABILITY

    return required, tuple(issues)


def _validate_evidence(
    candidate: NarrativeDecision,
    required_roles: dict[str, EvidenceRole],
    integrity_validator: EvidenceIntegrityValidator | None,
) -> tuple[ContractIssue, ...]:
    issues: list[ContractIssue] = []
    bindings = candidate.chapter_contract.intent_evidence_bindings
    if not isinstance(bindings, tuple):
        return (
            _issue(
                "incomplete_contract",
                "chapter_contract.intent_evidence_bindings",
                "字段证据绑定必须使用稳定 tuple。",
            ),
        )

    by_path: dict[str, list[EvidenceRef]] = {}
    for binding in bindings:
        path = getattr(binding, "field_path", "chapter_contract.intent_evidence_bindings")
        evidence = getattr(binding, "evidence", ())
        if path not in required_roles:
            code = (
                "invalid_not_applicable_reason"
                if path.endswith(".not_applicable_reason")
                else "incomplete_contract"
            )
            issues.append(_issue(code, path, "证据路径必须来自当前候选的真实字段或稳定数组索引。"))
        if not isinstance(evidence, tuple):
            issues.append(_issue("incomplete_contract", path, "字段证据必须使用稳定 tuple。"))
            continue
        for ref in evidence:
            if isinstance(ref, EvidenceRef):
                by_path.setdefault(path, []).append(ref)
            if integrity_validator is not None:
                issues.extend(integrity_validator.validate(ref, path))

    for path, expected_role in required_roles.items():
        refs = by_path.get(path, [])
        matching = tuple(ref for ref in refs if ref.role == expected_role)
        if any(ref.role != expected_role for ref in refs):
            code = (
                "invalid_not_applicable_reason"
                if expected_role == EvidenceRole.NON_APPLICABILITY
                else "incomplete_contract"
            )
            issues.append(_issue(code, path, f"字段证据角色只能是 {expected_role.value}。"))
        if not matching:
            code = (
                "invalid_not_applicable_reason"
                if expected_role == EvidenceRole.NON_APPLICABILITY
                else "incomplete_contract"
            )
            issues.append(_issue(code, path, f"为字段提供 {expected_role.value} EvidenceRef。"))
            continue
        if expected_role == EvidenceRole.INTENT:
            intent_values = {ref.excerpt.strip() for ref in matching if isinstance(ref.excerpt, str)}
            if len(intent_values) > 1:
                issues.append(
                    _issue(
                        "conflicting_intent_evidence",
                        path,
                        "Task 与 Director 的字段意图值冲突，需人工裁决。",
                    )
                )

    return tuple(issues)


def _validate_causality(
    candidate: NarrativeDecision,
    causal_result: object,
) -> tuple[ContractIssue, ...]:
    path = "chapter_contract.optional_candidates"
    if not isinstance(causal_result, CausalAnalysisResult):
        return (_issue("causal_analysis_failed", path, "重新执行完整因果分析。"),)
    if not isinstance(causal_result.issues, tuple) or not all(
        isinstance(issue, ContractIssue) for issue in causal_result.issues
    ):
        return (_issue("causal_analysis_failed", path, "恢复结构有效的因果分析结果。"),)
    issues = list(causal_result.issues)
    if causal_result.resolutions != candidate.chapter_contract.optional_candidates:
        issues.insert(0, _issue("causal_analysis_failed", path, "因果结果必须绑定当前候选。"))
        return tuple(issues)
    if causal_result.field_paths != CAUSAL_FIELD_PATHS_V1:
        issues.append(_issue("causal_analysis_failed", path, "因果结果必须使用完整的版本化字段闭包。"))
    for index, resolution in enumerate(candidate.chapter_contract.optional_candidates):
        candidate_id = getattr(resolution, "candidate_id", None)
        resolution_path = (
            f"{path}[{candidate_id}]"
            if isinstance(candidate_id, str) and candidate_id.strip()
            else f"{path}[{index}]"
        )
        if resolution.affects_current_chapter == CandidateImpact.UNDETERMINED:
            issues.append(_issue("unresolved_causal_candidate", resolution_path, "明确裁决候选是否影响本章。"))
        elif (
            resolution.affects_current_chapter == CandidateImpact.YES
            and resolution.value_state != CandidateValueState.KNOWN
        ):
            issues.append(_issue("unresolved_causal_candidate", resolution_path, "影响本章的候选必须给出确定值。"))
    return tuple(issues)


def _integrity_validator(sources: object) -> EvidenceIntegrityValidator:
    if isinstance(sources, EvidenceIntegrityValidator):
        return sources
    if callable(sources):
        return EvidenceIntegrityValidator(sources)
    if not isinstance(sources, tuple):
        raise TypeError("sources must be an immutable tuple, resolver, or validator")
    by_id: dict[str, ResolvedEvidenceSource] = {}
    for source in sources:
        if not isinstance(source, ResolvedEvidenceSource) or source.source_id in by_id:
            raise ValueError("sources must contain unique ResolvedEvidenceSource values")
        by_id[source.source_id] = source

    resolver: Callable[[str], ResolvedEvidenceSource | None] = by_id.get
    return EvidenceIntegrityValidator(resolver)


def _invalid_control(path: str, value: object, candidate: NarrativeDecision) -> bool:
    chapter = candidate.chapter
    valid_chapter = type(chapter) is int and chapter > 0
    if path == "contract_id":
        return not valid_chapter or value != f"narrative-chapter-{chapter:03d}"
    if path == "chapter_contract.chapter_id":
        return not valid_chapter or value != f"chapter_{chapter:03d}"
    if path in {"contract_version", "chapter", "chapter_contract.target_chinese_chars"}:
        return type(value) is not int or value < 1
    if path == "schema_version":
        return type(value) is not int or value != 2
    if path == "kind":
        return value != "narrative_decision"
    return _is_unknown(value)


def _invalid_intent_value(path: str, value: object) -> bool:
    if path == "arc_phase":
        return not isinstance(value, ArcPhase)
    if path == "chapter_contract.protagonist_choice.status":
        return not isinstance(value, ChoiceStatus)
    return not isinstance(value, str) or not value.strip()


def _is_unknown(value: object) -> bool:
    return value is None or isinstance(value, str) and not value.strip()


def _read_field(value: object, path: str) -> object:
    current = value
    for segment in path.split("."):
        match = fullmatch(r"([a-z_]+)(?:\[([0-9]+)\])?", segment)
        if match is None:
            raise ValueError(f"unsupported field path: {path}")
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
