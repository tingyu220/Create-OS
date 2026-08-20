from dataclasses import replace

import pytest

from creative_os.domains.contract_issue import ContractIssue, EvidenceCheck
from creative_os.domains.contract_preflight import ContractPreflightValidator
from creative_os.domains.narrative_causality import CausalAnalysisResult, CausalDependencyAnalyzer
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import (
    ArcPhase,
    CandidateImpact,
    CandidateValueState,
    ChapterContract,
    ChoiceStatus,
    FieldEvidenceBinding,
    InformationPlan,
    NarrativeDecision,
    NullablePlan,
    OptionalCandidateResolution,
    PressureCurve,
    ProtagonistChoice,
    ReaderChange,
)
from creative_os.domains.narrative_evidence import (
    EvidenceAssertion,
    EvidenceIntegrityValidator,
    EvidenceLocator,
    EvidenceRef,
    EvidenceRole,
    EvidenceSourceKind,
    ResolvedEvidenceSource,
)
from tests.test_narrative_decision import _profile


INTENT_VALUES = {
    "arc_phase": "escalation",
    "arc_goal": "将短信疑点转化为主动调查",
    "inherited_pressure": "主角可能是投递工具",
    "future_pressures[0]": "第九区权限将被收紧",
    "chapter_contract.functions[0]": "推进主线",
    "chapter_contract.functions[1]": "改变人物关系",
    "chapter_contract.dramatic_question": "主角是否追查短信？",
    "chapter_contract.protagonist_choice.status": "complete",
    "chapter_contract.protagonist_choice.actor": "林子轩",
    "chapter_contract.protagonist_choice.action": "查看日志",
    "chapter_contract.protagonist_choice.alternatives[0]": "继续等待",
    "chapter_contract.protagonist_choice.cost": "失去父亲信任",
    "chapter_contract.protagonist_choice.consequence": "进入审查名单",
    "chapter_contract.reader_change.before": "怀疑内部泄露",
    "chapter_contract.reader_change.after": "确认主角也在链路中",
    "chapter_contract.information.reveal[0]": "日志被覆盖",
    "chapter_contract.information.withhold[0]": "覆盖者身份",
    "chapter_contract.information.misdirect.values[0]": "嫌疑指向周远",
    "chapter_contract.pressure_curve.start": "封控",
    "chapter_contract.pressure_curve.turn": "违令",
    "chapter_contract.pressure_curve.end": "启动审查",
    "chapter_contract.foreshadow_actions.values[0]": "加深钥匙线索",
    "chapter_contract.ending_shift": "主角成为审查对象",
    "chapter_contract.forbidden.values[0]": "不得确认发送者",
}

AUTHORITATIVE_VALUES = {
    "arc_phase": "escalation",
    "arc_goal": "将短信疑点转化为主动调查",
    "inherited_pressure": "主角可能是投递工具",
    "future_pressures[0]": "第九区权限将被收紧",
    "chapter_contract.functions[0]": "推进主线",
    "chapter_contract.functions[1]": "改变人物关系",
    "chapter_contract.dramatic_question": "主角是否追查短信？",
    "chapter_contract.protagonist_choice.status": "complete",
    "chapter_contract.protagonist_choice.actor": "林子轩",
    "chapter_contract.protagonist_choice.action": "查看日志",
    "chapter_contract.protagonist_choice.alternatives[0]": "继续等待",
    "chapter_contract.protagonist_choice.cost": "失去父亲信任",
    "chapter_contract.protagonist_choice.consequence": "进入审查名单",
    "chapter_contract.reader_change.before": "怀疑内部泄露",
    "chapter_contract.reader_change.after": "确认主角也在链路中",
    "chapter_contract.information.reveal[0]": "日志被覆盖",
    "chapter_contract.information.withhold[0]": "覆盖者身份",
    "chapter_contract.information.misdirect.values[0]": "嫌疑指向周远",
    "chapter_contract.pressure_curve.start": "封控",
    "chapter_contract.pressure_curve.turn": "违令",
    "chapter_contract.pressure_curve.end": "启动审查",
    "chapter_contract.foreshadow_actions.values[0]": "加深钥匙线索",
    "chapter_contract.ending_shift": "主角成为审查对象",
    "chapter_contract.forbidden.values[0]": "不得确认发送者",
}


