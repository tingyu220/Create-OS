from dataclasses import replace

import pytest

from creative_os.domains import contract_approval
from creative_os.domains.contract_approval import (
    ApprovalItem,
    ApprovalStatus,
    ContractApprovalPolicy,
    ContractApprovalRecord,
)
from creative_os.domains.contract_baseline import BaselineEntry, BaselineManifest
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import NullablePlan
from creative_os.domains.narrative_evidence import EvidenceLocator, EvidenceRef, EvidenceRole
from tests.test_narrative_decision import _v2_decision


APPROVED_AT = "2026-08-20T08:30:00+00:00"
SPECIAL_ITEMS = (
    "major_choice_and_cost",
    "information_reveal_and_misdirect",
    "foreshadow_payoff_or_close",
    "new_facts",
    "outline_change",
    "post_freeze_revision",
)
PHASE_A_SPECIAL_ITEMS = SPECIAL_ITEMS[:-1]


def _baseline() -> BaselineManifest:
    return BaselineManifest.build(
        (
            BaselineEntry(
                role="profile",
                source_id="profile-main",
                source_version="5",
                content_hash="a" * 64,
            ),
        )
    )


def _item(status: ApprovalStatus = ApprovalStatus.APPROVED, *, reason: str = "人工确认") -> ApprovalItem:
    return ApprovalItem(
        status=status,
        reason=reason,
        approved_by="human-editor-7",
        approved_at=APPROVED_AT,
    )


def _record(
    *,
    full: ApprovalStatus = ApprovalStatus.APPROVED,
    overrides: dict[str, ApprovalItem] | None = None,
) -> ContractApprovalRecord:
    candidate = _v2_decision()
    values = {name: _item() for name in SPECIAL_ITEMS}
    values.update(overrides or {})
    return ContractApprovalRecord(
        contract_id="narrative-chapter-007",
        contract_version=2,
        contract_content_hash=NarrativeDecisionCodec.content_hash(candidate),
        baseline_manifest=_baseline(),
        full_contract=_item(full),
        **values,
    )


def _decision_evidence(
    role: EvidenceRole = EvidenceRole.DECISION,
    *,
    field_path: str = "chapter_contract.protagonist_choice.cost",
) -> EvidenceRef:
    return EvidenceRef(
        evidence_id="approval-evidence-1",
        contract_id="narrative-chapter-007",
        contract_version=2,
        field_path=field_path,
        role=role,
        source_id="approval-session-1",
        source_version="1",
        source_content_hash="e" * 64,
        locator=EvidenceLocator(kind="record_id", value="decision-1"),
        excerpt="编辑确认代价足以支撑不可逆选择。",
        assertion="批准重大选择与代价。",
    )


def test_approval_status_is_the_exact_three_state_domain():
    assert tuple(status.value for status in ApprovalStatus) == (
        "approved",
        "rejected",
        "not_applicable",
    )


@pytest.mark.parametrize("status", list(ApprovalStatus))
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reason", ""),
        ("approved_by", ""),
        ("approved_by", "system"),
        ("approved_at", ""),
        ("approved_at", "2026-08-20T08:30:00"),
    ],
)
def test_every_special_status_requires_reason_human_actor_and_timezone_aware_time(status, field, value):
    arguments = {
        "status": status,
        "reason": "人工确认",
        "approved_by": "human-editor-7",
        "approved_at": APPROVED_AT,
    }
    arguments[field] = value

    with pytest.raises(ValueError):
        ApprovalItem(**arguments)


def test_decision_evidence_is_accepted_only_on_the_external_approval_item():
    evidence = _decision_evidence()

    item = ApprovalItem(
        status=ApprovalStatus.APPROVED,
        reason="人工裁决已记录",
        approved_by="human-editor-7",
        approved_at=APPROVED_AT,
        decision_evidence=(evidence,),
    )
    record = _record(overrides={"major_choice_and_cost": item})

    assert record.major_choice_and_cost.decision_evidence == (evidence,)


