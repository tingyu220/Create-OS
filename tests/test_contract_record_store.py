from __future__ import annotations

import hashlib
import json
import multiprocessing
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
from creative_os.domains.narrative_evidence import EvidenceLocator, EvidenceRef, EvidenceRole


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


def _record_path(project_root: Path, directory: str, record_id: str) -> Path:
    return _record_root(project_root) / directory / f"{record_id}.json"


def _journal_path(project_root: Path, record_type: str, record_id: str) -> Path:
    operation_id = _canonical_hash({"record_id": record_id, "record_type": record_type})
    return _record_root(project_root) / "journal" / f"{operation_id}.json"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(_io_path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    _io_path(path).write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
    )


def _copy_file(source: Path, target: Path) -> None:
    _io_path(target).write_bytes(_io_path(source).read_bytes())


def _install_prepared_journal(
    source_root: Path,
    target_root: Path,
    record_type: str,
    record_id: str,
) -> Path:
    journal = _read_json(_journal_path(source_root, record_type, record_id))
    journal["state"] = "prepared"
    journal["entry_hash"] = _canonical_hash(
        {key: value for key, value in journal.items() if key != "entry_hash"}
    )
    target = _journal_path(target_root, record_type, record_id)
    _write_json(target, journal)
    return target


def _process_save_approval(
    project_root: str,
    reason: str,
    start_event,
    result_queue,
) -> None:
    """Spawn-safe worker proving serialization is provided by the OS lock."""
    try:
        store = ContractRecordStore(project_root)
        approval = _approval(_baseline(), reason=reason)
        if not start_event.wait(15):
            result_queue.put(("timeout", reason))
            return
        result_queue.put(("saved", store.save_approval(approval)))
    except ContractRecordConflictError:
        result_queue.put(("conflict", reason))
    except Exception as error:  # pragma: no cover - reported to the parent assertion
        result_queue.put(("error", f"{type(error).__name__}: {error}"))


def test_authority_record_types_use_exact_physical_keys_envelopes_and_round_trip(tmp_path: Path):
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
        "continuation_authorizations",
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