def _ref(field_path: str, value: str, *, source_id: str = "director/chapter-007", role=EvidenceRole.INTENT):
    return EvidenceRef(
        evidence_id=f"ev-{source_id}-{field_path}",
        contract_id="narrative-chapter-007",
        contract_version=2,
        field_path=field_path,
        role=role,
        source_id=source_id,
        source_version="v1",
        source_content_hash="a" * 64,
        locator=EvidenceLocator(kind="record_id", value=field_path),
        excerpt=value,
        assertion=f"权威来源约束 {field_path}",
        asserted_value=value,
    )


def _source(
    values: dict[str, str],
    *,
    source_id: str = "director/chapter-007",
    source_kind: EvidenceSourceKind = EvidenceSourceKind.DIRECTOR,
    source_content_hash: str = "a" * 64,
):
    return ResolvedEvidenceSource(
        source_id=source_id,
        source_version="v1",
        source_content_hash=source_content_hash,
        source_kind=source_kind,
        located_excerpts=tuple(
            (EvidenceLocator(kind="record_id", value=path), value)
            for path, value in values.items()
        ),
        assertions_by_field_path=tuple(
            (path, (f"权威来源约束 {path}", "Task 明确要求本章推进主线"))
            for path in values
        ),
        asserted_values=tuple(EvidenceAssertion(path, value) for path, value in values.items()),
    )


def _resolver(*sources: ResolvedEvidenceSource):
    by_id = {source.source_id: source for source in sources}
    return by_id.get


def _candidate(*, bindings: tuple[FieldEvidenceBinding, ...] | None = None) -> NarrativeDecision:
    refs = tuple(_ref(path, value) for path, value in INTENT_VALUES.items())
    return NarrativeDecision(
        contract_id="narrative-chapter-007",
        contract_version=2,
        chapter=7,
        profile_id="civilization-profile",
        volume_id="volume-1",
        arc_id="arc-identity",
        arc_phase=ArcPhase.ESCALATION,
        arc_goal=INTENT_VALUES["arc_goal"],
        inherited_pressure=INTENT_VALUES["inherited_pressure"],
        future_pressures=(INTENT_VALUES["future_pressures[0]"],),
        chapter_contract=ChapterContract(
            chapter_id="chapter_007",
            functions=(
                INTENT_VALUES["chapter_contract.functions[0]"],
                INTENT_VALUES["chapter_contract.functions[1]"],
            ),
            dramatic_question=INTENT_VALUES["chapter_contract.dramatic_question"],
            protagonist_choice=ProtagonistChoice(
                actor=INTENT_VALUES["chapter_contract.protagonist_choice.actor"],
                action=INTENT_VALUES["chapter_contract.protagonist_choice.action"],
                alternatives=(INTENT_VALUES["chapter_contract.protagonist_choice.alternatives[0]"],),
                cost=INTENT_VALUES["chapter_contract.protagonist_choice.cost"],
                consequence=INTENT_VALUES["chapter_contract.protagonist_choice.consequence"],
            ),
            reader_change=ReaderChange(
                before=INTENT_VALUES["chapter_contract.reader_change.before"],
                after=INTENT_VALUES["chapter_contract.reader_change.after"],
            ),
            information=InformationPlan(
                reveal=(INTENT_VALUES["chapter_contract.information.reveal[0]"],),
                withhold=(INTENT_VALUES["chapter_contract.information.withhold[0]"],),
                misdirect=NullablePlan(
                    values=(INTENT_VALUES["chapter_contract.information.misdirect.values[0]"],)
                ),
            ),
            pressure_curve=PressureCurve(
                start=INTENT_VALUES["chapter_contract.pressure_curve.start"],
                turn=INTENT_VALUES["chapter_contract.pressure_curve.turn"],
                end=INTENT_VALUES["chapter_contract.pressure_curve.end"],
            ),
            foreshadow_actions=NullablePlan(
                values=(INTENT_VALUES["chapter_contract.foreshadow_actions.values[0]"],)
            ),
            ending_shift=INTENT_VALUES["chapter_contract.ending_shift"],
            target_chinese_chars=7000,
            forbidden=NullablePlan(values=(INTENT_VALUES["chapter_contract.forbidden.values[0]"],)),
            intent_evidence_bindings=bindings
            if bindings is not None
            else tuple(FieldEvidenceBinding(ref.field_path, (ref,)) for ref in refs),
        ),
    )


