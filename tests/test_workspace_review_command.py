from __future__ import annotations

import json
from http.client import HTTPConnection
from threading import Thread

from creative_os.web_workspace import WorkspaceWebAdapter, create_server
from creative_os.workspace import (
    CommandBoundary,
    CommandError,
    CommandResult,
    CommandStatus,
    FileCommandResultStore,
    ProjectionSection,
    WorkspaceQueryAdapter,
)
from creative_os.workspace_command_adapter import (
    WorkspaceCommandAdapter,
    WorkspaceReviewIssueCommandHandler,
    WorkspaceReviewIssueProjectionRefreshScheduler,
)
from creative_os.workspace_refresh import RefreshReceipt, RefreshResult, RefreshStatus
from creative_os.domains.contract_issue import EvidenceCheck
from creative_os.domains.contract_review import ReviewIssue
from tests.test_review_issue_command import _review, _store
from tests.test_web_workspace import Reader


class CommandStub:
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.result


def _request() -> dict[str, object]:
    return {
        "command_id": "accept_review_issue",
        "request_id": "request-accept-1",
        "actor": "editor-1",
        "target": {"project_id": "p", "issue_id": "issue-1"},
        "payload": {
            "reason": "主编确认当前缺口可接受",
            "reviewer_result_id": "review-1",
            "reviewer_result_hash": "a" * 64,
            "expected_version": 1,
        },
        "expected_version": None,
        "idempotency_key": "accept-key-1",
    }


def _post(server, body: object):
    connection = HTTPConnection(*server.server_address)
    encoded = json.dumps(body).encode("utf-8")
    connection.request(
        "POST",
        "/api/commands/accept-review-issue",
        body=encoded,
        headers={"Content-Type": "application/json", "Content-Length": str(len(encoded))},
    )
    return connection.getresponse()


def _domain_request(review, *, reason: str = "主编确认当前缺口可接受", status: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "reason": reason,
        "reviewer_result_id": review.result_id,
        "reviewer_result_hash": review.result_hash,
        "expected_version": review.contract_version,
    }
    if status is not None:
        payload["status"] = status
    return {
        "command_id": "accept_review_issue",
        "request_id": "request-domain-1",
        "actor": "editor-1",
        "target": {"project_id": review.contract_id, "issue_id": review.issues[0].issue_id},
        "payload": payload,
        "expected_version": None,
        "idempotency_key": "domain-accept-key-1",
    }


class ReviewCoordinator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, set[ProjectionSection], str | None]] = []

    def refresh(self, project_id: str, sections: set[ProjectionSection], trace_id: str | None = None):
        self.calls.append((project_id, sections, trace_id))
        receipt = RefreshReceipt("refresh-review-1", project_id, ("project",), "snapshot-review-1", trace_id or "trace-fallback")
        return RefreshResult("refresh-review-1", RefreshStatus.SUCCEEDED, 1, trace_id=trace_id, receipt=receipt)


def _domain_server(tmp_path, review, events, coordinator):
    store = _store(tmp_path, review)
    handler = WorkspaceReviewIssueCommandHandler(review.contract_id, store, events)
    boundary = CommandBoundary(
        handler,
        version_reader=lambda _target: 0,
        store=FileCommandResultStore(tmp_path),
        refresh_scheduler=WorkspaceReviewIssueProjectionRefreshScheduler(coordinator),
        request_validator=handler.validate,
    )
    return create_server(
        WorkspaceWebAdapter(WorkspaceQueryAdapter(Reader()), review.contract_id),
        review_command_adapter=WorkspaceCommandAdapter(boundary),
        port=0,
    )


def test_accept_review_issue_http_returns_event_trace_and_refresh_receipt():
    result = CommandResult(
        CommandStatus.ACCEPTED,
        "accept_review_issue",
        "request-accept-1",
        audit_ref="audit-request-accept-1",
        trace_id="trace-accept-1",
        emitted_event_refs=("event-accept-1",),
        projection_refresh_id="refresh-accept-1",
    )
    command = CommandStub(result)
    server = create_server(
        WorkspaceWebAdapter(WorkspaceQueryAdapter(Reader()), "p"),
        command_adapter=command,
        port=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = _post(server, _request())
        payload = json.loads(response.read())
        assert response.status == 202
        assert payload["trace_id"] == "trace-accept-1"
        assert payload["emitted_event_refs"] == ["event-accept-1"]
        assert payload["projection_refresh_id"] == "refresh-accept-1"
        assert command.requests[0].target == {"project_id": "p", "issue_id": "issue-1"}
    finally:
        server.shutdown()
        server.server_close()


def test_accept_review_issue_http_maps_conflict_to_409():
    command = CommandStub(
        CommandResult(
            CommandStatus.REJECTED,
            "accept_review_issue",
            "request-accept-1",
            error=CommandError("idempotency_conflict", "幂等键对应不同请求。", False),
        )
    )
    server = create_server(
        WorkspaceWebAdapter(WorkspaceQueryAdapter(Reader()), "p"),
        command_adapter=command,
        port=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert _post(server, _request()).status == 409
    finally:
        server.shutdown()
        server.server_close()


def test_accept_review_issue_http_rejects_resolved_without_event_or_refresh(tmp_path):
    review = _review()
    events: list[object] = []
    coordinator = ReviewCoordinator()
    server = _domain_server(tmp_path, review, events, coordinator)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = _post(server, _domain_request(review, status="resolved"))
        payload = json.loads(response.read())
        assert response.status == 422
        assert payload["error"]["code"] == "status_not_allowed"
        assert events == []
        assert coordinator.calls == []
    finally:
        server.shutdown()
        server.server_close()


def test_accept_review_issue_http_rejects_high_issue_without_event_or_refresh(tmp_path):
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
    events: list[object] = []
    coordinator = ReviewCoordinator()
    server = _domain_server(tmp_path, review, events, coordinator)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = _post(server, _domain_request(review))
        payload = json.loads(response.read())
        assert response.status == 422
        assert payload["error"]["code"] == "reviewer_gate_blocked"
        assert events == []
        assert coordinator.calls == []
    finally:
        server.shutdown()
        server.server_close()


def test_accept_review_issue_http_replays_idempotently_and_does_not_refresh_twice(tmp_path):
    review = _review()
    events: list[object] = []
    coordinator = ReviewCoordinator()
    server = _domain_server(tmp_path, review, events, coordinator)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        first = _post(server, _domain_request(review))
        first_payload = json.loads(first.read())
        second = _post(server, _domain_request(review))
        second_payload = json.loads(second.read())
        assert first.status == second.status == 202
        assert second_payload == first_payload
        assert len(events) == 1
        assert len(coordinator.calls) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_accept_review_issue_http_conflict_does_not_overwrite_event_or_refresh(tmp_path):
    review = _review()
    events: list[object] = []
    coordinator = ReviewCoordinator()
    server = _domain_server(tmp_path, review, events, coordinator)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        first = _post(server, _domain_request(review))
        first.read()
        conflict = _post(server, _domain_request(review, reason="不同的裁决理由"))
        payload = json.loads(conflict.read())
        assert conflict.status == 409
        assert payload["error"]["code"] == "idempotency_conflict"
        assert len(events) == 1
        assert len(coordinator.calls) == 1
    finally:
        server.shutdown()
        server.server_close()
