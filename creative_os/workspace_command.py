from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
from typing import Callable, Mapping, Protocol
from uuid import uuid4

SCHEMA_VERSION = 1

class CommandStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"

class CommandRecordState(StrEnum):
    RESERVED = "reserved"
    COMPLETED = "completed"

class ReserveStatus(StrEnum):
    ACQUIRED = "acquired"
    RESERVED = "reserved"
    COMPLETED = "completed"
    CONFLICT = "conflict"

@dataclass(frozen=True, slots=True)
class CommandRequest:
    command_id: str
    request_id: str
    actor: str
    target: str
    payload: Mapping[str, object]
    expected_version: int | None = None
    idempotency_key: str = ""
    request_fingerprint: str = ""

@dataclass(frozen=True, slots=True)
class CommandError:
    code: str
    message: str
    retryable: bool

@dataclass(frozen=True, slots=True)
class CommandResult:
    status: CommandStatus
    command_id: str
    request_id: str
    error: CommandError | None = None
    audit_ref: str | None = None
    trace_id: str | None = None
    emitted_event_refs: tuple[str, ...] = ()
    projection_refresh_id: str | None = None

@dataclass(frozen=True, slots=True)
class CommandResultRecord:
    fingerprint: str
    state: CommandRecordState
    result: CommandResult | None = None

    def __post_init__(self) -> None:
        if self.state is CommandRecordState.RESERVED and self.result is not None:
            raise ValueError("reserved_command_must_not_have_result")
        if self.state is CommandRecordState.COMPLETED and self.result is None:
            raise ValueError("completed_command_result_required")

@dataclass(frozen=True, slots=True)
class ReserveOutcome:
    status: ReserveStatus
    record: CommandResultRecord | None = None

class CommandStoreError(RuntimeError):
    pass


class CommandRejectedError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

class CommandResultStore(Protocol):
    def read(self, key: str) -> CommandResultRecord | None: ...
    def reserve(self, key: str, fingerprint: str) -> ReserveOutcome: ...
    def complete(self, key: str, fingerprint: str, result: CommandResult) -> None: ...
    def release(self, key: str, fingerprint: str) -> None: ...

