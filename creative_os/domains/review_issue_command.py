from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
from typing import Any, Protocol

from creative_os.domains.contract_record_store import (
    ContractRecordConflictError,
    ContractRecordStore,
    ContractRecordStoreError,
)
from creative_os.domains.contract_lifecycle import ContractLifecycleCoordinator
from creative_os.domains.contract_review import (
    PrewriteReviewerResult,
    ReviewIssueDisposition,
    validate_reviewer_gate,
)


class CommandStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CONFLICT = "conflict"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AcceptReviewIssueCommand:
    """人工接受一条审阅问题的领域命令。"""

    command_id: str
    request_id: str
    actor: str
    target: Mapping[str, object]
    payload: Mapping[str, object]
    idempotency_key: str
    trace_id: str
    status: str = "accepted"


@dataclass(frozen=True, slots=True)
class CommandError:
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    command_id: str
    request_id: str
    idempotency_key: str
    fingerprint: str
    audit_ref: str
    trace_id: str
    disposition_record_id: str
    event_id: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "CommandReceipt":
        fields = (
            "command_id", "request_id", "idempotency_key", "fingerprint",
            "audit_ref", "trace_id", "disposition_record_id", "event_id",
        )
        if set(payload) != set(fields) or any(type(payload[field]) is not str or not payload[field] for field in fields):
            raise ValueError("command receipt fields are invalid")
        return cls(**{field: payload[field] for field in fields})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    status: CommandStatus
    command_id: str
    request_id: str
    trace_id: str
    receipt: CommandReceipt | None = None
    error: CommandError | None = None

    @property
    def audit_ref(self) -> str | None:
        return None if self.receipt is None else self.receipt.audit_ref

    @property
    def event_id(self) -> str | None:
        return None if self.receipt is None else self.receipt.event_id


@dataclass(frozen=True, slots=True)
class ReviewIssueAcceptedEvent:
    """已接受审阅问题的领域事件，供后续投影层消费。"""

    event_id: str
    event_type: str
    occurred_at: str
    project_id: str
    issue_id: str
    canonical_issue_hash: str
    reviewer_result_id: str
    reviewer_result_hash: str
    actor: str
    reason: str
    trace_id: str
    disposition_record_id: str


class EventSink(Protocol):
    """至少一次投递；消费者必须按稳定 event_id 去重。"""

    def append(self, event: ReviewIssueAcceptedEvent) -> object: ...