def _causal(candidate: NarrativeDecision) -> CausalAnalysisResult:
    return CausalDependencyAnalyzer().analyze(candidate, _profile(), (), None, ())


def _validate(candidate: NarrativeDecision, sources=None, causal_result=None):
    return ContractPreflightValidator().validate(
        candidate,
        _resolver(_source(AUTHORITATIVE_VALUES)) if sources is None else sources,
        _causal(candidate) if causal_result is None else causal_result,
    )


def _remove_binding(candidate: NarrativeDecision, field_path: str) -> NarrativeDecision:
    return replace(
        candidate,
        chapter_contract=replace(
            candidate.chapter_contract,
            intent_evidence_bindings=tuple(
                binding
                for binding in candidate.chapter_contract.intent_evidence_bindings
                if binding.field_path != field_path
            ),
        ),
    )


def test_complete_candidate_with_exact_field_evidence_and_resolved_causality_passes():
    result = _validate(_candidate())

    assert result.issues == ()
    assert result.is_ready is True


@pytest.mark.parametrize("field_path", tuple(INTENT_VALUES))
def test_every_scalar_and_array_element_requires_its_exact_intent_binding(field_path):
    candidate = _candidate()
    candidate = _remove_binding(candidate, field_path)

    result = _validate(candidate)

    assert any(
        issue.code == "incomplete_contract" and issue.field_path == field_path
        for issue in result.issues
    )


@pytest.mark.parametrize(
    "field_path",
    (
        "arc_goal",
        "inherited_pressure",
        "future_pressures[0]",
        "chapter_contract.functions[0]",
        "chapter_contract.dramatic_question",
        "chapter_contract.protagonist_choice.actor",
        "chapter_contract.protagonist_choice.action",
        "chapter_contract.protagonist_choice.alternatives[0]",
        "chapter_contract.protagonist_choice.cost",
        "chapter_contract.protagonist_choice.consequence",
        "chapter_contract.reader_change.before",
        "chapter_contract.reader_change.after",
        "chapter_contract.information.reveal[0]",
        "chapter_contract.information.withhold[0]",
        "chapter_contract.information.misdirect.values[0]",
        "chapter_contract.pressure_curve.start",
        "chapter_contract.pressure_curve.turn",
        "chapter_contract.pressure_curve.end",
        "chapter_contract.foreshadow_actions.values[0]",
        "chapter_contract.ending_shift",
        "chapter_contract.forbidden.values[0]",
    ),
)
def test_unknown_value_reports_the_exact_concrete_candidate_path(field_path):
    candidate = _candidate()
    current = candidate
    segments = field_path.split(".")
    for segment in segments[:-1]:
        current = getattr(current, segment)
    leaf = segments[-1]
    if "[0]" in leaf:
        object.__setattr__(current, leaf[:-3], ("",) + getattr(current, leaf[:-3])[1:])
    else:
        object.__setattr__(current, leaf, "")

    result = _validate(candidate)

    assert any(
        issue.code == "incomplete_contract" and issue.field_path == field_path
        for issue in result.issues
    )


def test_unknown_arc_phase_reports_its_exact_control_path():
    candidate = _candidate()
    object.__setattr__(candidate, "arc_phase", "unknown")

    result = _validate(candidate)

    assert any(
        issue.code == "incomplete_contract" and issue.field_path == "arc_phase"
        for issue in result.issues
    )


