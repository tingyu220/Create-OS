from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from creative_os.domains.contract_approval import (
    ApprovalItem,
    ApprovalStatus,
    ContractApprovalRecord,
)
from creative_os.domains.contract_baseline import BaselineEntry, BaselineManifest
from creative_os.domains.contract_issue import EvidenceCheck
from creative_os.domains.contract_record_store import (
    ContractRecordConflictError,
    ContractRecordStore,
    ContractRecordStoreError,
)
from creative_os.domains.contract_review import (
    PrewriteReviewerResult,
    ReviewIssue,
    ReviewIssueDisposition,
)


CONTRACT_ID = "narrative-chapter-007"
CONTRACT_VERSION = 2
CONTRACT_HASH = "a" * 64
APPROVED_AT = "2026-08-20T08:30:00+00:00"


def _canonical_hash(payload: object) -> str:
    value = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _baseline(content_hash: str = "b" * 64) -> BaselineManifest:
    return BaselineManifest.build(
        (
            BaselineEntry(
                role="profile",
                source_id="profile-main",
                source_version="5",
                content_hash=content_hash,
            ),
        )
    )


def _approval_item(reason: str = "人工确认") -> ApprovalItem:
    return ApprovalItem(
        status=ApprovalStatus.APPROVED,
        reason=reason,
        approved_by="editor-tingyu",
        approved_at=APPROVED_AT,
    )


def _approval(
    baseline: BaselineManifest,
    *,
    contract_id: str = CONTRACT_ID,
    reason: str = "人工确认",
) -> ContractApprovalRecord:
    item = _approval_item(reason)
    return ContractApprovalRecord(
        contract_id=contract_id,
        contract_version=CONTRACT_VERSION,
        contract_content_hash=CONTRACT_HASH,
        baseline_manifest=baseline,
        full_contract=item,
        major_choice_and_cost=item,
        information_reveal_and_misdirect=item,
        foreshadow_payoff_or_close=item,
        new_facts=item,
        outline_change=item,
        post_freeze_revision=item,
    )


def _issue(
    *,
    issue_id: str = "issue-cost",
    field_path: str = "chapter_contract.protagonist_choice.cost",
) -> ReviewIssue:
    return ReviewIssue.build(
        issue_id=issue_id,
        code="missing_choice_cost",
        severity="warning",
        blocking=True,
        requires_human_disposition=False,
        field_path=field_path,
        evidence_checks=(
            EvidenceCheck(code="field_found", passed=False, detail="未找到选择代价"),
        ),
        repair_hint="补充选择代价或由人工裁决",
    )


def _review(
    baseline: BaselineManifest,
    *,
    result_id: str = "review-001",
    contract_id: str = CONTRACT_ID,
    ruleset_version: str = "prewrite-v1",
    issues: tuple[ReviewIssue, ...] | None = None,
) -> PrewriteReviewerResult:
    return PrewriteReviewerResult.build(
        result_id=result_id,
        contract_id=contract_id,
        contract_version=CONTRACT_VERSION,
        contract_content_hash=CONTRACT_HASH,
        baseline_fingerprint=baseline.fingerprint,
        ruleset_version=ruleset_version,
        semantic_asset_versions=(("function_semantics", "v1"),),
        issues=(_issue(),) if issues is None else issues,
    )


def _disposition(
    result: PrewriteReviewerResult,
    issue: ReviewIssue,
    *,
    reason: str = "主编确认当前缺口可接受",
) -> ReviewIssueDisposition:
    return ReviewIssueDisposition(
        issue_id=issue.issue_id,
        canonical_issue_hash=issue.canonical_issue_hash,
        issue_code=issue.code,
        field_path=issue.field_path,
        evidence_hash=issue.evidence_hash,
        status="accepted",
        reason=reason,
        actor="editor-tingyu",
        decided_at="2026-08-20T10:30:00+08:00",
        reviewer_result_id=result.result_id,
        reviewer_result_hash=result.result_hash,
    )