def test_approval_decision_evidence_round_trips_every_nested_field(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    evidence = EvidenceRef(
        evidence_id="approval-evidence-1",
        contract_id=CONTRACT_ID,
        contract_version=CONTRACT_VERSION,
        field_path="chapter_contract.protagonist_choice.cost",
        role=EvidenceRole.DECISION,
        source_id="approval-session-1",
        source_version="7",
        source_content_hash="e" * 64,
        locator=EvidenceLocator(kind="record_id", value="decision-7"),
        excerpt="主编确认当前选择代价。",
        assertion="批准重大选择与代价。",
        asserted_value=True,
    )
    item = replace(_approval_item(), decision_evidence=(evidence,))
    approval = replace(_approval(baseline), major_choice_and_cost=item)

    record_id = store.save_approval(approval)

    assert ContractRecordStore(tmp_path).load_approval(record_id) == approval


def test_generic_load_reconstructs_each_authoritative_record_type(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    baseline, approval, review, disposition, record_ids = _seed(store)

    assert tuple(store.load(record_id) for record_id in record_ids) == (
        baseline,
        approval,
        review,
        disposition,
    )


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

    assert not (tmp_path / "outside.json").exists()


@pytest.mark.parametrize(
    "result",
    (
        _review(_baseline(), result_id="审阅-001"),
        _review(_baseline(), result_id="r" * 65),
        _review(_baseline(), issues=(_issue(issue_id="问题-代价"),)),
        _review(_baseline(), issues=(_issue(issue_id="i" * 65),)),
        _review(
            _baseline(),
            issues=(
                _issue(),
                _issue(
                    issue_id="问题-后果",
                    field_path="chapter_contract.protagonist_choice.consequence",
                ),
            ),
        ),
        _review(
            _baseline(),
            result_id="r" * 64,
            issues=(_issue(issue_id="i" * 64),),
        ),
    ),
    ids=(
        "unicode-result",
        "overlong-result",
        "unicode-issue",
        "overlong-issue",
        "later-unicode-issue",
        "combined-key",
    ),
)
def test_reviewer_save_rejects_any_issue_without_a_safe_future_disposition_key(
    tmp_path: Path,
    result: PrewriteReviewerResult,
):
    store = ContractRecordStore(tmp_path)

    with pytest.raises(ContractRecordStoreError):
        store.save_reviewer_result(result)

    root = _record_root(tmp_path)
    assert tuple((root / "reviews").glob("*.json")) == ()
    assert tuple((root / "journal").glob("*.json")) == ()


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


@pytest.mark.parametrize("mutation", ("duplicate-key", "noncanonical"))
def test_strict_load_rejects_duplicate_keys_and_noncanonical_json(tmp_path: Path, mutation: str):
    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    record_id = store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    path = _record_path(tmp_path, "baselines", record_id)
    raw = _io_path(path).read_text(encoding="utf-8")
    if mutation == "duplicate-key":
        raw = raw.replace('{\n  "payload":', '{\n  "record_type": "baseline",\n  "payload":', 1)
    else:
        raw = json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True)
    _io_path(path).write_text(raw, encoding="utf-8")

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


@pytest.mark.parametrize("mutation", ("entry-hash", "state", "filename"))
def test_recover_rejects_journal_hash_state_and_filename_tamper(tmp_path: Path, mutation: str):
    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    record_id = store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    journal_path = _journal_path(tmp_path, "baseline", record_id)
    if mutation == "filename":
        forged = journal_path.with_name(f"{journal_path.stem}-forged.json")
        _io_path(journal_path).replace(_io_path(forged))
    else:
        journal = _read_json(journal_path)
        if mutation == "entry-hash":
            journal["entry_hash"] = "0" * 64
        else:
            journal["state"] = "unknown"
            journal["entry_hash"] = _canonical_hash(
                {key: value for key, value in journal.items() if key != "entry_hash"}
            )
        _write_json(journal_path, journal)

    with pytest.raises(ContractRecordStoreError):
        ContractRecordStore(tmp_path).recover()


def test_recover_rejects_a_committed_journal_whose_record_is_missing_after_backup(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    record_id = store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    record_path = _record_path(tmp_path, "baselines", record_id)
    backup = tmp_path / "missing-record-backup.json"
    backup.write_bytes(_io_path(record_path).read_bytes())
    _io_path(record_path).unlink()

    with pytest.raises(ContractRecordStoreError, match="missing"):
        ContractRecordStore(tmp_path).recover()

    assert backup.read_bytes()


def test_recover_rejects_an_orphan_record_without_a_journal(tmp_path: Path):
    source_root = tmp_path / "source"
    source = ContractRecordStore(source_root)
    baseline = _baseline()
    record_id = source.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    store = ContractRecordStore(tmp_path)
    _copy_file(
        _record_path(source_root, "baselines", record_id),
        _record_path(tmp_path, "baselines", record_id),
    )

    with pytest.raises(ContractRecordStoreError, match="orphan"):
        store.recover()


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


@pytest.mark.parametrize("read_path", ("load_disposition", "load", "recover", "find_exact"))
def test_every_authoritative_read_rejects_a_disposition_without_its_exact_reviewer_issue(
    tmp_path: Path,
    read_path: str,
):
    store = ContractRecordStore(tmp_path)
    baseline, _, review, _, _ = _seed(store)
    foreign_root = tmp_path / "foreign"
    foreign_store = ContractRecordStore(foreign_root)
    foreign_review = _review(baseline, result_id="review-foreign")
    foreign_store.save_reviewer_result(foreign_review)
    foreign_disposition = _disposition(foreign_review, foreign_review.issues[0])
    foreign_id = foreign_store.save_disposition(foreign_disposition)
    _copy_file(
        _record_path(foreign_root, "dispositions", foreign_id),
        _record_path(tmp_path, "dispositions", foreign_id),
    )
    _copy_file(
        _journal_path(foreign_root, "disposition", foreign_id),
        _journal_path(tmp_path, "disposition", foreign_id),
    )

    with pytest.raises(ContractRecordStoreError):
        if read_path == "load_disposition":
            store.load_disposition(foreign_id)
        elif read_path == "load":
            store.load(foreign_id)
        elif read_path == "recover":
            store.recover()
        else:
            store.find_exact(
                contract_id=CONTRACT_ID,
                contract_version=CONTRACT_VERSION,
                contract_hash=CONTRACT_HASH,
                baseline_fingerprint=baseline.fingerprint,
                ruleset_version=review.ruleset_version,
            )


@pytest.mark.parametrize("reviewer_state", ("missing", "mismatched"))
def test_prepared_disposition_recovery_validates_reviewer_before_record_or_commit(
    tmp_path: Path,
    reviewer_state: str,
):
    baseline = _baseline()
    foreign_root = tmp_path / "foreign"
    foreign_store = ContractRecordStore(foreign_root)
    foreign_review = _review(baseline, result_id="review-foreign")
    foreign_store.save_reviewer_result(foreign_review)
    disposition = _disposition(foreign_review, foreign_review.issues[0])
    record_id = foreign_store.save_disposition(disposition)

    store = ContractRecordStore(tmp_path)
    if reviewer_state == "mismatched":
        store.save_reviewer_result(_review(baseline, result_id="review-foreign", issues=()))
    journal = _read_json(_journal_path(foreign_root, "disposition", record_id))
    journal["state"] = "prepared"
    journal["entry_hash"] = _canonical_hash(
        {key: value for key, value in journal.items() if key != "entry_hash"}
    )
    target_journal = _journal_path(tmp_path, "disposition", record_id)
    _write_json(target_journal, journal)
    target_record = _record_path(tmp_path, "dispositions", record_id)

    with pytest.raises(ContractRecordStoreError):
        store.recover()

    assert not _io_path(target_record).exists()
    persisted_journal = _read_json(target_journal)
    assert persisted_journal["state"] == "prepared"


def test_recover_rebuilds_missing_prepared_reviewer_before_its_prepared_disposition(
    tmp_path: Path,
):
    source_root = tmp_path / "source"
    source = ContractRecordStore(source_root)
    _, _, review, disposition, record_ids = _seed(source)
    review_id, disposition_id = record_ids[2:]

    target_root = tmp_path / "target"
    target = ContractRecordStore(target_root)
    review_journal = _install_prepared_journal(
        source_root, target_root, "reviewer_result", review_id
    )
    disposition_journal = _install_prepared_journal(
        source_root, target_root, "disposition", disposition_id
    )

    target.recover()

    assert target.load_reviewer_result(review_id) == review
    assert target.load_disposition(disposition_id) == disposition
    assert _read_json(review_journal)["state"] == "committed"
    assert _read_json(disposition_journal)["state"] == "committed"


def test_recover_never_materializes_a_disposition_after_recovering_a_mismatched_reviewer(
    tmp_path: Path,
):
    baseline = _baseline()
    expected_root = tmp_path / "expected"
    expected = ContractRecordStore(expected_root)
    expected_review = _review(baseline, result_id="review-shared")
    expected_review_id = expected.save_reviewer_result(expected_review)
    disposition = _disposition(expected_review, expected_review.issues[0])
    disposition_id = expected.save_disposition(disposition)

    mismatched_root = tmp_path / "mismatched"
    mismatched = ContractRecordStore(mismatched_root)
    mismatched_review = _review(
        baseline,
        result_id="review-shared",
        issues=(),
    )
    mismatched_review_id = mismatched.save_reviewer_result(mismatched_review)

    target_root = tmp_path / "target"
    target = ContractRecordStore(target_root)
    _install_prepared_journal(
        mismatched_root, target_root, "reviewer_result", mismatched_review_id
    )
    disposition_journal = _install_prepared_journal(
        expected_root, target_root, "disposition", disposition_id
    )

    with pytest.raises(ContractRecordStoreError, match="binding"):
        target.recover()

    assert _record_path(target_root, "reviews", mismatched_review_id).is_file()
    assert _read_json(
        _journal_path(target_root, "reviewer_result", mismatched_review_id)
    )["state"] == "committed"
    assert not _record_path(target_root, "dispositions", disposition_id).exists()
    assert _read_json(disposition_journal)["state"] == "prepared"
    assert expected_review_id != mismatched_review_id


def test_lock_file_symlink_is_rejected_without_following_or_changing_its_target(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    outside = tmp_path / "outside-lock-target"
    outside.write_bytes(b"outside-sentinel")
    lock_path = _record_root(tmp_path) / "journal" / ".contract-records.lock"
    try:
        lock_path.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlink unavailable: {error}")

    with pytest.raises(ContractRecordStoreError):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, _baseline())

    assert outside.read_bytes() == b"outside-sentinel"
    assert tuple((_record_root(tmp_path) / "journal").glob("*.json")) == ()


def test_lock_file_reparse_detection_is_enforced_when_symlink_creation_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    if os.name != "nt":
        pytest.skip("Windows reparse simulation")
    import creative_os.domains.contract_record_filesystem as filesystem_module

    store = ContractRecordStore(tmp_path)
    lock_path = _record_root(tmp_path) / "journal" / ".contract-records.lock"
    lock_path.write_bytes(b"sentinel")
    original = filesystem_module._win_handle_information

    def report_reparse(handle: int):
        info = original(handle)
        if not info.dwFileAttributes & 0x10 and info.nFileSizeLow == len(b"sentinel"):
            info.dwFileAttributes |= 0x400
        return info

    monkeypatch.setattr(filesystem_module, "_win_handle_information", report_reparse)

    with pytest.raises(ContractRecordStoreError):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, _baseline())

    assert lock_path.read_bytes() == b"sentinel"


def test_lock_file_directory_is_rejected_before_open(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    lock_path = _record_root(tmp_path) / "journal" / ".contract-records.lock"
    lock_path.mkdir()

    with pytest.raises(ContractRecordStoreError, match="regular file"):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, _baseline())


@pytest.mark.parametrize(
    "relative_ancestor",
    (
        Path(".creative_os"),
        Path(".creative_os/memory"),
        Path(".creative_os/memory/contract_records"),
        Path(".creative_os/memory/contract_records/baselines"),
    ),
    ids=("metadata", "memory", "records", "record-type"),
)
def test_every_store_ancestor_reparse_is_rejected_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_ancestor: Path,
):
    if os.name != "nt":
        pytest.skip("Windows reparse simulation")
    import creative_os.domains.contract_record_filesystem as filesystem_module

    store = ContractRecordStore(tmp_path)
    marked = (tmp_path / relative_ancestor).absolute()
    outside = tmp_path / "outside-sentinel"
    outside.write_bytes(b"unchanged")
    marked_handle = store._filesystem._directory_handles[marked]
    original = filesystem_module._win_handle_information
    marked_info = original(marked_handle)
    marked_identity = (
        marked_info.dwVolumeSerialNumber,
        (marked_info.nFileIndexHigh << 32) | marked_info.nFileIndexLow,
    )

    def report_reparse(handle: int):
        info = original(handle)
        identity = (
            info.dwVolumeSerialNumber,
            (info.nFileIndexHigh << 32) | info.nFileIndexLow,
        )
        if identity == marked_identity:
            info.dwFileAttributes |= 0x400
        return info

    monkeypatch.setattr(filesystem_module, "_win_handle_information", report_reparse)

    with pytest.raises(ContractRecordStoreError, match="link|reparse"):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, _baseline())

    root = _record_root(tmp_path)
    assert tuple((root / "baselines").glob("*.json")) == ()
    assert tuple((root / "journal").glob("*.json")) == ()
    assert outside.read_bytes() == b"unchanged"


