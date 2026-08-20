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
    _io_path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _copy_file(source: Path, target: Path) -> None:
    _io_path(target).write_bytes(_io_path(source).read_bytes())


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
    import creative_os.domains.contract_record_store as record_store_module

    store = ContractRecordStore(tmp_path)
    lock_path = _record_root(tmp_path) / "journal" / ".contract-records.lock"
    lock_path.write_bytes(b"sentinel")
    monkeypatch.setattr(
        record_store_module,
        "_path_is_link_or_reparse",
        lambda path: Path(path).name == ".contract-records.lock",
        raising=False,
    )

    with pytest.raises(ContractRecordStoreError):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, _baseline())

    assert lock_path.read_bytes() == b"sentinel"


def test_lock_file_directory_is_rejected_before_open(tmp_path: Path):
    store = ContractRecordStore(tmp_path)
    lock_path = _record_root(tmp_path) / "journal" / ".contract-records.lock"
    lock_path.mkdir()

    with pytest.raises(ContractRecordStoreError, match="regular file"):
        store.save_baseline(CONTRACT_ID, CONTRACT_VERSION, _baseline())


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
    import creative_os.domains.contract_record_store as record_store_module

    store = ContractRecordStore(tmp_path)
    temporary = _record_root(tmp_path) / "baselines" / ".record-aaaaaaaa.tmp"
    temporary.write_text("sentinel", encoding="utf-8")
    monkeypatch.setattr(
        record_store_module,
        "_path_is_link_or_reparse",
        lambda path: Path(path).name == temporary.name,
        raising=False,
    )

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