def _seed(store: ContractRecordStore):
    baseline = _baseline()
    approval = _approval(baseline)
    review = _review(baseline)
    disposition = _disposition(review, review.issues[0])
    ids = (
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline),
        store.save_approval(approval),
        store.save_reviewer_result(review),
        store.save_disposition(disposition),
    )
    return baseline, approval, review, disposition, ids


def _record_root(project_root: Path) -> Path:
    return project_root / ".creative_os" / "memory" / "contract_records"


def _io_path(path: Path) -> Path:
    if os.name != "nt":
        return path
    return Path("\\\\?\\" + str(path.absolute()))


def test_four_record_types_use_exact_physical_keys_envelopes_and_round_trip(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    baseline, approval, review, disposition, ids = _seed(store)
    disposition_payload = {
        "actor": disposition.actor,
        "canonical_issue_hash": disposition.canonical_issue_hash,
        "decided_at": disposition.decided_at,
        "evidence_hash": disposition.evidence_hash,
        "field_path": disposition.field_path,
        "issue_code": disposition.issue_code,
        "issue_id": disposition.issue_id,
        "reason": disposition.reason,
        "reviewer_result_hash": disposition.reviewer_result_hash,
        "reviewer_result_id": disposition.reviewer_result_id,
        "status": disposition.status,
    }

    assert ids == (
        f"baseline-{CONTRACT_ID}-v0002-{baseline.fingerprint}",
        f"approval-{CONTRACT_ID}-v0002-{CONTRACT_HASH}-{baseline.fingerprint}",
        f"review-{CONTRACT_ID}-v0002-{review.result_hash}",
        (
            f"disposition-{review.result_id}-{disposition.issue_id}-"
            f"{disposition.canonical_issue_hash}-{_canonical_hash(disposition_payload)}"
        ),
    )
    root = _record_root(tmp_path)
    assert {path.name for path in root.iterdir()} == {
        "baselines",
        "approvals",
        "reviews",
        "dispositions",
        "journal",
    }
    for directory, record_id, record_type in zip(
        ("baselines", "approvals", "reviews", "dispositions"),
        ids,
        ("baseline", "approval", "reviewer_result", "disposition"),
        strict=True,
    ):
        envelope = json.loads(
            _io_path(root / directory / f"{record_id}.json").read_text(encoding="utf-8")
        )
        assert set(envelope) == {"record_type", "schema_version", "payload_hash", "payload"}
        assert envelope["record_type"] == record_type
        assert envelope["schema_version"] == 1
        assert envelope["payload_hash"] == _canonical_hash(envelope["payload"])

    restarted = ContractRecordStore(tmp_path)
    assert restarted.load_baseline(ids[0]) == baseline
    assert restarted.load_approval(ids[1]) == approval
    assert restarted.load_reviewer_result(ids[2]) == review
    assert restarted.load_disposition(ids[3]) == disposition


def test_exact_repeated_saves_are_idempotent_but_same_id_different_content_conflicts(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    baseline_id = store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    approval = _approval(baseline)
    approval_id = store.save_approval(approval)

    assert store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline) == baseline_id
    assert store.save_approval(approval) == approval_id

    changed = replace(approval, full_contract=_approval_item("另一份人工裁决"))
    with pytest.raises(ContractRecordConflictError):
        store.save_approval(changed)
    assert store.load_approval(approval_id) == approval


def test_save_and_load_reject_unsafe_slugs_and_path_escape(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    baseline = _baseline()

    with pytest.raises(ContractRecordStoreError):
        store.save_baseline("../outside", CONTRACT_VERSION, baseline)
    with pytest.raises(ContractRecordStoreError):
        store.load_baseline("../outside")

    review = _review(baseline, result_id="../review")
    disposition = _disposition(review, review.issues[0])
    with pytest.raises(ContractRecordStoreError):
        store.save_disposition(disposition)

    overlong_review = _review(baseline, result_id="r" * 53)
    store.save_reviewer_result(overlong_review)
    with pytest.raises(ContractRecordStoreError):
        store.save_disposition(_disposition(overlong_review, overlong_review.issues[0]))
    assert not (tmp_path / "outside.json").exists()


@pytest.mark.parametrize(
    "mutation",
    ("payload", "payload_hash", "unknown", "missing", "schema_type"),
)
def test_strict_load_rejects_payload_hash_unknown_missing_and_wrong_types(tmp_path: Path, mutation: str):
    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    record_id = store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    path = _record_root(tmp_path) / "baselines" / f"{record_id}.json"
    envelope = json.loads(_io_path(path).read_text(encoding="utf-8"))

    if mutation == "payload":
        envelope["payload"]["contract_version"] = 3
    elif mutation == "payload_hash":
        envelope["payload_hash"] = "0" * 64
    elif mutation == "unknown":
        envelope["unexpected"] = True
    elif mutation == "missing":
        del envelope["record_type"]
    else:
        envelope["schema_version"] = True
    _io_path(path).write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ContractRecordStoreError):
        ContractRecordStore(tmp_path).load_baseline(record_id)


def test_tampered_filename_is_rejected_and_never_used_by_exact_lookup(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    record_id = store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    original = _record_root(tmp_path) / "baselines" / f"{record_id}.json"
    renamed = original.with_name(f"{record_id}-forged.json")
    _io_path(original).replace(_io_path(renamed))

    with pytest.raises(ContractRecordStoreError):
        ContractRecordStore(tmp_path).load_baseline(f"{record_id}-forged")
    with pytest.raises(ContractRecordStoreError):
        ContractRecordStore(tmp_path).find_exact(
            contract_id=CONTRACT_ID,
            contract_version=CONTRACT_VERSION,
            contract_hash=CONTRACT_HASH,
            baseline_fingerprint=baseline.fingerprint,
        )


def test_find_exact_rebuilds_cross_record_bindings_after_restart(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    baseline, approval, review, disposition, ids = _seed(store)

    exact = ContractRecordStore(tmp_path).find_exact(
        contract_id=CONTRACT_ID,
        contract_version=CONTRACT_VERSION,
        contract_hash=CONTRACT_HASH,
        baseline_fingerprint=baseline.fingerprint,
        ruleset_version=review.ruleset_version,
    )

    assert exact is not None
    assert exact.baseline == baseline
    assert exact.approval == approval
    assert exact.reviewer_result == review
    assert exact.dispositions == (disposition,)
    assert exact.record_ids == ids
    assert ContractRecordStore(tmp_path).find_exact(
        contract_id=CONTRACT_ID,
        contract_version=CONTRACT_VERSION,
        contract_hash="f" * 64,
        baseline_fingerprint=baseline.fingerprint,
        ruleset_version=review.ruleset_version,
    ) is None


def test_find_exact_never_returns_foreign_reviewer_or_issue_bindings(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    baseline, _, review, disposition, _ = _seed(store)
    foreign_baseline = _baseline("c" * 64)
    store.save_baseline("narrative-chapter-008", CONTRACT_VERSION, foreign_baseline)
    foreign_review = _review(
        foreign_baseline,
        result_id="review-foreign",
        contract_id="narrative-chapter-008",
    )
    store.save_reviewer_result(foreign_review)
    store.save_disposition(_disposition(foreign_review, foreign_review.issues[0]))

    exact = store.find_exact(
        contract_id=CONTRACT_ID,
        contract_version=CONTRACT_VERSION,
        contract_hash=CONTRACT_HASH,
        baseline_fingerprint=baseline.fingerprint,
        ruleset_version=review.ruleset_version,
    )

    assert exact is not None
    assert exact.reviewer_result == review
    assert exact.dispositions == (disposition,)

    wrong_issue = replace(disposition, issue_id="other-issue")
    with pytest.raises(ContractRecordStoreError):
        store.save_disposition(wrong_issue)


def test_find_exact_fails_closed_when_multiple_reviewer_results_match(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    store.save_approval(_approval(baseline))
    store.save_reviewer_result(_review(baseline, result_id="review-001", issues=()))
    store.save_reviewer_result(_review(baseline, result_id="review-002", issues=()))

    with pytest.raises(ContractRecordConflictError, match="ambiguous"):
        store.find_exact(
            contract_id=CONTRACT_ID,
            contract_version=CONTRACT_VERSION,
            contract_hash=CONTRACT_HASH,
            baseline_fingerprint=baseline.fingerprint,
            ruleset_version="prewrite-v1",
        )


@pytest.mark.parametrize(
    ("fail_call", "write_before_failure", "recovered"),
    (
        (1, False, False),
        (1, True, True),
        (2, False, True),
        (2, True, True),
        (3, False, True),
        (3, True, True),
    ),
    ids=(
        "before-prepare",
        "after-prepare",
        "before-record",
        "after-record",
        "before-commit",
        "after-commit",
    ),
)
def test_recover_has_a_deterministic_action_at_every_journal_fault_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_call: int,
    write_before_failure: bool,
    recovered: bool,
):
    import creative_os.domains.contract_record_store as record_store_module

    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    original = record_store_module._atomic_write_json
    calls = 0

    def fail_once(path, payload):
        nonlocal calls
        calls += 1
        if calls == fail_call and not write_before_failure:
            raise OSError("simulated crash")
        original(path, payload)
        if calls == fail_call and write_before_failure:
            raise OSError("simulated crash")

    monkeypatch.setattr(record_store_module, "_atomic_write_json", fail_once)
    with pytest.raises(ContractRecordStoreError):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    monkeypatch.setattr(record_store_module, "_atomic_write_json", original)

    restarted = ContractRecordStore(tmp_path)
    restarted.recover()
    record_id = f"baseline-{CONTRACT_ID}-v0002-{baseline.fingerprint}"
    if recovered:
        assert restarted.load_baseline(record_id) == baseline
    else:
        with pytest.raises(KeyError):
            restarted.load_baseline(record_id)


def test_recover_never_overwrites_a_different_valid_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import creative_os.domains.contract_record_store as record_store_module

    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    approval = _approval(baseline)
    original = record_store_module._atomic_write_json
    calls = 0

    def stop_before_record(path, payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated crash")
        original(path, payload)

    monkeypatch.setattr(record_store_module, "_atomic_write_json", stop_before_record)
    with pytest.raises(ContractRecordStoreError):
        store.save_approval(approval)
    monkeypatch.setattr(record_store_module, "_atomic_write_json", original)

    other_root = tmp_path / "other"
    other = ContractRecordStore(other_root)
    other.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    changed = replace(approval, full_contract=_approval_item("冲突的人工裁决"))
    changed_id = other.save_approval(changed)
    foreign_path = _record_root(other_root) / "approvals" / f"{changed_id}.json"
    target_path = _record_root(tmp_path) / "approvals" / f"{changed_id}.json"
    _io_path(target_path).write_bytes(_io_path(foreign_path).read_bytes())
    before = _io_path(target_path).read_bytes()

    with pytest.raises(ContractRecordConflictError):
        ContractRecordStore(tmp_path).recover()
    assert _io_path(target_path).read_bytes() == before


def test_concurrent_same_and_different_content_writes_are_serialized_deterministically(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    approval = _approval(baseline)

    with ThreadPoolExecutor(max_workers=8) as pool:
        record_ids = tuple(pool.map(lambda _: store.save_approval(approval), range(16)))
    assert len(set(record_ids)) == 1

    second_root = tmp_path / "conflict"
    second_store = ContractRecordStore(second_root)
    second_store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    alternatives = (approval, replace(approval, full_contract=_approval_item("另一份裁决")))

    def save(candidate):
        try:
            return ("saved", second_store.save_approval(candidate))
        except ContractRecordConflictError:
            return ("conflict", None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(save, alternatives))
    assert sorted(status for status, _ in outcomes) == ["conflict", "saved"]