def test_existing_store_fails_closed_when_a_parent_directory_is_replaced(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    records = _record_root(tmp_path)
    backup = tmp_path / "contract-records-backup"
    if os.name == "nt":
        with pytest.raises(PermissionError):
            records.replace(backup)
        assert records.is_dir()
        assert not backup.exists()
        return
    records.replace(backup)
    for directory in ("baselines", "approvals", "reviews", "dispositions", "journal"):
        (records / directory).mkdir(parents=True, exist_ok=True)
    sentinel = backup / "authority-sentinel"
    sentinel.write_bytes(b"original-authority")

    with pytest.raises(ContractRecordStoreError, match="changed|trust"):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, _baseline())

    assert tuple(records.rglob("*.json")) == ()
    assert sentinel.read_bytes() == b"original-authority"


def test_existing_store_rejects_an_actual_symlinked_store_ancestor_without_writing_outside(
    tmp_path: Path,
):
    store = ContractRecordStore(tmp_path)
    memory = tmp_path / ".creative_os" / "memory"
    backup = tmp_path / "memory-backup"
    if os.name == "nt":
        with pytest.raises(PermissionError):
            memory.replace(backup)
        assert memory.is_dir()
        assert not backup.exists()
        return
    memory.replace(backup)
    outside = tmp_path / "outside-memory"
    outside.mkdir()
    try:
        memory.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink unavailable: {error}")

    with pytest.raises(ContractRecordStoreError, match="link|reparse"):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, _baseline())

    assert tuple(outside.rglob("*")) == ()
    assert (backup / "contract_records" / "baselines").is_dir()