def test_approval_item_rejects_non_decision_evidence_and_mutable_evidence_containers():
    with pytest.raises(ValueError, match="decision"):
        replace(_item(), decision_evidence=(_decision_evidence(EvidenceRole.INTENT),))

    with pytest.raises(TypeError, match="tuple"):
        replace(_item(), decision_evidence=[_decision_evidence()])


def test_full_contract_can_never_be_not_applicable():
    with pytest.raises(ValueError, match="full_contract"):
        _record(full=ApprovalStatus.NOT_APPLICABLE)


def test_an_applicable_special_item_cannot_be_not_applicable():
    record = _record(
        overrides={
            "major_choice_and_cost": _item(
                ApprovalStatus.NOT_APPLICABLE,
                reason="声称没有重大选择",
            )
        }
    )

    with pytest.raises(ValueError, match="invalid_approval_not_applicable"):
        ContractApprovalPolicy.validate(
            record,
            _v2_decision(),
        )


def test_a_non_applicable_special_item_is_valid_only_with_its_own_human_decision():
    item = _item(ApprovalStatus.NOT_APPLICABLE, reason="本章没有新增事实候选")
    record = _record(overrides={"new_facts": item})

    ContractApprovalPolicy.validate(record, _v2_decision())

    assert record.new_facts is item


def test_validate_rejects_a_different_candidate_that_hides_applicable_fields():
    approved_candidate = _v2_decision()
    hidden_foreshadow = replace(
        approved_candidate,
        chapter_contract=replace(
            approved_candidate.chapter_contract,
            foreshadow_actions=NullablePlan(
                values=(),
                not_applicable_reason="声称本章无伏笔动作",
            ),
        ),
    )

    with pytest.raises(ValueError, match="candidate binding"):
        ContractApprovalPolicy.validate(_record(), hidden_foreshadow)


def test_full_approval_and_special_rejection_conflict_in_both_directions():
    with pytest.raises(ValueError, match="conflicting approval"):
        _record(overrides={"major_choice_and_cost": _item(ApprovalStatus.REJECTED)})

    with pytest.raises(ValueError, match="conflicting approval"):
        _record(full=ApprovalStatus.REJECTED)


def test_record_rejects_wrong_identity_hash_type_and_decision_evidence_binding():
    with pytest.raises(ValueError):
        replace(_record(), contract_version=True)
    with pytest.raises(ValueError):
        replace(_record(), contract_content_hash="bad")

    wrong_contract = replace(_decision_evidence(), contract_id="narrative-chapter-008")
    with pytest.raises(ValueError, match="identity"):
        _record(overrides={"major_choice_and_cost": replace(_item(), decision_evidence=(wrong_contract,))})


@pytest.mark.parametrize(
    ("item_name", "wrong_path"),
    [
        ("major_choice_and_cost", "arc_goal"),
        ("information_reveal_and_misdirect", "chapter_contract.protagonist_choice.cost"),
        ("outline_change", "chapter_contract.information.reveal[0]"),
    ],
)
def test_special_decision_evidence_must_land_in_that_items_coverage(item_name, wrong_path):
    item = replace(_item(), decision_evidence=(_decision_evidence(field_path=wrong_path),))

    with pytest.raises(ValueError, match="coverage"):
        _record(overrides={item_name: item})


def test_full_contract_decision_evidence_can_cover_any_concrete_contract_field():
    full_item = replace(
        _item(),
        decision_evidence=(
            _decision_evidence(field_path="chapter_contract.target_chinese_chars"),
        ),
    )

    record = replace(_record(), full_contract=full_item)

    assert record.full_contract is full_item


def test_full_contract_decision_evidence_rejects_a_concrete_but_unrelated_domain():
    full_item = replace(
        _item(),
        decision_evidence=(
            _decision_evidence(field_path="unrelated_resource.secret"),
        ),
    )

    with pytest.raises(ValueError, match="coverage"):
        replace(_record(), full_contract=full_item)


