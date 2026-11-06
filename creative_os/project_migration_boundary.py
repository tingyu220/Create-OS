"""复用通用reserve/complete语义；迁移专用边界绑定原意图和原trace。"""

from dataclasses import replace
from uuid import uuid4
import re

from creative_os.project_migration_contract import (validate_directory_command, expected_key, request_data)
from creative_os.project_migration_schema import command_fingerprint
from creative_os.project_write_gate import migration_lease, operation_migration_lease
from creative_os.workspace_command import (CommandBoundary, FileCommandResultStore, CommandResult,
                                          CommandError, CommandStatus, _decode_result, _unknown)


class MigrationCommandResults(FileCommandResultStore):
    def __init__(self, service):
        super().__init__(service.projects_root)
        self.service = service

    def reserve(self, key, fingerprint):
        self.service.checkpoint("before_command_reserve", {})
        result = super().reserve(key, fingerprint)
        self.service.checkpoint("after_command_reserve", {})
        return result

    def complete(self, key, fingerprint, result):
        self.service.checkpoint("before_command_complete", {})
        super().complete(key, fingerprint, result)
        self.service.checkpoint("after_command_complete", {})


class MigrationCommandBoundary(CommandBoundary):
    def __init__(self, service):
        self.service = service
        super().__init__(service, version_reader=lambda _target: None, store=MigrationCommandResults(service))

    def execute(self, request):
        service = self.service
        try:
            op = validate_directory_command(request.command_id, request.target, request.payload, request.expected_version)
            if (request.actor != service.actor or not isinstance(request.request_id, str) or not request.request_id.strip()
                    or request.status != "accepted" or request.idempotency_key != expected_key(request, op)):
                raise ValueError("migration_request_invalid")
            request = replace(request, request_fingerprint=command_fingerprint(request_data(request)))
            existing = service.operations.read_operation(op)
            if request.command_id == "migrate_project_directory":
                if existing is not None:
                    return self._replay(request, existing)
                with migration_lease(service.projects_root, request.target["project_id"]):
                    existing = service.operations.read_operation(op)
                    if existing is not None:
                        return self._replay(request, existing)
                    service.prepare(request)
                    return self._execute_owned(request, op)
            if existing is None:
                raise ValueError("migration_operation_not_found")
            service.bind(request, existing)
            cached = self._store.read(request.idempotency_key)
            if cached is not None:
                if cached.fingerprint != request.request_fingerprint:
                    raise ValueError("migration_idempotency_conflict")
                return cached.result if cached.result is not None else _unknown(request)
            with operation_migration_lease(service.projects_root, existing["project_id"]):
                service.bind(request, service.operations.read_operation(op))
                return self._execute_owned(request, op)
        except (ValueError, OSError, RuntimeError) as error:
            code = str(error) if isinstance(error, ValueError) and re.fullmatch(r"[a-z][a-z0-9_]{1,100}", str(error)) else "migration_evidence_unavailable"
            return CommandResult(CommandStatus.REJECTED, request.command_id, request.request_id,
                                 CommandError(code, "迁移请求或证据暂不可用，请重新检查。", False))

    def _execute_owned(self, request, op):
        self.service.active.add(op)
        try:
            return super().execute(request)
        finally:
            self.service.active.discard(op)

    def _replay(self, request, record):
        self.service.bind(request, record, original=True)
        stored = self._store.read(request.idempotency_key)
        if stored is not None:
            if stored.fingerprint != record["command_fingerprint"]:
                raise ValueError("migration_command_evidence_conflict")
            if stored.result is not None:
                return stored.result
        # RESERVED或只有意图均不是自动续跑许可；原token过期不改变已有操作身份。
        return _unknown(request, record["trace_id"])

    def _execute(self, request):
        op = request.payload.get("operation_id") or request.target.get("operation_id")
        record = self.service.operations.read_operation(op)
        trace = record["trace_id"] if request.command_id == "migrate_project_directory" else "trace-" + uuid4().hex
        handled = self.service.execute_with_trace(request, trace)
        return CommandResult(handled.status, request.command_id, request.request_id, handled.error, handled.audit_ref,
                             trace, handled.emitted_event_refs)
