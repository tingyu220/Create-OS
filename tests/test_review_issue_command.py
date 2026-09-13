from __future__ import annotations

from dataclasses import replace

from creative_os.domains.contract_issue import EvidenceCheck
from creative_os.domains.contract_lifecycle import ContractLifecycleCoordinator, ContractPointer
from creative_os.domains.contract_record_store import ContractRecordStore, ContractRecordStoreError
from creative_os.domains.contract_review import PrewriteReviewerResult, ReviewIssue
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_memory import build_narrative_candidate_item
from creative_os.memory.model import MemoryEvidence
from creative_os.domains.review_issue_command import (
    AcceptReviewIssueCommand,
    accept_review_issue,
)
from tests.test_contract_preflight import _candidate
from tests.test_contract_revision import _replacement


_CURRENT_DECISION = _candidate()
_CURRENT_CONTENT_HASH = NarrativeDecisionCodec.content_hash(_CURRENT_DECISION)


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


def _review(
    issue: ReviewIssue | None = None,
    *,
    contract_content_hash: str = _CURRENT_CONTENT_HASH,
    contract_version: int = _CURRENT_DECISION.contract_version,
    issues: tuple[ReviewIssue, ...] | None = None,
) -> PrewriteReviewerResult:
    return PrewriteReviewerResult.build(
        result_id="review-001",
        contract_id=_CURRENT_DECISION.contract_id,
        contract_version=contract_version,
        contract_content_hash=contract_content_hash,
        baseline_fingerprint="b" * 64,
        ruleset_version="prewrite-v1",
        semantic_asset_versions=(("function_semantics", "v1"),),
        issues=issues or (issue or _issue(),),
    )