def test_covered_paths_are_the_exact_immutable_design_table():
    assert ContractApprovalPolicy.covered_paths("full_contract") == (
        "NarrativeDecision.*",
        "BaselineManifest.fingerprint",
    )
    assert ContractApprovalPolicy.covered_paths("major_choice_and_cost") == (
        "chapter_contract.protagonist_choice.*",
        "chapter_contract.pressure_curve.*",
        "chapter_contract.ending_shift",
    )
    assert ContractApprovalPolicy.covered_paths("information_reveal_and_misdirect") == (
        "chapter_contract.information.*",
        "chapter_contract.reader_change.*",
        "chapter_contract.forbidden.*",
    )
    assert ContractApprovalPolicy.covered_paths("foreshadow_payoff_or_close") == (
        "chapter_contract.foreshadow_actions.*",
        "hook_refs[*]",
    )
    assert ContractApprovalPolicy.covered_paths("new_facts") == (
        "new_fact_candidates[*]",
        "fact_boundary_refs[*]",
    )
    assert ContractApprovalPolicy.covered_paths("outline_change") == (
        "arc_phase",
        "arc_goal",
        "change_requests[*]",
    )
    assert ContractApprovalPolicy.covered_paths("post_freeze_revision") == (
        "revision_request.changed_field_paths[*]",
    )

    with pytest.raises(ValueError):
        ContractApprovalPolicy.covered_paths("unknown")


def test_required_items_cannot_hide_candidate_fields_by_omitting_event_inputs():
    assert ContractApprovalPolicy.required_items(_v2_decision()) == (
        "full_contract",
        "major_choice_and_cost",
        "information_reveal_and_misdirect",
        "foreshadow_payoff_or_close",
    )


def test_required_items_add_only_explicit_phase_a_event_domains():
    assert ContractApprovalPolicy.required_items(
        _v2_decision(),
        contract_approval.PhaseAApprovalEvents(
            new_fact_paths=("new_fact_candidates[0]",),
            outline_change_paths=("change_requests[0]",),
        )
    ) == ("full_contract", *PHASE_A_SPECIAL_ITEMS)


def test_phase_a_policy_rejects_falsey_values_that_are_not_event_objects():
    with pytest.raises(TypeError, match="PhaseAApprovalEvents"):
        ContractApprovalPolicy.required_items(_v2_decision(), ())

    changes = contract_approval.PhaseAReapprovalChanges(
        direct_changed_paths=("chapter_contract.ending_shift",),
    )
    with pytest.raises(TypeError, match="PhaseAApprovalEvents"):
        ContractApprovalPolicy.required_reapprovals(_v2_decision(), changes, ())


@pytest.mark.parametrize(
    ("direct_paths", "causal_paths", "expected"),
    [
        (
            ("chapter_contract.protagonist_choice.cost",),
            (),
            ("full_contract", "major_choice_and_cost"),
        ),
        (
            (),
            ("chapter_contract.reader_change.after",),
            ("full_contract", "information_reveal_and_misdirect"),
        ),
    ],
)
def test_required_reapprovals_distinguish_direct_and_causal_affected_paths(direct_paths, causal_paths, expected):
    changes = contract_approval.PhaseAReapprovalChanges(
        direct_changed_paths=direct_paths,
        causal_dependency_affected_paths=causal_paths,
    )

    assert ContractApprovalPolicy.required_reapprovals(_v2_decision(), changes) == expected


def test_required_reapprovals_requires_the_real_candidate_even_for_direct_changes():
    changes = contract_approval.PhaseAReapprovalChanges(
        direct_changed_paths=("chapter_contract.protagonist_choice.cost",),
    )

    with pytest.raises(TypeError, match="NarrativeDecision"):
        ContractApprovalPolicy.required_reapprovals(object(), changes)