def accept_review_issue(
    command: AcceptReviewIssueCommand,
    store: ContractRecordStore,
    event_sink: EventSink | list[ReviewIssueAcceptedEvent],
) -> CommandOutcome:
    """校验并持久化 accepted 裁决，然后发布一个可追溯领域事件。"""

    try:
        values = _validate_command(command)
    except (TypeError, ValueError) as error:
        return _rejected(command, "validation_failed", str(error))

    target, payload = values
    if command.status != "accepted" or payload.get("status", "accepted") != "accepted":
        return _rejected(command, "status_not_allowed", "当前命令只允许 accepted 状态。")

    try:
        reviewer_result = store.find_reviewer_result(payload["reviewer_result_id"])
    except KeyError:
        return _rejected(command, "reviewer_result_not_found", "审阅结果不存在。")
    except ContractRecordStoreError:
        return _failed(command, "reviewer_result_unavailable", "审阅结果暂时不可读取。", True)

    if reviewer_result is None:
        return _rejected(command, "reviewer_result_not_found", "审阅结果不存在。")
    if not isinstance(reviewer_result, PrewriteReviewerResult):
        return _failed(command, "reviewer_result_invalid", "审阅结果类型无效。")
    if reviewer_result.contract_id != target["project_id"]:
        return _rejected(command, "reviewer_result_binding_mismatch", "审阅结果不属于目标项目。")
    if reviewer_result.result_hash != payload["reviewer_result_hash"]:
        return _rejected(command, "reviewer_result_hash_mismatch", "审阅结果哈希不匹配。")
    try:
        current_pointer = ContractLifecycleCoordinator(store.project_root).read_pointer(
            target["project_id"]
        )
    except Exception:
        return _rejected(command, "current_contract_unavailable", "当前活动合同暂时无法读取。")
    if current_pointer is None:
        return _rejected(command, "current_contract_unavailable", "当前活动合同不存在。")
    if (
        current_pointer.contract_version != reviewer_result.contract_version
        or current_pointer.content_hash != reviewer_result.contract_content_hash
        or current_pointer.baseline_fingerprint != reviewer_result.baseline_fingerprint
        or current_pointer.reviewer_result_id != reviewer_result.result_id
        or current_pointer.reviewer_result_hash != reviewer_result.result_hash
    ):
        return _rejected(command, "current_contract_binding_mismatch", "审阅结果不是当前活动合同的结果。")
    issue = next((item for item in reviewer_result.issues if item.issue_id == target["issue_id"]), None)
    if issue is None:
        return _rejected(command, "review_issue_not_found", "审阅问题不存在。")
    if payload["expected_version"] != reviewer_result.contract_version:
        return _conflict(command, "version_conflict", "目标合同版本已变化。")

    fingerprint = _fingerprint(command)
    try:
        stored = store.load_command_receipt(command.idempotency_key)
    except ContractRecordStoreError:
        return _failed(command, "command_store_unavailable", "命令幂等记录暂时不可读取。", True)
    if stored is not None:
        stored_fingerprint, stored_payload, state = stored
        if stored_fingerprint != fingerprint:
            return _conflict(command, "idempotency_conflict", "幂等键对应不同请求。")
        try:
            receipt = CommandReceipt.from_payload(stored_payload)
        except ValueError:
            return _failed(command, "command_receipt_invalid", "命令幂等记录无效。")
        if state == "completed":
            return CommandOutcome(CommandStatus.ACCEPTED, command.command_id, command.request_id, receipt.trace_id, receipt)
        if state != "pending":
            return _failed(command, "command_receipt_invalid", "命令幂等状态无效。")
        event = _build_event(command, target, payload, reviewer_result, issue, receipt)
        try:
            _emit(event_sink, event)
            store.save_command_receipt(
                command.idempotency_key, fingerprint, asdict(receipt), state="completed",
            )
        except ContractRecordConflictError:
            return _conflict(command, "idempotency_conflict", "幂等键对应不同请求。")
        except ContractRecordStoreError:
            return _failed(command, "command_store_unavailable", "命令幂等记录暂时无法完成。", True)
        except Exception:
            return _failed(command, "event_publish_failed", "审阅事件发布失败，结果需要对账。", False)
        return CommandOutcome(CommandStatus.ACCEPTED, command.command_id, command.request_id, receipt.trace_id, receipt)

    disposition = ReviewIssueDisposition(
        issue_id=issue.issue_id,
        canonical_issue_hash=issue.canonical_issue_hash,
        issue_code=issue.code,
        field_path=issue.field_path,
        evidence_hash=issue.evidence_hash,
        status="accepted",
        reason=payload["reason"],
        actor=command.actor,
        decided_at=datetime.now(timezone.utc).isoformat(),
        reviewer_result_id=reviewer_result.result_id,
        reviewer_result_hash=reviewer_result.result_hash,
    )
    try:
        existing_records = store.find_dispositions(
            reviewer_result.result_id, reviewer_result.result_hash,
        )
    except ContractRecordConflictError:
        return _conflict(command, "reviewer_disposition_conflict", "审阅裁决事实存在冲突。")
    except ContractRecordStoreError:
        return _failed(command, "disposition_lookup_failed", "审阅裁决暂时无法读取。", True)

    existing = tuple(record for _, record in existing_records)
    matching = next((item for item in existing_records if _same_disposition(item[1], disposition)), None)
    gate_dispositions = existing if matching is not None else existing + (disposition,)
    gate = validate_reviewer_gate(
        reviewer_result,
        gate_dispositions,
        contract_id=reviewer_result.contract_id,
        contract_version=reviewer_result.contract_version,
        contract_content_hash=reviewer_result.contract_content_hash,
        baseline_fingerprint=reviewer_result.baseline_fingerprint,
        ruleset_version=reviewer_result.ruleset_version,
        semantic_asset_versions=reviewer_result.semantic_asset_versions,
    )
    if any(code in {"missing_prewrite_review", "stale_prewrite_review"} for code in gate.issue_codes):
        return _rejected(command, "reviewer_result_stale", "审阅结果绑定已失效。")
    if issue.severity == "high":
        return _rejected(command, "reviewer_gate_blocked", "当前审阅结果仍包含不可接受的阻断问题。")

    try:
        disposition_record_id = matching[0] if matching is not None else store.save_disposition(disposition)
    except ContractRecordConflictError:
        return _conflict(command, "disposition_conflict", "审阅裁决事实已存在冲突。")
    except ContractRecordStoreError:
        return _failed(command, "disposition_save_failed", "审阅裁决暂时无法保存。", True)

    event_id = f"event-{fingerprint}"
    receipt = CommandReceipt(
        command_id=command.command_id,
        request_id=command.request_id,
        idempotency_key=command.idempotency_key,
        fingerprint=fingerprint,
        audit_ref=f"audit-{command.request_id}",
        trace_id=command.trace_id,
        disposition_record_id=disposition_record_id,
        event_id=event_id,
    )
    event = _build_event(command, target, payload, reviewer_result, issue, receipt)
    try:
        store.save_command_receipt(
            command.idempotency_key, fingerprint, asdict(receipt), state="pending",
        )
    except ContractRecordConflictError:
        return _conflict(command, "idempotency_conflict", "幂等键对应不同请求。")
    except ContractRecordStoreError:
        return _failed(command, "command_store_unavailable", "命令幂等记录暂时无法保存。", True)
    try:
        _emit(event_sink, event)
    except Exception:
        return _failed(command, "event_publish_failed", "审阅事件发布失败，结果需要对账。", False)
    try:
        store.save_command_receipt(
            command.idempotency_key, fingerprint, asdict(receipt), state="completed",
        )
    except ContractRecordConflictError:
        return _conflict(command, "idempotency_conflict", "幂等键对应不同请求。")
    except ContractRecordStoreError:
        return _failed(command, "command_store_unavailable", "命令幂等记录暂时无法完成。", True)
    return CommandOutcome(CommandStatus.ACCEPTED, command.command_id, command.request_id, command.trace_id, receipt)


