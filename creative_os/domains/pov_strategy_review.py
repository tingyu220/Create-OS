from __future__ import annotations

from creative_os.domains.pov_strategy_model import POVRisk, POVStrategyCandidateSet, POVStrategyInput
from creative_os.domains.pov_strategy_policy import POVStrategyPolicy
from dataclasses import replace


SUPPORTED_CODES = frozenset({
    "protagonist_absence_unresolved", "protagonist_pov_monopoly",
    "supporting_pov_without_agency", "pov_cannot_serve_chapter_function",
    "supporting_outcome_only_reported_to_protagonist", "pov_transition_without_arc_reason",
})


class POVStrategyReviewBlockedError(ValueError):
    pass


def review_pov_strategy(
    input: POVStrategyInput,
    candidates: POVStrategyCandidateSet,
    policy: POVStrategyPolicy,
) -> tuple[POVRisk, ...]:
    option = candidates.recommended
    refs = option.evidence_refs or input.evidence
    risks: list[POVRisk] = []
    if option.primary_owner != policy.protagonist_id and input.protagonist_load.unresolved_consequences:
        risks.append(_risk("protagonist_absence_unresolved", "high", refs, "主角缺席期间的后果仍未承接"))
    supporting = [item for item in candidates.alternatives if item.primary_owner != policy.protagonist_id]
    if option.primary_owner == policy.protagonist_id and input.protagonist_load.consecutive_primary_pov >= policy.monopoly_review_after and supporting:
        risks.append(_risk("protagonist_pov_monopoly", "medium", refs, "主角连续占用且存在可行动配角"))
    agency = option.agency
    if option.primary_owner != policy.protagonist_id and (
        not agency.actor or not agency.choice_boundary or agency.plausible_cost_ref is None
        or not option.mainline_change.target_state_ref
    ):
        risks.append(_risk("supporting_pov_without_agency", "blocking", refs, "配角缺少独立选择或代价"))
    if not option.function_fits:
        risks.append(_risk("pov_cannot_serve_chapter_function", "blocking", refs, "POV无法服务章节功能"))
    if option.primary_owner != policy.protagonist_id and option.mainline_change.change_type == "report":
        risks.append(_risk("supporting_outcome_only_reported_to_protagonist", "high", refs, "结果只向主角汇报"))
    if input.recent_pov_history and option.primary_owner != input.recent_pov_history[-1].primary_owner and not option.transition.arc_reason.strip():
        risks.append(_risk("pov_transition_without_arc_reason", "high", refs, "POV切换缺少Arc理由"))
    return tuple(risks)


def review_selected_pov(input, candidates, option, policy):
    """Reviewer 始终审查实际选中项，包括人工覆盖。"""
    return review_pov_strategy(input, replace(candidates, recommended=option), policy)


review_pov_strategy.supported_codes = SUPPORTED_CODES


def assert_pov_strategy_admissible(input, candidates, policy) -> None:
    risks = review_pov_strategy(input, candidates, policy)
    blocking = [risk for risk in risks if risk.code in policy.blocking_risks or risk.severity == "blocking"]
    if blocking:
        raise POVStrategyReviewBlockedError(",".join(risk.code for risk in blocking))


def _risk(code, severity, refs, explanation):
    return POVRisk(code, severity, tuple(refs), explanation)
