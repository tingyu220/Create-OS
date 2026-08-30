from dataclasses import replace

import pytest

from creative_os.domains.contract_approval import ContractApprovalPolicy
from creative_os.domains.contract_revision import ContractRevisionRequest, RevisionValidationError
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import (
    ArcPhase, FieldEvidenceBinding, NarrativeChangeRequest, NarrativeChangeStatus,
    WrittenTextStrategy,
)
from tests.test_contract_preflight import _candidate


def _approved_change(old_plan="旧计划", new_plan="新计划", chapter: int = 7) -> NarrativeChangeRequest:
    return NarrativeChangeRequest(
        id="change-007", reason="人工批准调整", old_plan=old_plan, new_plan=new_plan,
        affected_chapters=(chapter,), affected_state_subjects=("主角",), affected_hooks=("hook-1",),
        written_text_strategy=WrittenTextStrategy.LOCAL_REVISION,
        status=NarrativeChangeStatus.APPROVED,
    )


def _replacement(current, **changes):
    version = current.contract_version + 1
    provisional = replace(current, contract_version=version, **changes)
    bindings = []
    for binding in current.chapter_contract.intent_evidence_bindings:
        try:
            expected = provisional
            for segment in binding.field_path.split("."):
                if "[" in segment:
                    name, index = segment[:-1].split("[")
                    expected = getattr(expected, name)[int(index)]
                else:
                    expected = getattr(expected, segment)
            expected = expected.value if hasattr(expected, "value") else expected
        except (AttributeError, IndexError):
            continue
        bindings.append(FieldEvidenceBinding(
            binding.field_path,
            tuple(replace(ref, contract_version=version, asserted_value=expected,
                          excerpt=str(expected))
                  for ref in binding.evidence),
        ))
    chapter_contract = replace(provisional.chapter_contract, intent_evidence_bindings=tuple(bindings))
    return replace(provisional, chapter_contract=chapter_contract)


def test_revision_binds_next_version_base_hash_and_keeps_old_contract_unchanged():
    current = _candidate()
    before = NarrativeDecisionCodec.encode_v2(current)
    replacement = _replacement(current, arc_phase=ArcPhase.TURN)
    request = ContractRevisionRequest.build(
        current, replacement, base_baseline_fingerprint="a" * 64,
        replacement_baseline_fingerprint="a" * 64,
        causal_impact_paths=("arc_phase",), scene_impact="下一场景转折",
        approved_change_requests=(_approved_change("escalation", "turn"),),
    )
    assert request.base_contract_version == current.contract_version
    assert request.replacement_contract_version == current.contract_version + 1
    assert request.base_contract_content_hash == NarrativeDecisionCodec.content_hash(current)
    assert request.changed_field_paths == ("arc_phase",)
    assert NarrativeDecisionCodec.encode_v2(current) == before


def test_canonical_leaf_diff_uses_stable_array_indices_and_exact_values():
    current = _candidate()
    replacement = _replacement(current, future_pressures=(current.future_pressures[0], "新增压力"))
    source = current.chapter_contract.intent_evidence_bindings[0].evidence[0]
    added = FieldEvidenceBinding(
        "future_pressures[1]",
        (replace(source, evidence_id="future-pressure-2", contract_version=replacement.contract_version,
                 field_path="future_pressures[1]", asserted_value="新增压力"),),
    )
    replacement = replace(replacement, chapter_contract=replace(
        replacement.chapter_contract,
        intent_evidence_bindings=(*replacement.chapter_contract.intent_evidence_bindings, added),
    ))
    request = ContractRevisionRequest.build(
        current, replacement, base_baseline_fingerprint="a" * 64,
        replacement_baseline_fingerprint="a" * 64,
        causal_impact_paths=("future_pressures[1]",), scene_impact="压力升级",
        approved_change_requests=(_approved_change("<missing>", "新增压力"),),
    )
    change = request.change("future_pressures[1]")
    assert change.old_value is None
    assert change.new_value == "新增压力"