@pytest.mark.parametrize(
    ("plan_path", "binding_path"),
    (
        ("information.misdirect", "chapter_contract.information.misdirect.not_applicable_reason"),
        ("foreshadow_actions", "chapter_contract.foreshadow_actions.not_applicable_reason"),
        ("forbidden", "chapter_contract.forbidden.not_applicable_reason"),
    ),
)
def test_empty_nullable_array_requires_reason_and_non_applicability_evidence(plan_path, binding_path):
    candidate = _candidate()
    parent = candidate.chapter_contract
    if "." in plan_path:
        parent = parent.information
        attribute = "misdirect"
    else:
        attribute = plan_path
    object.__setattr__(parent, attribute, NullablePlan(values=()))

    result = _validate(candidate)

    assert any(
        issue.code == "invalid_not_applicable_reason" and issue.field_path == binding_path
        for issue in result.issues
    )


def test_empty_nullable_array_accepts_reason_with_valid_non_applicability_evidence():
    candidate = _candidate()
    path = "chapter_contract.foreshadow_actions.not_applicable_reason"
    reason = "本章没有适用的既有伏笔"
    ref = _ref(path, reason, role=EvidenceRole.NON_APPLICABILITY)
    bindings = tuple(
        binding
        for binding in candidate.chapter_contract.intent_evidence_bindings
        if binding.field_path != "chapter_contract.foreshadow_actions.values[0]"
    ) + (FieldEvidenceBinding(path, (ref,)),)
    candidate = replace(
        candidate,
        chapter_contract=replace(
            candidate.chapter_contract,
            foreshadow_actions=NullablePlan(values=(), not_applicable_reason=reason),
            intent_evidence_bindings=bindings,
        ),
    )

    authoritative_values = dict(AUTHORITATIVE_VALUES)
    authoritative_values.pop("chapter_contract.foreshadow_actions.values[0]")
    authoritative_values[path] = reason
    result = _validate(candidate, sources=_resolver(_source(authoritative_values)))

    assert result.issues == ()


def test_nonempty_nullable_array_rejects_not_applicable_reason_and_reason_evidence():
    candidate = _candidate()
    path = "chapter_contract.foreshadow_actions.not_applicable_reason"
    reason = "错误地标记不适用"
    ref = _ref(path, reason, role=EvidenceRole.NON_APPLICABILITY)
    object.__setattr__(candidate.chapter_contract.foreshadow_actions, "not_applicable_reason", reason)
    object.__setattr__(
        candidate.chapter_contract,
        "intent_evidence_bindings",
        candidate.chapter_contract.intent_evidence_bindings + (FieldEvidenceBinding(path, (ref,)),),
    )

    result = _validate(candidate)

    assert any(
        issue.code == "invalid_not_applicable_reason" and issue.field_path == path
        for issue in result.issues
    )


def test_same_task_and_director_intent_value_is_accepted_but_conflict_is_blocking():
    path = "chapter_contract.functions[0]"
    candidate = _candidate()
    director_binding = next(
        binding for binding in candidate.chapter_contract.intent_evidence_bindings if binding.field_path == path
    )
    same = replace(
        _ref(path, INTENT_VALUES[path], source_id="task/chapter-007"),
        assertion="Task 明确要求本章推进主线",
    )
    candidate_same = replace(
        candidate,
        chapter_contract=replace(
            candidate.chapter_contract,
            intent_evidence_bindings=tuple(
                replace(binding, evidence=binding.evidence + (same,))
                if binding.field_path == path
                else binding
                for binding in candidate.chapter_contract.intent_evidence_bindings
            ),
        ),
    )
    same_sources = _resolver(
        _source(AUTHORITATIVE_VALUES),
        _source(
            {path: INTENT_VALUES[path]},
            source_id="task/chapter-007",
            source_kind=EvidenceSourceKind.TASK,
        ),
    )
    assert _validate(candidate_same, sources=same_sources).issues == ()

    conflict = replace(same, excerpt=INTENT_VALUES[path], asserted_value=INTENT_VALUES[path])
    candidate_conflict = replace(
        candidate_same,
        chapter_contract=replace(
            candidate_same.chapter_contract,
            intent_evidence_bindings=tuple(
                replace(binding, evidence=director_binding.evidence + (conflict,))
                if binding.field_path == path
                else binding
                for binding in candidate_same.chapter_contract.intent_evidence_bindings
            ),
        ),
    )

    conflict_sources = _resolver(
        _source(AUTHORITATIVE_VALUES),
        _source(
            {path: "改为只推进支线"},
            source_id="task/chapter-007",
            source_kind=EvidenceSourceKind.TASK,
        ),
    )
    result = _validate(candidate_conflict, sources=conflict_sources)

    assert any(
        issue.code == "conflicting_intent_evidence" and issue.field_path == path and issue.blocking
        for issue in result.issues
    )