def test_parent_replacement_injected_after_validation_never_redirects_a_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import creative_os.domains.contract_record_store as record_store_module

    store = ContractRecordStore(tmp_path)
    journal = _record_root(tmp_path) / "journal"
    backup = tmp_path / "journal-backup"
    outside = tmp_path / "outside-journal"
    outside.mkdir()
    injected = False

    def replace_parent(event: str, path: Path) -> None:
        nonlocal injected
        if injected or event != "before_temp_create" or path.parent != journal:
            return
        injected = True
        journal.replace(backup)
        journal.symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(record_store_module, "_IO_TEST_HOOK", replace_parent, raising=False)

    with pytest.raises(ContractRecordStoreError):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, _baseline())

    assert injected
    assert tuple(outside.iterdir()) == ()


def test_file_replacement_injected_before_open_is_not_followed_or_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import creative_os.domains.contract_record_store as record_store_module

    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    record_id = store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    record_path = _record_path(tmp_path, "baselines", record_id)
    backup = tmp_path / "baseline-record-backup.json"
    outside = tmp_path / "outside-authority.json"
    outside.write_bytes(record_path.read_bytes())
    injected = False

    def replace_file(event: str, path: Path) -> None:
        nonlocal injected
        if injected or event != "before_file_open" or path != record_path:
            return
        injected = True
        path.replace(backup)
        os.link(outside, path)

    monkeypatch.setattr(record_store_module, "_IO_TEST_HOOK", replace_file, raising=False)

    with pytest.raises(ContractRecordStoreError):
        store.load_baseline(record_id)

    assert injected
    assert outside.read_bytes() == backup.read_bytes()


