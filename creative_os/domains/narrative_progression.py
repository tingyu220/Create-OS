from __future__ import annotations

from dataclasses import dataclass

from creative_os.domains.narrative_decision import ArcPhase, NarrativeDecision
from creative_os.domains.narrative_semantics import (
    FunctionSemanticNormalizer, SemanticComparison, SemanticRelation,
)


PHASE_ORDER = {
    ArcPhase.SETUP: 0,
    ArcPhase.ESCALATION: 1,
    ArcPhase.TURN: 2,
    ArcPhase.AFTERMATH: 3,
    ArcPhase.CLOSURE: 4,
}


@dataclass(frozen=True, slots=True)
class ProgressionIssue:
    code: str
    severity: str
    evidence: str


@dataclass(frozen=True, slots=True)
class NarrativeProgression:
    chapter: int
    volume_id: str
    arc_id: str
    phase: ArcPhase
    phase_changed: bool
    functions: tuple[str, ...]
    protagonist_action: str
    pressure_curve: tuple[str, str, str]
    reader_change: tuple[str, str]
    foreshadow_actions: tuple[str, ...]
    semantic_comparisons: tuple[SemanticComparison, ...]
    issues: tuple[ProgressionIssue, ...]


def evaluate_progression(
    current: NarrativeDecision,
    recent_contracts: list[NarrativeDecision],
) -> NarrativeProgression:
    prior = [
        item for item in recent_contracts
        if item.volume_id == current.volume_id and item.arc_id == current.arc_id and item.chapter < current.chapter
    ]
    previous = max(prior, key=lambda item: item.chapter, default=None)
    issues: list[ProgressionIssue] = []
    contract = current.chapter_contract
    phase_changed = previous is not None and previous.arc_phase != current.arc_phase
    semantic_comparisons: list[SemanticComparison] = []

    if previous is not None:
        if PHASE_ORDER[current.arc_phase] < PHASE_ORDER[previous.arc_phase]:
            issues.append(ProgressionIssue(
                "arc_phase_regression", "high",
                f"第{previous.chapter}章 {previous.arc_phase.value} -> 第{current.chapter}章 {current.arc_phase.value}",
            ))
        previous_choice = previous.chapter_contract.protagonist_choice
        choice = contract.protagonist_choice
        if choice.action == previous_choice.action and choice.consequence == previous_choice.consequence:
            issues.append(ProgressionIssue(
                "repeated_protagonist_choice", "medium",
                f"第{previous.chapter}章与第{current.chapter}章均为：{choice.action}",
            ))
        previous_pressure = previous.chapter_contract.pressure_curve
        pressure = contract.pressure_curve
        if (pressure.start, pressure.turn, pressure.end) == (
            previous_pressure.start, previous_pressure.turn, previous_pressure.end,
        ):
            issues.append(ProgressionIssue(
                "flat_pressure_curve", "medium",
                f"第{current.chapter}章与第{previous.chapter}章压力曲线完全相同",
            ))
        overlap = set(contract.functions) & set(previous.chapter_contract.functions)
        if overlap and contract.ending_shift == previous.chapter_contract.ending_shift and not phase_changed:
            issues.append(ProgressionIssue(
                "stalled_story_progression", "medium",
                f"功能={','.join(sorted(overlap))}; 结尾失衡未改变",
            ))
        normalizer = FunctionSemanticNormalizer()
        for current_function in contract.functions:
            current_key = normalizer.normalize(
                current_function, before_state=contract.reader_change.before,
                after_state=contract.reader_change.after, arc_phase=current.arc_phase.value,
                ending_shift=contract.ending_shift,
            )
            for previous_function in previous.chapter_contract.functions:
                previous_key = normalizer.normalize(
                    previous_function,
                    before_state=previous.chapter_contract.reader_change.before,
                    after_state=previous.chapter_contract.reader_change.after,
                    arc_phase=previous.arc_phase.value,
                    ending_shift=previous.chapter_contract.ending_shift,
                )
                comparison = normalizer.compare(current_key, previous_key)
                semantic_comparisons.append(comparison)
                if comparison.relation is SemanticRelation.REPEATED:
                    issues.append(ProgressionIssue(
                        "repeated_chapter_function", "high", "; ".join(comparison.evidence),
                    ))
                elif comparison.relation is SemanticRelation.UNCERTAIN:
                    issues.append(ProgressionIssue(
                        "uncertain_function_similarity", "high", "; ".join(comparison.evidence),
                    ))

    recent_actions = {
        action
        for item in prior[-2:]
        for action in item.chapter_contract.foreshadow_actions
    }
    repeated_hooks = tuple(action for action in contract.foreshadow_actions if action in recent_actions)
    if repeated_hooks:
        issues.append(ProgressionIssue(
            "stagnant_foreshadow_action", "low", "; ".join(repeated_hooks),
        ))

    return NarrativeProgression(
        chapter=current.chapter,
        volume_id=current.volume_id,
        arc_id=current.arc_id,
        phase=current.arc_phase,
        phase_changed=phase_changed,
        functions=contract.functions,
        protagonist_action=contract.protagonist_choice.action,
        pressure_curve=(
            contract.pressure_curve.start,
            contract.pressure_curve.turn,
            contract.pressure_curve.end,
        ),
        reader_change=(contract.reader_change.before, contract.reader_change.after),
        foreshadow_actions=contract.foreshadow_actions,
        semantic_comparisons=tuple(semantic_comparisons),
        issues=tuple(issues),
    )