def test_director_and_profile_value_difference_does_not_use_task_director_conflict_code():
    path = "chapter_contract.functions[0]"
    candidate = _candidate()
    profile_ref = _ref(path, INTENT_VALUES[path], source_id="profile/chapter-007")
    candidate = replace(
        candidate,
        chapter_contract=replace(
            candidate.chapter_contract,
            intent_evidence_bindings=tuple(
                replace(binding, evidence=binding.evidence + (profile_ref,))
                if binding.field_path == path
                else binding
                for binding in candidate.chapter_contract.intent_evidence_bindings
            ),
        ),
    )
    resolver = _resolver(
        _source(AUTHORITATIVE_VALUES),
        _source(
            {path: "Profile 中的不同约束值"},
            source_id="profile/chapter-007",
            source_kind=EvidenceSourceKind.PROFILE,
        ),
    )

    result = _validate(candidate, sources=resolver)

    assert any(issue.code == "evidence_excerpt_mismatch" for issue in result.issues)
    assert not any(issue.code == "conflicting_intent_evidence" for issue in result.issues)


def test_multiple_intent_evidence_from_one_director_source_does_not_conflict():
    path = "chapter_contract.functions[0]"
    candidate = _candidate()
    duplicate = replace(
        next(
            binding.evidence[0]
            for binding in candidate.chapter_contract.intent_evidence_bindings
            if binding.field_path == path
        ),
        evidence_id="ev-director-second-proof",
        assertion="Task 明确要求本章推进主线",
    )
    candidate = replace(
        candidate,
        chapter_contract=replace(
            candidate.chapter_contract,
            intent_evidence_bindings=tuple(
                replace(binding, evidence=binding.evidence + (duplicate,))
                if binding.field_path == path
                else binding
                for binding in candidate.chapter_contract.intent_evidence_bindings
            ),
        ),
    )

    result = _validate(candidate)

    assert result.issues == ()


def test_intent_path_rejects_an_extra_non_applicability_role_even_when_intent_exists():
    path = "chapter_contract.functions[0]"
    candidate = _candidate()
    wrong_role = _ref(path, INTENT_VALUES[path], source_id="task/chapter-007", role=EvidenceRole.NON_APPLICABILITY)
    candidate = replace(
        candidate,
        chapter_contract=replace(
            candidate.chapter_contract,
            intent_evidence_bindings=tuple(
                replace(binding, evidence=binding.evidence + (wrong_role,))
                if binding.field_path == path
                else binding
                for binding in candidate.chapter_contract.intent_evidence_bindings
            ),
        ),
    )

    result = _validate(candidate)

    assert any(
        issue.code == "incomplete_contract" and issue.field_path == path and issue.blocking
        for issue in result.issues
    )


