from dataclasses import replace

import pytest

from creative_os.domains.contract_approval import (
    ApprovalItem,
    ApprovalStatus,
    ContractApprovalPolicy,
    ContractApprovalRecord,
)
from creative_os.domains.contract_baseline import BaselineEntry, BaselineManifest
from creative_os.domains.narrative_evidence import EvidenceLocator, EvidenceRef, EvidenceRole


APPROVED_AT = "2026-08-20T08:30:00+00:00"
SPECIAL_ITEMS = (
    "major_choice_and_cost",
    "information_reveal_and_misdirect",
    "foreshadow_payoff_or_close",
    "new_facts",
    "outline_change",
    "post_freeze_revision",
)


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
    values = {name: _item() for name in SPECIAL_ITEMS}
    values.update(overrides or {})
    return ContractApprovalRecord(
        contract_id="narrative-chapter-007",
        contract_version=2,
        contract_content_hash="c" * 64,
        baseline_manifest=_baseline(),
        full_contract=_item(full),
        **values,
    )


def _decision_evidence(role: EvidenceRole = EvidenceRole.DECISION) -> EvidenceRef:
    return EvidenceRef(
        evidence_id="approval-evidence-1",
        contract_id="narrative-chapter-007",
        contract_version=2,
        field_path="chapter_contract.protagonist_choice.cost",
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
            ("chapter_contract.protagonist_choice.cost",),
        )


def test_a_non_applicable_special_item_is_valid_only_with_its_own_human_decision():
    item = _item(ApprovalStatus.NOT_APPLICABLE, reason="本章没有新增事实候选")
    record = _record(overrides={"new_facts": item})

    ContractApprovalPolicy.validate(record, ("chapter_contract.protagonist_choice.cost",))

    assert record.new_facts is item


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


def test_required_items_are_derived_from_exact_applicable_paths_without_prefix_leaks():
    assert ContractApprovalPolicy.required_items(
        (
            "chapter_contract.protagonist_choice.cost",
            "chapter_contract.information.reveal[0]",
            "hook_refs[hook-7]",
            "new_fact_candidates[fact-3]",
            "change_requests[change-2]",
            "revision_request.changed_field_paths[0]",
        )
    ) == ("full_contract", *SPECIAL_ITEMS)

    assert ContractApprovalPolicy.required_items(("chapter_contract.protagonist_choice_backup.cost",)) == (
        "full_contract",
    )
    assert ContractApprovalPolicy.required_items(
        ("chapter_contract.foreshadow_actions.not_applicable_reason",)
    ) == ("full_contract",)


@pytest.mark.parametrize(
    ("changed_paths", "expected"),
    [
        (("BaselineManifest.fingerprint",), ("full_contract",)),
        (
            ("chapter_contract.protagonist_choice.cost",),
            ("full_contract", "major_choice_and_cost"),
        ),
        (
            ("chapter_contract.information.misdirect.not_applicable_reason",),
            ("full_contract", "information_reveal_and_misdirect"),
        ),
        (
            ("chapter_contract.foreshadow_actions.not_applicable_reason",),
            ("full_contract", "foreshadow_payoff_or_close"),
        ),
        (("new_fact_candidates[fact-3]",), ("full_contract", "new_facts")),
        (("arc_goal",), ("full_contract", "outline_change")),
        (
            ("revision_request.changed_field_paths[0]",),
            ("full_contract", "post_freeze_revision"),
        ),
        (("chapter_contract.target_chinese_chars",), ("full_contract",)),
        ((), ()),
    ],
)
def test_required_reapprovals_precisely_cover_field_baseline_and_event_changes(changed_paths, expected):
    assert ContractApprovalPolicy.required_reapprovals(changed_paths) == expected