def _command(review: PrewriteReviewerResult, **overrides: object) -> AcceptReviewIssueCommand:
    values: dict[str, object] = {
        "command_id": "accept_review_issue",
        "request_id": "request-001",
        "actor": "editor-tingyu",
        "target": {"project_id": review.contract_id, "issue_id": review.issues[0].issue_id},
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
    lifecycle = ContractLifecycleCoordinator(tmp_path)
    item = build_narrative_candidate_item(
        tmp_path,
        _CURRENT_DECISION,
        evidence=(MemoryEvidence("test", "current"),),
        item_id=f"{_CURRENT_DECISION.contract_id}-v{_CURRENT_DECISION.contract_version:04d}",
    ).activate(actor="editor")
    lifecycle.store.add_immutable(item)
    lifecycle.write_pointer(
        ContractPointer.build(
            physical_key=item.id,
            contract_version=review.contract_version,
            content_hash=_CURRENT_CONTENT_HASH,
            baseline_fingerprint=review.baseline_fingerprint,
            approval_record_id="approval-1",
            approval_record_hash="c" * 64,
            reviewer_result_id=review.result_id,
            reviewer_result_hash=review.result_hash,
            ruleset_version=review.ruleset_version,
            semantic_asset_versions=review.semantic_asset_versions,
            disposition_set_hash="d" * 64,
        )
    )
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
    assert events[0].project_id == review.contract_id
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


def test_accept_review_issue_rejects_high_issue_with_authoritative_gate(tmp_path):
    high_issue = ReviewIssue.build(
        issue_id="issue-high",
        code="missing_required_fact",
        severity="high",
        blocking=True,
        requires_human_disposition=False,
        field_path="chapter_contract.required_fact",
        evidence_checks=(EvidenceCheck("field_found", False, "未找到必要事实"),),
        repair_hint="补充必要事实",
    )
    review = _review(high_issue)
    store = _store(tmp_path, review)

    outcome = accept_review_issue(_command(review, target={"project_id": review.contract_id, "issue_id": "issue-high"}), store, [])

    assert outcome.status == "rejected"
    assert outcome.error is not None
    assert outcome.error.code == "reviewer_gate_blocked"


def test_accept_review_issue_rejects_same_version_reviewer_after_contract_content_changes(tmp_path):
    review = _review(contract_content_hash="e" * 64)
    store = _store(tmp_path, review)

    outcome = accept_review_issue(_command(review), store, [])

    assert outcome.status == "rejected"
    assert outcome.error is not None
    assert outcome.error.code == "current_contract_binding_mismatch"


def test_accept_review_issue_rejects_reviewer_from_old_pointer_after_contract_switch(tmp_path):
    review = _review()
    store = _store(tmp_path, review)
    lifecycle = ContractLifecycleCoordinator(tmp_path)
    replacement = _replacement(_CURRENT_DECISION)
    item = build_narrative_candidate_item(
        tmp_path,
        replacement,
        evidence=(MemoryEvidence("test", "replacement"),),
        item_id=f"{replacement.contract_id}-v{replacement.contract_version:04d}",
    ).activate(actor="editor")
    lifecycle.store.add_immutable(item)
    lifecycle.write_pointer(
        ContractPointer.build(
            physical_key=item.id,
            contract_version=replacement.contract_version,
            content_hash=NarrativeDecisionCodec.content_hash(replacement),
            baseline_fingerprint="f" * 64,
            approval_record_id="approval-3",
            approval_record_hash="a" * 64,
            reviewer_result_id=review.result_id,
            reviewer_result_hash=review.result_hash,
            ruleset_version=review.ruleset_version,
            semantic_asset_versions=review.semantic_asset_versions,
            disposition_set_hash="b" * 64,
        )
    )

    outcome = accept_review_issue(_command(review), store, [])

    assert outcome.status == "rejected"
    assert outcome.error is not None
    assert outcome.error.code == "current_contract_binding_mismatch"


def test_accept_review_issue_accepts_multiple_warning_issues_one_at_a_time(tmp_path):
    first_issue = _issue()
    second_issue = ReviewIssue.build(
        issue_id="issue-consequence",
        code="missing_choice_consequence",
        severity="warning",
        blocking=True,
        requires_human_disposition=False,
        field_path="chapter_contract.protagonist_choice.consequence",
        evidence_checks=(EvidenceCheck("field_found", False, "未找到选择后果"),),
        repair_hint="补充选择后果或由人工裁决",
    )
    review = _review(issues=(first_issue, second_issue))
    store = _store(tmp_path, review)
    first = accept_review_issue(_command(review), store, [])
    second_command = _command(
        review,
        target={"project_id": review.contract_id, "issue_id": second_issue.issue_id},
        payload={**_command(review).payload, "reason": "第二条缺口也已由主编确认可接受"},
        idempotency_key="idem-002",
        trace_id="trace-002",
    )

    second = accept_review_issue(second_command, store, [])

    assert first.status == "accepted"
    assert second.status == "accepted"
    assert len(store.find_dispositions(review.result_id, review.result_hash)) == 2


def test_accept_review_issue_retries_partial_sink_with_same_event_id(tmp_path):
    review = _review()
    store = _store(tmp_path, review)

    class _PartialSink:
        def __init__(self):
            self.events: list[object] = []
            self.fail_once = True

        def append(self, event):
            self.events.append(event)
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError("sink disconnected after append")

    sink = _PartialSink()
    first = accept_review_issue(_command(review), store, sink)
    pending = store.load_command_receipt("idem-001")
    second = accept_review_issue(_command(review), ContractRecordStore(tmp_path), sink)

    assert first.status == "failed"
    assert pending is not None and pending[2] == "pending"
    assert second.status == "accepted"
    assert len(sink.events) == 2
    assert sink.events[0].event_id == sink.events[1].event_id == second.event_id


def test_accept_review_issue_retries_when_receipt_save_fails_before_event(tmp_path, monkeypatch):
    review = _review()
    store = _store(tmp_path, review)
    original = store.save_command_receipt
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ContractRecordStoreError("receipt store unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "save_command_receipt", fail_once)
    events: list[object] = []

    first = accept_review_issue(_command(review), store, events)
    second = accept_review_issue(_command(review), store, events)

    assert first.status == "failed"
    assert second.status == "accepted"
    assert len(events) == 1


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