@pytest.mark.parametrize(
    ("baseline_role", "expected"),
    [
        (
            "profile",
            (
                "full_contract",
                "major_choice_and_cost",
                "information_reveal_and_misdirect",
                "foreshadow_payoff_or_close",
            ),
        ),
        (
            "previous_chapter",
            (
                "full_contract",
                "major_choice_and_cost",
                "information_reveal_and_misdirect",
                "foreshadow_payoff_or_close",
            ),
        ),
        (
            "fact_snapshot",
            (
                "full_contract",
                "major_choice_and_cost",
                "information_reveal_and_misdirect",
                "foreshadow_payoff_or_close",
            ),
        ),
        (
            "outline_change",
            (
                "full_contract",
                "major_choice_and_cost",
                "information_reveal_and_misdirect",
                "foreshadow_payoff_or_close",
                "outline_change",
            ),
        ),
    ],
)
def test_baseline_role_changes_propagate_to_currently_affected_special_items(baseline_role, expected):
    changes = contract_approval.PhaseAReapprovalChanges(baseline_changed_roles=(baseline_role,))

    assert ContractApprovalPolicy.required_reapprovals(_v2_decision(), changes) == expected


def test_phase_a_event_changes_map_to_their_special_reapprovals():
    changes = contract_approval.PhaseAReapprovalChanges(
        event_changes=contract_approval.PhaseAApprovalEvents(
            foreshadow_event_paths=("hook_refs[0]",),
            new_fact_paths=("new_fact_candidates[0]",),
            outline_change_paths=("change_requests[0]",),
        )
    )

    assert ContractApprovalPolicy.required_reapprovals(_v2_decision(), changes) == (
        "full_contract",
        "foreshadow_payoff_or_close",
        "new_facts",
        "outline_change",
    )


def test_phase_a_reapproval_changes_reject_post_freeze_revision_input():
    with pytest.raises(ValueError, match="Phase A"):
        contract_approval.PhaseAReapprovalChanges(
            direct_changed_paths=("revision_request.changed_field_paths[0]",),
        )


@pytest.mark.parametrize(
    "malformed_path",
    [
        "hook_refs[]",
        "hook_refs[*]",
        "hook_refs[-1]",
        "hook_refs[hook-7]",
        "hook_refs[0",
        "hook_refs[0]..status",
    ],
)
def test_phase_a_event_inputs_reject_non_concrete_or_malformed_paths(malformed_path):
    with pytest.raises(ValueError, match="field path"):
        contract_approval.PhaseAApprovalEvents(
            foreshadow_event_paths=(malformed_path,),
        )


@pytest.mark.parametrize(
    "malformed_path",
    [
        "future_pressures[]",
        "future_pressures[*]",
        "future_pressures[-1]",
        "future_pressures[index]",
        "chapter_contract..ending_shift",
    ],
)
def test_change_sets_reject_non_concrete_or_malformed_paths(malformed_path):
    with pytest.raises(ValueError, match="field path"):
        contract_approval.PhaseAReapprovalChanges(
            direct_changed_paths=(malformed_path,),
        )


def test_pattern_matching_accepts_numeric_indices_and_explicit_subfields():
    events = contract_approval.PhaseAApprovalEvents(
        new_fact_paths=("new_fact_candidates[0].fact_id",),
    )
    changes = contract_approval.PhaseAReapprovalChanges(
        direct_changed_paths=("chapter_contract.information.reveal[0]",),
        event_changes=events,
    )

    assert ContractApprovalPolicy.required_items(_v2_decision(), events)[-1] == "new_facts"
    assert ContractApprovalPolicy.required_reapprovals(_v2_decision(), changes) == (
        "full_contract",
        "information_reveal_and_misdirect",
        "new_facts",
    )


def test_decision_evidence_rejects_patterns_and_accepts_concrete_index_subfields():
    with pytest.raises(ValueError, match="field path"):
        replace(
            _record(),
            full_contract=replace(
                _item(),
                decision_evidence=(
                    _decision_evidence(field_path="chapter_contract.information.reveal[*]"),
                ),
            ),
        )

    new_fact_item = replace(
        _item(),
        decision_evidence=(
            _decision_evidence(field_path="new_fact_candidates[0].fact_id"),
        ),
    )
    record = _record(overrides={"new_facts": new_fact_item})

    assert record.new_facts is new_fact_item