def test_major_change_requires_approved_change_request_for_the_chapter():
    current = _candidate()
    replacement = _replacement(current, arc_goal="新目标")
    with pytest.raises(RevisionValidationError, match="approved NarrativeChangeRequest"):
        ContractRevisionRequest.build(
            current, replacement, base_baseline_fingerprint="a" * 64,
            replacement_baseline_fingerprint="a" * 64,
            causal_impact_paths=("arc_goal",), scene_impact="目标变化",
            approved_change_requests=(),
        )
    with pytest.raises(RevisionValidationError, match="approved NarrativeChangeRequest"):
        ContractRevisionRequest.build(
            current, replacement, base_baseline_fingerprint="a" * 64,
            replacement_baseline_fingerprint="a" * 64,
            causal_impact_paths=("arc_goal",), scene_impact="目标变化",
            approved_change_requests=(replace(_approved_change(current.arc_goal, "新目标"), status=NarrativeChangeStatus.PROPOSED),),
        )


def test_revision_reapproval_set_always_has_full_and_post_freeze_plus_specialties():
    current = _candidate()
    information = replace(current.chapter_contract.information, reveal=("新揭示",))
    replacement = _replacement(current, chapter_contract=replace(current.chapter_contract, information=information))
    request = ContractRevisionRequest.build(
        current, replacement, base_baseline_fingerprint="a" * 64,
        replacement_baseline_fingerprint="a" * 64,
        causal_impact_paths=("chapter_contract.information.reveal[0]",), scene_impact="信息策略变化",
        approved_change_requests=(_approved_change(current.chapter_contract.information.reveal[0], "新揭示"),),
    )
    assert ContractApprovalPolicy.required_revision_approvals(
        current, replacement, request,
        authority_causal_impact_paths=("chapter_contract.information.reveal[0]",),
        authority_approved_change_requests=(
            _approved_change(current.chapter_contract.information.reveal[0], "新揭示"),
        ),
    ) == (
        "full_contract", "information_reveal_and_misdirect", "post_freeze_revision",
    )


def test_baseline_change_requires_a_new_reviewer_result():
    current = _candidate()
    replacement = _replacement(current, inherited_pressure="新压力")
    request = ContractRevisionRequest.build(
        current, replacement, base_baseline_fingerprint="a" * 64,
        replacement_baseline_fingerprint="b" * 64,
        causal_impact_paths=("inherited_pressure",), scene_impact="因果压力变化",
        approved_change_requests=(_approved_change(current.inherited_pressure, "新压力"),),
    )
    assert request.requires_new_reviewer is True
    assert request.required_reviewer_binding.contract_content_hash == request.replacement_contract_content_hash
    assert request.required_reviewer_binding.baseline_fingerprint == "b" * 64


def test_every_business_change_must_be_present_in_causal_impact():
    current = _candidate()
    replacement = _replacement(current, arc_phase=ArcPhase.TURN)
    with pytest.raises(RevisionValidationError, match="causal impact"):
        ContractRevisionRequest.build(
            current, replacement, base_baseline_fingerprint="a" * 64,
            replacement_baseline_fingerprint="a" * 64,
            causal_impact_paths=(), scene_impact="转折",
            approved_change_requests=(_approved_change("escalation", "turn"),),
        )


def test_causal_affected_paths_also_trigger_special_reapproval():
    current = _candidate()
    replacement = _replacement(current, arc_phase=ArcPhase.TURN)
    request = ContractRevisionRequest.build(
        current, replacement, base_baseline_fingerprint="a" * 64,
        replacement_baseline_fingerprint="a" * 64,
        causal_impact_paths=("arc_phase", "chapter_contract.information.reveal[0]"),
        scene_impact="转折影响揭示",
        approved_change_requests=(_approved_change("escalation", "turn"),),
    )
    assert ContractApprovalPolicy.required_revision_approvals(
        current, replacement, request,
        authority_causal_impact_paths=("arc_phase", "chapter_contract.information.reveal[0]"),
        authority_approved_change_requests=(_approved_change("escalation", "turn"),),
    ) == (
        "full_contract", "information_reveal_and_misdirect", "outline_change",
        "post_freeze_revision",
    )


