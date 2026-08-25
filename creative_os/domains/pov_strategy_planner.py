from __future__ import annotations

from creative_os.domains.pov_strategy_model import (
    MainlineChangeProposal, POVOption, POVStrategyCandidateSet, POVStrategyInput,
    RhythmOutlook, SupportingAgencyBoundary, TransitionReason,
)
from creative_os.domains.pov_strategy_policy import POVStrategyPolicy


class POVStrategyPlanningError(ValueError):
    pass


class POVStrategyPlanner:
    """只基于已装配输入做确定性排序，不读写外部状态。"""

    def plan(self, input: POVStrategyInput, policy: POVStrategyPolicy) -> POVStrategyCandidateSet:
        input.validate_fingerprint()
        policy.validate()
        options = eligible_options(input, policy)
        if not options:
            raise POVStrategyPlanningError("no_viable_pov_candidate")
        ranked = rank_options(options, input, policy)
        result = POVStrategyCandidateSet(
            id=f"pov-strategy-{input.target_chapter:03d}",
            target_chapter=input.target_chapter,
            input_fingerprint=input.baseline_fingerprint,
            policy_version=policy.version,
            generated_at=input.assembled_at,
            expires_when=("source_or_policy_changed", "target_chapter_changed", "contract_activated"),
            recommended=ranked[0],
            alternatives=ranked[1:3],
            rhythm_outlook=_outlook(input),
            risks=(),
        )
        result.validate()
        return result


def eligible_options(input: POVStrategyInput, policy: POVStrategyPolicy) -> tuple[POVOption, ...]:
    functions = set(input.chapter_needs.functions)
    required = functions | set(input.chapter_needs.required_scene_capabilities) | set(input.chapter_needs.technology_roles)
    previous = input.recent_pov_history[-1].primary_owner if input.recent_pov_history else "none"
    result = []
    for pressure in input.character_pressures:
        if policy.eligible_pov_ids and pressure.character_id not in policy.eligible_pov_ids:
            continue
        capability = next((item for item in pressure.agency_capabilities if required.issubset(set(item.serves_functions) | {item.id})), None)
        if capability is None:
            continue
        if not pressure.unfinished_goals or not pressure.pending_choices or not pressure.unpaid_costs:
            continue
        evidence = capability.evidence_refs
        option = POVOption(
            id=f"option-{pressure.character_id}",
            primary_owner=pressure.character_id,
            protagonist_present=pressure.character_id == policy.protagonist_id,
            rationale=f"{pressure.character_id}能够以{capability.id}承接当前章节功能",
            function_fits=tuple(value for value in dict.fromkeys((
                *input.chapter_needs.functions,
                *input.chapter_needs.required_scene_capabilities,
                *input.chapter_needs.technology_roles,
            )) if value in capability.serves_functions),
            benefits=("直接改变主线状态",),
            tradeoffs=(),
            cannot_serve=(),
            mainline_change=MainlineChangeProposal(capability.target_state_ref, "choose", capability.id, evidence),
            agency=SupportingAgencyBoundary(
                pressure.character_id, pressure.unfinished_goals[0], pressure.pending_choices[0],
                "必须在章节内作出可改变主线的选择", pressure.unpaid_costs[0],
            ),
            transition=TransitionReason(previous, input.arc_state.current_pressure, input.arc_state.evidence_refs),
            evidence_refs=tuple(dict.fromkeys((*evidence, *input.arc_state.evidence_refs))),
        )
        result.append(option)
    return tuple(result)


def rank_options(options: tuple[POVOption, ...], input: POVStrategyInput, policy: POVStrategyPolicy) -> tuple[POVOption, ...]:
    unresolved = bool(input.unclaimed_consequences or input.protagonist_load.unresolved_consequences)

    def key(option: POVOption) -> tuple[int, int, int, str]:
        consequence_fit = int(unresolved and option.primary_owner == policy.protagonist_id)
        function_fit = len(option.function_fits)
        direct_change = int(option.mainline_change.change_type != "report")
        return consequence_fit, function_fit, direct_change, option.primary_owner

    return tuple(sorted(options, key=key, reverse=True))


def _outlook(input: POVStrategyInput) -> RhythmOutlook:
    pressures = tuple(item.value for item in input.unclaimed_consequences[:4]) or (input.arc_state.current_pressure,)
    functions = ("integrate", "externalize", "counteract")
    return RhythmOutlook(3, pressures, functions, ("每章状态物化后重新计算，不冻结未来POV",))
