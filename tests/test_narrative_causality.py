from dataclasses import replace

from creative_os.domains.narrative_causality import (
    CAUSAL_FIELD_PATHS_V1,
    CausalDependencyAnalyzer,
)
from creative_os.domains.narrative_decision import (
    ArcPhase,
    CandidateImpact,
    CandidateValueState,
    NarrativeDecision,
    OptionalCandidateResolution,
)
from tests.test_narrative_decision import _profile, _v2_decision


EXPECTED_CAUSAL_FIELD_PATHS = (
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


def _analyze(candidate: NarrativeDecision):
    return CausalDependencyAnalyzer().analyze(
        candidate,
        _profile(),
        fact_snapshots=(),
        previous_chapter=None,
        change_requests=(),
    )


def _candidate(
    *,
    impact: CandidateImpact,
    value_state: CandidateValueState,
    proposed_value: str | None,
    decided_by: str = "rule",
    decision_ref: str = "causal-rules-v1",
) -> OptionalCandidateResolution:
    return OptionalCandidateResolution(
        candidate_id="candidate-scene-transition",
        kind="scene_transition",
        value_state=value_state,
        proposed_value=proposed_value,
        dependency_inputs=("chapter_contract.pressure_curve.end",),
        affects_current_chapter=impact,
        rationale="结尾直接落入权限审查。",
        decided_by=decided_by,
        decision_ref=decision_ref,
    )


def test_causal_field_paths_cover_outer_arc_pressure_and_all_stable_array_paths():
    assert CAUSAL_FIELD_PATHS_V1 == EXPECTED_CAUSAL_FIELD_PATHS


def test_yes_known_direct_candidate_must_be_present_in_a_formal_causal_field():
    decision = _v2_decision()
    resolution = _candidate(
        impact=CandidateImpact.YES,
        value_state=CandidateValueState.KNOWN,
        proposed_value=decision.chapter_contract.pressure_curve.end,
    )
    candidate = replace(
        decision,
        chapter_contract=replace(decision.chapter_contract, optional_candidates=(resolution,)),
    )

    result = _analyze(candidate)

    assert result.issues == ()
    assert result.resolutions == (resolution,)
    assert result.ruleset_version == "causal-rules-v1"


def test_yes_candidate_is_blocked_when_known_value_is_not_in_formal_field():
    decision = _v2_decision()
    resolution = _candidate(
        impact=CandidateImpact.YES,
        value_state=CandidateValueState.KNOWN,
        proposed_value="未进入合同字段的转场",
    )
    candidate = replace(
        decision,
        chapter_contract=replace(decision.chapter_contract, optional_candidates=(resolution,)),
    )

    result = _analyze(candidate)

    assert result.issues[0].code == "unresolved_causal_candidate"
    assert result.issues[0].blocking is True


def test_no_candidate_requires_a_rule_or_human_decision_record():
    decision = _v2_decision()
    rule_resolution = _candidate(
        impact=CandidateImpact.NO,
        value_state=CandidateValueState.UNKNOWN,
        proposed_value=None,
    )
    human_resolution = replace(rule_resolution, decided_by="human", decision_ref="approval-2026-08-20")

    assert _analyze(replace(decision, chapter_contract=replace(decision.chapter_contract, optional_candidates=(rule_resolution,)))).issues == ()
    assert _analyze(replace(decision, chapter_contract=replace(decision.chapter_contract, optional_candidates=(human_resolution,)))).issues == ()


def test_undetermined_candidate_fails_closed_even_when_its_value_is_known():
    decision = _v2_decision()
    unresolved = _candidate(
        impact=CandidateImpact.UNDETERMINED,
        value_state=CandidateValueState.KNOWN,
        proposed_value=decision.chapter_contract.pressure_curve.end,
    )

    result = _analyze(replace(decision, chapter_contract=replace(decision.chapter_contract, optional_candidates=(unresolved,))))

    assert result.issues[0].code == "unresolved_causal_candidate"
    assert result.issues[0].field_path == "chapter_contract.optional_candidates[candidate-scene-transition]"


def test_analysis_exception_becomes_task_one_blocking_issue():
    result = CausalDependencyAnalyzer().analyze(
        object(),
        _profile(),
        fact_snapshots=(),
        previous_chapter=None,
        change_requests=(),
    )

    assert result.issues[0].code == "causal_analysis_failed"
    assert result.issues[0].blocking is True


def test_outer_arc_and_pressure_changes_remain_in_the_causal_closure():
    decision = _v2_decision()
    candidate = replace(
        decision,
        arc_phase=ArcPhase.TURN,
        arc_goal="将权限审查推入不可逆转折",
        inherited_pressure="旧权限已被收回",
        future_pressures=("听证会将在下一章公开",),
    )

    result = _analyze(candidate)

    assert result.field_paths == CAUSAL_FIELD_PATHS_V1
    assert set(("arc_phase", "arc_goal", "inherited_pressure", "future_pressures[*]")).issubset(result.field_paths)