def test_policy_recomputes_diff_and_rejects_a_publicly_forged_request():
    current = _candidate()
    replacement = _replacement(current, arc_phase=ArcPhase.TURN)
    request = ContractRevisionRequest.build(
        current, replacement, base_baseline_fingerprint="a" * 64,
        replacement_baseline_fingerprint="a" * 64, causal_impact_paths=("arc_phase",),
        scene_impact="转折", approved_change_requests=(_approved_change("escalation", "turn"),),
    )
    other = _replacement(current, arc_goal="新目标")
    other_request = ContractRevisionRequest.build(
        current, other, base_baseline_fingerprint="a" * 64,
        replacement_baseline_fingerprint="a" * 64, causal_impact_paths=("arc_goal",),
        scene_impact="目标变化", approved_change_requests=(_approved_change(current.arc_goal, "新目标"),),
    )
    forged = replace(request, leaf_changes=other_request.leaf_changes)
    with pytest.raises(RevisionValidationError, match="canonical binding"):
        ContractApprovalPolicy.required_revision_approvals(
            current, replacement, forged,
            authority_causal_impact_paths=("arc_phase",),
            authority_approved_change_requests=(_approved_change("escalation", "turn"),),
        )


def test_policy_rejects_forged_causal_and_change_request_projections():
    current = _candidate()
    replacement = _replacement(current, arc_phase=ArcPhase.TURN)
    approved = _approved_change("escalation", "turn")
    request = ContractRevisionRequest.build(
        current, replacement, base_baseline_fingerprint="a" * 64,
        replacement_baseline_fingerprint="a" * 64, causal_impact_paths=("arc_phase",),
        scene_impact="转折", approved_change_requests=(approved,),
    )
    with pytest.raises(RevisionValidationError, match="canonical binding"):
        ContractApprovalPolicy.required_revision_approvals(
            current, replacement, replace(request, causal_impact_paths=()),
            authority_causal_impact_paths=("arc_phase",),
            authority_approved_change_requests=(approved,),
        )
    with pytest.raises(RevisionValidationError, match="approved NarrativeChangeRequest"):
        ContractApprovalPolicy.required_revision_approvals(
            current, replacement, replace(request, approved_change_requests=()),
            authority_causal_impact_paths=("arc_phase",),
            authority_approved_change_requests=(),
        )
    with pytest.raises(RevisionValidationError, match="non-canonical"):
        ContractApprovalPolicy.required_revision_approvals(
            current, replacement,
            replace(request, causal_impact_paths=("arc_phase", "chapter_contract.unknown")),
            authority_causal_impact_paths=("arc_phase", "chapter_contract.unknown"),
            authority_approved_change_requests=(approved,),
        )
    forged_reference = replace(
        request.approved_change_requests[0], request_content_hash="0" * 64,
    )
    with pytest.raises(RevisionValidationError, match="canonical binding"):
        ContractApprovalPolicy.required_revision_approvals(
            current, replacement,
            replace(request, approved_change_requests=(forged_reference,)),
            authority_causal_impact_paths=("arc_phase",),
            authority_approved_change_requests=(approved,),
        )


def test_revision_rejects_skipped_version_wrong_base_and_unreported_impact():
    current = _candidate()
    replacement = replace(_replacement(current, arc_phase=ArcPhase.TURN),
                          contract_version=current.contract_version + 2)
    with pytest.raises(RevisionValidationError):
        ContractRevisionRequest.build(
            current, replacement, base_baseline_fingerprint="a" * 64,
            replacement_baseline_fingerprint="a" * 64,
            causal_impact_paths=(), scene_impact="变化", approved_change_requests=(_approved_change(),),
        )