class FileCommandResultStore:
    def __init__(self, root: str | Path, *, lock_attempts: int = 100) -> None:
        self.path = Path(root) / ".creative_os" / "commands" / "results.json"
        self.lock_path = self.path.with_suffix(".lock")
        self.lock_attempts = lock_attempts
        if lock_attempts < 1:
            raise ValueError("command_store_lock_attempts_invalid")
        self._read_records()

    def read(self, key: str) -> CommandResultRecord | None:
        return self._read_records().get(key)

    def reserve(self, key: str, fingerprint: str) -> ReserveOutcome:
        handle = self._acquire_lock()
        try:
            records = self._read_records()
            existing = records.get(key)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    return ReserveOutcome(ReserveStatus.CONFLICT, existing)
                state = ReserveStatus.COMPLETED if existing.result else ReserveStatus.RESERVED
                return ReserveOutcome(state, existing)
            record = CommandResultRecord(fingerprint, CommandRecordState.RESERVED)
            records[key] = record
            self._write_records(records)
            return ReserveOutcome(ReserveStatus.ACQUIRED, record)
        finally:
            self._release_lock(handle)

    def complete(self, key: str, fingerprint: str, result: CommandResult) -> None:
        handle = self._acquire_lock()
        try:
            records = self._read_records()
            existing = records.get(key)
            if existing is None or existing.fingerprint != fingerprint:
                raise CommandStoreError("command_reservation_missing_or_conflicting")
            completed = CommandResultRecord(fingerprint, CommandRecordState.COMPLETED, result)
            if existing.state is CommandRecordState.COMPLETED:
                if existing != completed:
                    raise CommandStoreError("command_completed_result_conflict")
                return
            records[key] = completed
            self._write_records(records)
        finally:
            self._release_lock(handle)

    def release(self, key: str, fingerprint: str) -> None:
        handle = self._acquire_lock()
        try:
            records = self._read_records()
            existing = records.get(key)
            if existing is None:
                return
            if existing.fingerprint != fingerprint or existing.state is not CommandRecordState.RESERVED:
                raise CommandStoreError("command_reservation_release_conflict")
            del records[key]
            self._write_records(records)
        finally:
            self._release_lock(handle)

    def _read_records(self) -> dict[str, CommandResultRecord]:
        if not self.path.is_file():
            return {}
        try:
            return _decode_store(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise CommandStoreError("command_store_corrupt") from error

    def _write_records(self, records: dict[str, CommandResultRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(_encode_store(records), stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.path)

    def _acquire_lock(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(self.lock_attempts):
            try:
                return os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                continue
        raise CommandStoreError("command_store_busy")

    def _release_lock(self, handle: int) -> None:
        os.close(handle)
        try:
            os.remove(self.lock_path)
        except FileNotFoundError:
            pass

class CommandHandler(Protocol):
    def __call__(self, request: CommandRequest) -> tuple[str, ...]: ...

class ProjectionRefreshScheduler(Protocol):
    def __call__(self, request: CommandRequest, event_refs: tuple[str, ...], trace_id: str) -> str: ...

class CommandBoundary:
    def __init__(
        self,
        handler: CommandHandler,
        *,
        version_reader,
        store: CommandResultStore | None = None,
        refresh_scheduler: ProjectionRefreshScheduler | None = None,
        request_validator: Callable[[CommandRequest], None] | None = None,
    ) -> None:
        self._handler = handler
        self._version_reader = version_reader
        self._store = store
        self._refresh_scheduler = refresh_scheduler
        self._request_validator = request_validator
        self._results: dict[str, tuple[str, CommandResult]] = {}

    def execute(self, request: CommandRequest) -> CommandResult:
        if not all(isinstance(value, str) and value.strip() for value in (request.command_id, request.request_id, request.actor, request.target)):
            return _rejected(request, "validation_failed", "命令身份字段不能为空。", False)
        if not isinstance(request.payload, Mapping):
            return _rejected(request, "validation_failed", "命令载荷或版本格式无效。", False)
        if self._request_validator is not None:
            try:
                self._request_validator(request)
            except CommandRejectedError as error:
                return _rejected(request, error.code, error.message, error.retryable)
            except Exception:
                return CommandResult(
                    CommandStatus.FAILED,
                    request.command_id,
                    request.request_id,
                    CommandError("command_validation_failed", "命令预校验失败。", False),
                )
        if request.expected_version is not None and (type(request.expected_version) is not int or request.expected_version < 0):
            return _rejected(request, "validation_failed", "命令载荷或版本格式无效。", False)
        key = request.idempotency_key or request.request_id
        try:
            fingerprint = request.request_fingerprint or _fingerprint(request)
        except ValueError:
            return _rejected(request, "validation_failed", "命令载荷必须是有效 JSON。", False)
        if self._store is not None:
            try:
                outcome = self._store.reserve(key, fingerprint)
            except CommandStoreError as error:
                code = "command_store_busy" if "busy" in str(error) else "command_store_unavailable"
                return CommandResult(CommandStatus.FAILED, request.command_id, request.request_id, CommandError(code, "命令存储暂不可用。", code == "command_store_busy"))
            early = self._reservation_result(outcome, request)
            if early is not None:
                return early
        else:
            cached = self._results.get(key)
            if cached is not None:
                return cached[1] if cached[0] == fingerprint else _conflict(request)
        result = self._execute(request)
        if result.error is not None and result.error.code == "command_version_unavailable":
            if self._store is not None:
                try:
                    self._store.release(key, fingerprint)
                except Exception:
                    return _unknown(request)
            return result
        if result.error is None or result.error.code != "command_outcome_unknown":
            if self._store is None:
                self._results[key] = (fingerprint, result)
            else:
                try:
                    self._store.complete(key, fingerprint, result)
                except Exception:
                    return _unknown(request, result.trace_id, result.emitted_event_refs)
        return result

    def _reservation_result(self, outcome: ReserveOutcome, request: CommandRequest) -> CommandResult | None:
        if outcome.status is ReserveStatus.ACQUIRED:
            return None
        if outcome.status is ReserveStatus.CONFLICT:
            return _conflict(request)
        if outcome.status is ReserveStatus.COMPLETED:
            assert outcome.record is not None and outcome.record.result is not None
            return outcome.record.result
        return _unknown(request)

    def _execute(self, request: CommandRequest) -> CommandResult:
        if request.expected_version is not None:
            try:
                current_version = self._version_reader(request.target)
            except Exception:
                return CommandResult(
                    CommandStatus.FAILED,
                    request.command_id,
                    request.request_id,
                    CommandError("command_version_unavailable", "暂时无法读取目标版本。", True),
                )
            if request.expected_version != current_version:
                return _rejected(request, "version_conflict", "目标版本已变化。", True)
        trace_id = f"trace-{uuid4().hex}"
        try:
            refs = tuple(self._handler(request))
        except CommandRejectedError as error:
            return _rejected(request, error.code, error.message, error.retryable)
        except Exception:
            return _unknown(request, trace_id)
        refresh_id = None
        if self._refresh_scheduler is not None:
            try:
                refresh_id = self._refresh_scheduler(request, refs, trace_id)
                if not isinstance(refresh_id, str) or not refresh_id:
                    raise ValueError("projection_refresh_receipt_invalid")
            except Exception:
                return _unknown(request, trace_id, refs)
        return CommandResult(CommandStatus.ACCEPTED, request.command_id, request.request_id,
                             audit_ref=f"audit-{request.request_id}", trace_id=trace_id,
                             emitted_event_refs=refs, projection_refresh_id=refresh_id)

def _rejected(request: CommandRequest, code: str, message: str, retryable: bool) -> CommandResult:
    return CommandResult(CommandStatus.REJECTED, request.command_id, request.request_id,
                         CommandError(code, message, retryable))

def _conflict(request: CommandRequest) -> CommandResult:
    return _rejected(request, "idempotency_conflict", "幂等键对应不同请求。", False)

def _unknown(request: CommandRequest, trace_id=None, refs=()) -> CommandResult:
    return CommandResult(CommandStatus.FAILED, request.command_id, request.request_id,
                         CommandError("command_outcome_unknown", "命令结果未完成对账，禁止自动重试。", False),
                         trace_id=trace_id, emitted_event_refs=tuple(refs))

def _fingerprint(request: CommandRequest) -> str:
    try:
        encoded = json.dumps({"command_id": request.command_id, "target": request.target,
                              "payload": request.payload, "expected_version": request.expected_version},
                             ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("command_payload_not_json") from error
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

def _encode_store(records: dict[str, CommandResultRecord]) -> dict[str, object]:
    return {"schema_version": SCHEMA_VERSION,
            "records": {key: {"fingerprint": item.fingerprint, "state": item.state.value,
                               "result": None if item.result is None else _encode_result(item.result)}
                        for key, item in records.items()}}

def _encode_result(result: CommandResult) -> dict[str, object]:
    error = None if result.error is None else {"code": result.error.code,
                                               "message": result.error.message,
                                               "retryable": result.error.retryable}
    return {"status": result.status.value, "command_id": result.command_id, "request_id": result.request_id,
            "error": error, "audit_ref": result.audit_ref, "trace_id": result.trace_id,
            "emitted_event_refs": list(result.emitted_event_refs),
            "projection_refresh_id": result.projection_refresh_id}

def _decode_store(raw: object) -> dict[str, CommandResultRecord]:
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "records"}:
        raise ValueError("command_store_schema_invalid")
    if raw["schema_version"] != SCHEMA_VERSION or not isinstance(raw["records"], dict):
        raise ValueError("command_store_schema_invalid")
    records = {}
    for key, item in raw["records"].items():
        if not isinstance(item, dict) or set(item) != {"fingerprint", "state", "result"}:
            raise ValueError("command_record_schema_invalid")
        result = None if item["result"] is None else _decode_result(item["result"])
        records[str(key)] = CommandResultRecord(str(item["fingerprint"]), CommandRecordState(item["state"]), result)
    return records

def _decode_result(raw: object) -> CommandResult:
    required = {"status", "command_id", "request_id", "error", "audit_ref", "trace_id",
                "emitted_event_refs", "projection_refresh_id"}
    if not isinstance(raw, dict) or set(raw) != required:
        raise ValueError("command_result_schema_invalid")
    error = raw["error"]
    decoded = None if error is None else CommandError(str(error["code"]), str(error["message"]),
                                                       bool(error["retryable"]))
    return CommandResult(CommandStatus(raw["status"]), str(raw["command_id"]), str(raw["request_id"]), decoded,
                         raw["audit_ref"], raw["trace_id"], tuple(str(x) for x in raw["emitted_event_refs"]),
                         raw["projection_refresh_id"])