@pytest.mark.parametrize("status", (ChoiceStatus.PARTIAL, ChoiceStatus.UNKNOWN))
def test_partial_or_unknown_choice_blocks_at_status_and_each_stable_missing_field_index(status):
    candidate = _candidate()
    missing = ("alternatives", "cost") if status == ChoiceStatus.PARTIAL else (
        "actor",
        "action",
        "alternatives",
        "cost",
        "consequence",
    )
    choice = ProtagonistChoice(
        actor="林子轩" if status == ChoiceStatus.PARTIAL else None,
        action="查看日志" if status == ChoiceStatus.PARTIAL else None,
        alternatives=(),
        cost=None,
        consequence="进入审查名单" if status == ChoiceStatus.PARTIAL else None,
        status=status,
        missing_fields=missing,
    )
    candidate = replace(
        candidate,
        chapter_contract=replace(candidate.chapter_contract, protagonist_choice=choice),
    )

    result = _validate(candidate)

    issue_paths = {issue.field_path for issue in result.issues if issue.code == "incomplete_contract"}
    assert "chapter_contract.protagonist_choice.status" in issue_paths
    assert {
        f"chapter_contract.protagonist_choice.missing_fields[{index}]"
        for index in range(len(missing))
    } <= issue_paths


def test_causal_undetermined_and_analysis_failure_are_blocking_and_aggregated_with_field_issues():
    candidate = _remove_binding(_candidate(), "arc_goal")
    causal_issue = ContractIssue(
        code="unresolved_causal_candidate",
        severity="error",
        blocking=True,
        field_path="chapter_contract.optional_candidates[candidate-x]",
        evidence_checks=(EvidenceCheck("unresolved_causal_candidate", False, "待裁决"),),
        repair_hint="完成裁决",
    )
    causal_result = CausalAnalysisResult(
        resolutions=(),
        issues=(causal_issue,),
        candidate_content_hash=NarrativeDecisionCodec.content_hash(candidate),
    )

    result = _validate(candidate, causal_result=causal_result)

    assert {issue.code for issue in result.issues} >= {
        "incomplete_contract",
        "unresolved_causal_candidate",
    }

    failed = _validate(candidate, causal_result=object())
    assert any(issue.code == "causal_analysis_failed" and issue.blocking for issue in failed.issues)


def test_forged_issue_free_undetermined_causal_result_still_fails_closed():
    candidate = _candidate()
    resolution = OptionalCandidateResolution(
        candidate_id="candidate-undetermined",
        kind="scene_transition",
        value_state=CandidateValueState.UNKNOWN,
        proposed_value=None,
        dependency_inputs=("chapter_contract.pressure_curve.end",),
        affects_current_chapter=CandidateImpact.UNDETERMINED,
        rationale="尚未获得裁决",
        decided_by="rule",
        decision_ref="causal-rules-v1",
    )
    candidate = replace(
        candidate,
        chapter_contract=replace(candidate.chapter_contract, optional_candidates=(resolution,)),
    )
    forged = CausalAnalysisResult(
        resolutions=(resolution,),
        issues=(),
        candidate_content_hash=NarrativeDecisionCodec.content_hash(candidate),
    )

    result = _validate(candidate, causal_result=forged)

    assert any(
        issue.code == "unresolved_causal_candidate"
        and issue.field_path == "chapter_contract.optional_candidates[candidate-undetermined]"
        and issue.blocking
        for issue in result.issues
    )


def test_preflight_preserves_task3_exact_invalid_causal_candidate_issue_before_hash_failure():
    candidate = _candidate()
    invalid_resolution = OptionalCandidateResolution(
        candidate_id="candidate-invalid-rationale",
        kind="scene_transition",
        value_state=CandidateValueState.UNKNOWN,
        proposed_value=None,
        dependency_inputs=("chapter_contract.pressure_curve.end",),
        affects_current_chapter=CandidateImpact.NO,
        rationale="有效理由",
        decided_by="human",
        decision_ref="human-ruling-1",
    )
    object.__setattr__(invalid_resolution, "rationale", "")
    candidate = replace(
        candidate,
        chapter_contract=replace(candidate.chapter_contract, optional_candidates=(invalid_resolution,)),
    )
    causal_result = _causal(candidate)

    result = _validate(candidate, causal_result=causal_result)

    assert any(
        issue.code == "invalid_causal_candidate"
        and issue.field_path == "chapter_contract.optional_candidates[candidate-invalid-rationale]"
        and issue.blocking
        for issue in result.issues
    )