def test_journal_replacement_injected_before_commit_is_never_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import creative_os.domains.contract_record_store as record_store_module

    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    record_id = f"baseline-{CONTRACT_ID}-v0002-{baseline.fingerprint}"
    journal_path = _journal_path(tmp_path, "baseline", record_id)
    backup = tmp_path / "prepared-journal-backup.json"
    outside = tmp_path / "outside-journal.json"
    injected = False

    def replace_journal(event: str, path: Path) -> None:
        nonlocal injected
        if injected or event != "before_atomic_publish" or path != journal_path:
            return
        if not path.exists():
            return
        injected = True
        outside.write_bytes(path.read_bytes())
        path.replace(backup)
        os.link(outside, path)

    monkeypatch.setattr(record_store_module, "_IO_TEST_HOOK", replace_journal, raising=False)

    with pytest.raises(ContractRecordStoreError):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)

    assert injected
    assert outside.read_bytes() == backup.read_bytes()


def test_lock_replacement_injected_before_open_cannot_create_a_second_lock_inode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import creative_os.domains.contract_record_store as record_store_module

    store = ContractRecordStore(tmp_path)
    lock_path = _record_root(tmp_path) / "journal" / ".contract-records.lock"
    outside = tmp_path / "outside-lock-sentinel"
    outside.write_bytes(b"unchanged")
    injected = False

    def replace_lock(event: str, path: Path) -> None:
        nonlocal injected
        if injected or event != "before_lock_open" or path != lock_path:
            return
        injected = True
        path.mkdir()

    monkeypatch.setattr(record_store_module, "_IO_TEST_HOOK", replace_lock, raising=False)

    with pytest.raises(ContractRecordStoreError):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, _baseline())

    assert injected
    assert outside.read_bytes() == b"unchanged"
    assert tuple((_record_root(tmp_path) / "journal").glob("*.json")) == ()


