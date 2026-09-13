from __future__ import annotations

from dataclasses import replace

from creative_os.domains.contract_issue import EvidenceCheck
from creative_os.domains.contract_record_store import ContractRecordStore
from creative_os.domains.contract_review import PrewriteReviewerResult, ReviewIssue
from creative_os.domains.review_issue_command import (
    AcceptReviewIssueCommand,
    accept_review_issue,
)


def _issue() -> ReviewIssue:
    return ReviewIssue.build(
        issue_id="issue-cost",
        code="missing_choice_cost",
        severity="warning",
        blocking=True,
        requires_human_disposition=False,
        field_path="chapter_contract.protagonist_choice.cost",
        evidence_checks=(EvidenceCheck("field_found", False, "未找到选择代价"),),
        repair_hint="补充选择代价或由人工裁决",
    )


def _review() -> PrewriteReviewerResult:
    return PrewriteReviewerResult.build(
        result_id="review-001",
        contract_id="project-a",
        contract_version=3,
        contract_content_hash="a" * 64,
        baseline_fingerprint="b" * 64,
        ruleset_version="prewrite-v1",
        semantic_asset_versions=(("function_semantics", "v1"),),
        issues=(_issue(),),
    )


def _command(review: PrewriteReviewerResult, **overrides: object) -> AcceptReviewIssueCommand:
    values: dict[str, object] = {
        "command_id": "accept_review_issue",
        "request_id": "request-001",
        "actor": "editor-tingyu",
        "target": {"project_id": "project-a", "issue_id": review.issues[0].issue_id},
        "payload": {
            "reason": "主编确认当前缺口可接受",
            "reviewer_result_id": review.result_id,
            "reviewer_result_hash": review.result_hash,
            "expected_version": review.contract_version,
        },
        "idempotency_key": "idem-001",
        "trace_id": "trace-001",
    }
    values.update(overrides)
    return AcceptReviewIssueCommand(**values)


def _store(tmp_path, review: PrewriteReviewerResult) -> ContractRecordStore:
    store = ContractRecordStore(tmp_path)
    store.save_reviewer_result(review)
    return store


def test_accept_review_issue_saves_disposition_and_emits_traceable_event(tmp_path):
    review = _review()
    store = _store(tmp_path, review)
    events: list[object] = []

    outcome = accept_review_issue(_command(review), store, events)

    assert outcome.status == "accepted"
    assert outcome.error is None
    assert outcome.receipt is not None
    assert outcome.receipt.trace_id == "trace-001"
    assert outcome.receipt.disposition_record_id
    assert outcome.receipt.event_id == events[0].event_id
    assert events[0].event_type == "ReviewIssueAccepted"
    assert events[0].project_id == "project-a"
    assert events[0].issue_id == "issue-cost"
    assert events[0].canonical_issue_hash == review.issues[0].canonical_issue_hash
    assert events[0].reviewer_result_hash == review.result_hash
    assert events[0].actor == "editor-tingyu"
    assert events[0].reason == "主编确认当前缺口可接受"
    assert events[0].trace_id == "trace-001"
    assert store.load_disposition(outcome.receipt.disposition_record_id).status == "accepted"


def test_accept_review_issue_rejects_resolved_status_before_writing(tmp_path):
    review = _review()
    store = _store(tmp_path, review)
    events: list[object] = []
    command = _command(review, payload={**_command(review).payload, "status": "resolved"})

    outcome = accept_review_issue(command, store, events)

    assert outcome.status == "rejected"
    assert outcome.error is not None
    assert outcome.error.code == "status_not_allowed"
    assert events == []


def test_accept_review_issue_rejects_top_level_resolved_status_before_writing(tmp_path):
    review = _review()
    store = _store(tmp_path, review)
    events: list[object] = []
    command = replace(_command(review), status="resolved")

    outcome = accept_review_issue(command, store, events)

    assert outcome.status == "rejected"
    assert outcome.error is not None
    assert outcome.error.code == "status_not_allowed"
    assert events == []


def test_accept_review_issue_rejects_missing_reason(tmp_path):
    review = _review()
    store = _store(tmp_path, review)
    command = _command(review, payload={**_command(review).payload, "reason": " "})

    outcome = accept_review_issue(command, store, [])

    assert outcome.status == "rejected"
    assert outcome.error is not None
    assert outcome.error.code == "validation_failed"


def test_accept_review_issue_rejects_wrong_project_binding(tmp_path):
    review = _review()
    store = _store(tmp_path, review)
    command = _command(review, target={"project_id": "project-b", "issue_id": "issue-cost"})

    outcome = accept_review_issue(command, store, [])

    assert outcome.status == "rejected"
    assert outcome.error is not None
    assert outcome.error.code == "reviewer_result_binding_mismatch"


def test_accept_review_issue_rejects_wrong_reviewer_result_hash(tmp_path):
    review = _review()
    store = _store(tmp_path, review)
    command = _command(review, payload={**_command(review).payload, "reviewer_result_hash": "c" * 64})

    outcome = accept_review_issue(command, store, [])

    assert outcome.status == "rejected"
    assert outcome.error is not None
    assert outcome.error.code == "reviewer_result_hash_mismatch"


def test_accept_review_issue_rejects_old_expected_version(tmp_path):
    review = _review()
    store = _store(tmp_path, review)
    command = _command(
        review,
        payload={**_command(review).payload, "expected_version": review.contract_version - 1},
    )

    outcome = accept_review_issue(command, store, [])

    assert outcome.status == "conflict"
    assert outcome.error is not None
    assert outcome.error.code == "version_conflict"


def test_accept_review_issue_replays_same_idempotency_key_without_duplicate_event(tmp_path):
    review = _review()
    store = _store(tmp_path, review)
    events: list[object] = []
    command = _command(review)

    first = accept_review_issue(command, store, events)
    second = accept_review_issue(command, ContractRecordStore(tmp_path), events)

    assert first.status == second.status == "accepted"
    assert second.receipt == first.receipt
    assert len(events) == 1


def test_accept_review_issue_rejects_different_content_with_same_idempotency_key(tmp_path):
    review = _review()
    store = _store(tmp_path, review)
    events: list[object] = []
    accept_review_issue(_command(review), store, events)
    conflicting = _command(
        review,
        payload={**_command(review).payload, "reason": "不同的裁决理由"},
    )

    outcome = accept_review_issue(conflicting, store, events)

    assert outcome.status == "conflict"
    assert outcome.error is not None
    assert outcome.error.code == "idempotency_conflict"
    assert len(events) == 1