def test_evidence_integrity_failures_are_preserved_at_the_exact_field_path():
    candidate = _candidate()
    source = _source(AUTHORITATIVE_VALUES, source_content_hash="b" * 64)

    result = _validate(candidate, sources=_resolver(source))

    assert any(
        issue.code == "evidence_hash_mismatch"
        and issue.field_path == "chapter_contract.functions[0]"
        for issue in result.issues
    )


def test_public_sources_boundary_rejects_tuple_and_prebuilt_validator_shortcuts():
    candidate = _candidate()

    tuple_result = _validate(candidate, sources=(_source(AUTHORITATIVE_VALUES),))
    validator_result = _validate(
        candidate,
        sources=EvidenceIntegrityValidator(_resolver(_source(AUTHORITATIVE_VALUES))),
    )

    assert any(issue.code == "evidence_source_unavailable" for issue in tuple_result.issues)
    assert any(issue.code == "evidence_source_unavailable" for issue in validator_result.issues)


def test_preflight_rejects_stale_candidate_hash_wrong_ruleset_and_forged_yes_result():
    candidate = _candidate()
    valid_result = _causal(candidate)
    stale_candidate = replace(candidate, arc_goal="改变后的剧情段目标")

    stale = _validate(stale_candidate, causal_result=valid_result)
    wrong_ruleset = _validate(
        candidate,
        causal_result=replace(valid_result, ruleset_version="causal-rules-v2"),
    )

    resolution = OptionalCandidateResolution(
        candidate_id="candidate-forged-yes",
        kind="scene_transition",
        value_state=CandidateValueState.KNOWN,
        proposed_value="未纳入正式字段的值",
        dependency_inputs=("chapter_contract.pressure_curve.end",),
        affects_current_chapter=CandidateImpact.YES,
        rationale="伪造无 issue 结果",
        decided_by="rule",
        decision_ref="causal-rules-v1",
    )
    forged_candidate = replace(
        candidate,
        chapter_contract=replace(candidate.chapter_contract, optional_candidates=(resolution,)),
    )
    forged_result = CausalAnalysisResult(
        resolutions=(resolution,),
        issues=(),
        candidate_content_hash=NarrativeDecisionCodec.content_hash(forged_candidate),
    )
    forged = _validate(forged_candidate, causal_result=forged_result)

    assert any(issue.code == "causal_analysis_failed" for issue in stale.issues)
    assert any(issue.code == "causal_analysis_failed" for issue in wrong_ruleset.issues)
    assert any(issue.code == "unresolved_causal_candidate" for issue in forged.issues)


def test_candidate_value_cannot_be_satisfied_by_self_asserted_ref_or_forged_excerpt():
    path = "chapter_contract.functions[0]"
    candidate = _candidate()
    binding = next(
        binding for binding in candidate.chapter_contract.intent_evidence_bindings if binding.field_path == path
    )
    forged = replace(binding.evidence[0], excerpt="推进主线", asserted_value="推进主线")
    candidate = replace(
        candidate,
        chapter_contract=replace(
            candidate.chapter_contract,
            intent_evidence_bindings=tuple(
                replace(item, evidence=(forged,)) if item.field_path == path else item
                for item in candidate.chapter_contract.intent_evidence_bindings
            ),
        ),
    )
    source = _source({**AUTHORITATIVE_VALUES, path: "改变人物关系"})

    result = _validate(candidate, sources=_resolver(source))

    codes = {issue.code for issue in result.issues if issue.field_path == path}
    assert "evidence_excerpt_mismatch" in codes or "evidence_asserted_value_mismatch" in codes


def test_internal_exceptions_become_blocking_contract_issues_without_fail_open():
    result = ContractPreflightValidator().validate(object(), lambda source_id: None, object())

    assert result.is_ready is False
    assert result.issues
    assert all(issue.blocking for issue in result.issues)