def test_scan_rejects_an_entry_injected_after_handle_based_enumeration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import creative_os.domains.contract_record_store as record_store_module

    store = ContractRecordStore(tmp_path)
    baselines = _record_root(tmp_path) / "baselines"
    outside = tmp_path / "outside-scan-target"
    outside.write_bytes(b"unchanged")
    injected = False

    def inject_entry(event: str, path: Path) -> None:
        nonlocal injected
        if injected or event != "after_scan" or path != baselines:
            return
        injected = True
        os.link(outside, baselines / ".record-aaaaaaaa.tmp")

    monkeypatch.setattr(record_store_module, "_IO_TEST_HOOK", inject_entry, raising=False)

    with pytest.raises(ContractRecordStoreError, match="scan|changed"):
        store.recover()

    assert injected
    assert outside.read_bytes() == b"unchanged"


@pytest.mark.parametrize("malicious_kind", ("wrong-name", "directory", "symlink"))
def test_recover_rejects_malicious_paths_disguised_as_atomic_temps(
    tmp_path: Path,
    malicious_kind: str,
):
    store = ContractRecordStore(tmp_path)
    records = _record_root(tmp_path) / "baselines"
    malicious = records / (
        ".evil.tmp" if malicious_kind == "wrong-name" else ".record-aaaaaaaa.tmp"
    )
    if malicious_kind == "directory":
        malicious.mkdir()
    elif malicious_kind == "symlink":
        target = tmp_path / "outside-temp-target"
        target.write_text("sentinel", encoding="utf-8")
        try:
            malicious.symlink_to(target)
        except OSError as error:
            pytest.skip(f"symlink unavailable: {error}")
    else:
        malicious.write_text("not an atomic temp", encoding="utf-8")

    with pytest.raises(ContractRecordStoreError):
        store.recover()