def _same_disposition(left: ReviewIssueDisposition, right: ReviewIssueDisposition) -> bool:
    return all(
        getattr(left, field) == getattr(right, field)
        for field in (
            "issue_id", "canonical_issue_hash", "issue_code", "field_path", "evidence_hash",
            "status", "reason", "actor", "reviewer_result_id", "reviewer_result_hash",
        )
    )


def _build_event(
    command: AcceptReviewIssueCommand,
    target: dict[str, str],
    payload: dict[str, object],
    reviewer_result: PrewriteReviewerResult,
    issue,
    receipt: CommandReceipt,
) -> ReviewIssueAcceptedEvent:
    return ReviewIssueAcceptedEvent(
        event_id=receipt.event_id,
        event_type="ReviewIssueAccepted",
        occurred_at=datetime.now(timezone.utc).isoformat(),
        project_id=target["project_id"],
        issue_id=issue.issue_id,
        canonical_issue_hash=issue.canonical_issue_hash,
        reviewer_result_id=reviewer_result.result_id,
        reviewer_result_hash=reviewer_result.result_hash,
        actor=command.actor,
        reason=payload["reason"],
        trace_id=receipt.trace_id,
        disposition_record_id=receipt.disposition_record_id,
    )


def _validate_command(command: AcceptReviewIssueCommand) -> tuple[dict[str, str], dict[str, object]]:
    if not isinstance(command, AcceptReviewIssueCommand):
        raise TypeError("命令类型无效")
    if command.command_id != "accept_review_issue":
        raise ValueError("命令类型不允许")
    for value, name in (
        (command.request_id, "request_id"), (command.actor, "actor"),
        (command.idempotency_key, "idempotency_key"), (command.trace_id, "trace_id"),
    ):
        if type(value) is not str or not value.strip():
            raise ValueError(f"{name} 必须是非空字符串")
    if type(command.status) is not str or not command.status.strip():
        raise ValueError("status 必须是非空字符串")
    if not isinstance(command.target, Mapping) or set(command.target) != {"project_id", "issue_id"}:
        raise ValueError("target 字段必须严格匹配契约")
    target = {name: command.target[name] for name in ("project_id", "issue_id")}
    for value, name in target.items():
        if type(value) is not str or not value.strip():
            raise ValueError(f"target.{name} 必须是非空字符串")
    if not isinstance(command.payload, Mapping):
        raise ValueError("payload 必须是对象")
    allowed = {"reason", "reviewer_result_id", "reviewer_result_hash", "expected_version"}
    if set(command.payload) not in (allowed, allowed | {"status"}):
        raise ValueError("payload 字段必须严格匹配契约")
    payload = dict(command.payload)
    if type(payload["reason"]) is not str or not payload["reason"].strip():
        raise ValueError("reason 必须是非空字符串")
    if type(payload["reviewer_result_id"]) is not str or not payload["reviewer_result_id"].strip():
        raise ValueError("reviewer_result_id 必须是非空字符串")
    if type(payload["reviewer_result_hash"]) is not str or not _is_sha256(payload["reviewer_result_hash"]):
        raise ValueError("reviewer_result_hash 必须是小写 sha256")
    if type(payload["expected_version"]) is not int or payload["expected_version"] < 1:
        raise ValueError("expected_version 必须是正整数")
    if "status" in payload and type(payload["status"]) is not str:
        raise ValueError("status 必须是字符串")
    return target, payload


def _fingerprint(command: AcceptReviewIssueCommand) -> str:
    payload = {
        "command_id": command.command_id,
        "request_id": command.request_id,
        "actor": command.actor,
        "target": dict(command.target),
        "payload": dict(command.payload),
        "idempotency_key": command.idempotency_key,
        "trace_id": command.trace_id,
        "status": command.status,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _emit(event_sink: EventSink | list[ReviewIssueAcceptedEvent], event: ReviewIssueAcceptedEvent) -> None:
    if hasattr(event_sink, "append"):
        event_sink.append(event)  # type: ignore[union-attr]
    else:
        event_sink(event)  # type: ignore[operator]


def _rejected(command: AcceptReviewIssueCommand, code: str, message: str) -> CommandOutcome:
    return CommandOutcome(CommandStatus.REJECTED, command.command_id, command.request_id, command.trace_id,
                          error=CommandError(code, message))


def _conflict(command: AcceptReviewIssueCommand, code: str, message: str) -> CommandOutcome:
    return CommandOutcome(CommandStatus.CONFLICT, command.command_id, command.request_id, command.trace_id,
                          error=CommandError(code, message))


def _failed(command: AcceptReviewIssueCommand, code: str, message: str, retryable: bool = False) -> CommandOutcome:
    return CommandOutcome(CommandStatus.FAILED, command.command_id, command.request_id, command.trace_id,
                          error=CommandError(code, message, retryable))