def test_recover_ignores_only_a_regular_implementation_named_atomic_temp(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    temporary = _record_root(tmp_path) / "baselines" / ".record-aaaaaaaa.tmp"
    temporary.write_text("incomplete", encoding="utf-8")

    store.recover()

    assert temporary.read_text(encoding="utf-8") == "incomplete"


def test_recover_checks_reparse_type_before_ignoring_an_atomic_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    if os.name != "nt":
        pytest.skip("Windows reparse simulation")
    import creative_os.domains.contract_record_filesystem as filesystem_module

    store = ContractRecordStore(tmp_path)
    temporary = _record_root(tmp_path) / "baselines" / ".record-aaaaaaaa.tmp"
    temporary.write_text("sentinel", encoding="utf-8")
    original = filesystem_module._win_handle_information

    def report_reparse(handle: int):
        info = original(handle)
        if not info.dwFileAttributes & 0x10 and info.nFileSizeLow == len(b"sentinel"):
            info.dwFileAttributes |= 0x400
        return info

    monkeypatch.setattr(filesystem_module, "_win_handle_information", report_reparse)

    with pytest.raises(ContractRecordStoreError):
        store.recover()


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
    import creative_os.domains.contract_record_filesystem as filesystem_module

    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    original = filesystem_module.TrustedStoreFilesystem.atomic_write_bytes
    calls = 0

    def fail_once(filesystem, path, payload, *, expected):
        nonlocal calls
        calls += 1
        if calls == fail_call and not write_before_failure:
            raise OSError("simulated crash")
        original(filesystem, path, payload, expected=expected)
        if calls == fail_call and write_before_failure:
            raise OSError("simulated crash")

    monkeypatch.setattr(filesystem_module.TrustedStoreFilesystem, "atomic_write_bytes", fail_once)
    with pytest.raises(ContractRecordStoreError):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    monkeypatch.setattr(
        filesystem_module.TrustedStoreFilesystem,
        "atomic_write_bytes",
        original,
    )

    restarted = ContractRecordStore(tmp_path)
    restarted.recover()
    record_id = f"baseline-{CONTRACT_ID}-v0002-{baseline.fingerprint}"
    if recovered:
        assert restarted.load_baseline(record_id) == baseline
    else:
        with pytest.raises(KeyError):
            restarted.load_baseline(record_id)


def test_recover_never_overwrites_a_different_valid_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import creative_os.domains.contract_record_filesystem as filesystem_module

    store = ContractRecordStore(tmp_path)
    baseline = _baseline()
    store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    approval = _approval(baseline)
    original = filesystem_module.TrustedStoreFilesystem.atomic_write_bytes
    calls = 0

    def stop_before_record(filesystem, path, payload, *, expected):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated crash")
        original(filesystem, path, payload, expected=expected)

    monkeypatch.setattr(
        filesystem_module.TrustedStoreFilesystem,
        "atomic_write_bytes",
        stop_before_record,
    )
    with pytest.raises(ContractRecordStoreError):
        store.save_approval(approval)
    monkeypatch.setattr(
        filesystem_module.TrustedStoreFilesystem,
        "atomic_write_bytes",
        original,
    )

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


def test_multiple_store_instances_share_file_lock_serialization(tmp_path: Path):
    first = ContractRecordStore(tmp_path)
    second = ContractRecordStore(tmp_path)
    baseline = _baseline()
    first.save_baseline(CONTRACT_ID, CONTRACT_VERSION, baseline)
    approval = _approval(baseline)
    stores = (first, second) * 8

    with ThreadPoolExecutor(max_workers=8) as pool:
        record_ids = tuple(pool.map(lambda store: store.save_approval(approval), stores))

    assert len(set(record_ids)) == 1
    assert first.load_approval(record_ids[0]) == approval


@pytest.mark.parametrize(
    ("reasons", "expected_statuses"),
    (
        (("同一裁决", "同一裁决"), ("saved", "saved")),
        (("裁决甲", "裁决乙"), ("conflict", "saved")),
    ),
    ids=("same-content", "different-content"),
)
def test_independent_processes_use_the_os_lock_for_deterministic_writes(
    tmp_path: Path,
    reasons: tuple[str, str],
    expected_statuses: tuple[str, str],
):
    store = ContractRecordStore(tmp_path)
    store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, _baseline())
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    processes = tuple(
        context.Process(
            target=_process_save_approval,
            args=(str(tmp_path), reason, start_event, result_queue),
        )
        for reason in reasons
    )

    for process in processes:
        process.start()
    start_event.set()
    outcomes = tuple(result_queue.get(timeout=20) for _ in processes)
    for process in processes:
        process.join(timeout=20)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            pytest.fail("contract record writer process hung")

    assert tuple(process.exitcode for process in processes) == (0, 0)
    assert tuple(sorted(status for status, _ in outcomes)) == expected_statuses
    if reasons[0] == reasons[1]:
        assert len({record_id for _, record_id in outcomes}) == 1
    else:
        approval_id = next(value for status, value in outcomes if status == "saved")
        persisted = ContractRecordStore(tmp_path).load_approval(approval_id)
        assert persisted.full_contract.reason in reasons
