"""同根目录迁移服务：明确确认、完整备份、拒绝覆盖移动及显式核对。"""

from dataclasses import replace
from pathlib import Path
import secrets
from uuid import uuid4

from creative_os.project_directory_inventory import (build_inventory, inventory_hash, copy_verified,
                                                       rename_no_replace, safe_path)
from creative_os.project_migration_preview import DirectoryMigrationPreview
from creative_os.project_migration_store import ProjectMigrationStore
from creative_os.project_migration_contract import request_data
from creative_os.project_migration_schema import command_fingerprint
from creative_os.project_migration_activity import assert_persistent_idle
from creative_os.project_write_gate import assert_operation_lease
from creative_os.project_migration_evidence import (validate_record_scope, matches, write_manifest,
                                                    verified_backup, command_record_guard)
from creative_os.workspace_command import (CommandHandlerResult, CommandResult, CommandStatus,
                                          CommandError, _encode_result, _decode_result)


def checkpoint(point, record):
    """阶段观察点；中断不得被解释为隐式重试许可。"""


class ProjectMigrationService:
    def __init__(self, projects_root, backup_root, registry, default_project_id=None, default_root=None):
        self.projects_root = safe_path(projects_root)
        safe_path(self.projects_root / ".creative_os")
        self.workspace = self.projects_root.parent
        self.backup_root = safe_path(backup_root)
        if self.backup_root != self.workspace / ".backup/project-directory-migrations":
            raise ValueError("migration_backup_scope_mismatch")
        self.registry, self.actor = registry, "作者"
        self.default_project_id = default_project_id
        self.default_root = Path(default_root).absolute() if default_root is not None else None
        self.operations = ProjectMigrationStore(self.projects_root)
        self.previews = DirectoryMigrationPreview(self.projects_root, self.backup_root, secrets.token_bytes(32))
        self.owner_epoch = str(uuid4())
        self.active = set()
        from creative_os.project_migration_boundary import MigrationCommandBoundary
        self.commands = MigrationCommandBoundary(self)

    def checkpoint(self, point, record):
        checkpoint(point, record)

    def preview(self, project_id):
        return self.previews.build(project_id)

    def prepare(self, request):
        project_id = request.target["project_id"]
        assert_operation_lease(self.projects_root, project_id)
        self.registry.assert_migration_idle(project_id)
        for other in self.operations.read_operations().values():
            if other["project_id"].casefold() == project_id.casefold() and other["stage"] not in {"verified", "failed"}:
                raise ValueError("project_migration_busy")
        payload = request.payload
        preview = self.previews.validate(payload["preview_token"], payload["operation_id"], payload["plan_fingerprint"])
        if preview["project_id"] != project_id:
            raise ValueError("project_scope_mismatch")
        plan, inventory, available, _reason = self.previews.inspect(project_id)
        if not available or inventory_hash(plan) != payload["plan_fingerprint"]:
            raise ValueError("preview_stale")
        raw = request_data(request)
        record = {"record_version": 2, "operation_id": payload["operation_id"], "project_id": project_id,
                  "plan_fingerprint": payload["plan_fingerprint"], "source_directory": plan["source_directory"],
                  "target_directory": plan["target_directory"], "backup_directory": preview["backup_directory"],
                  "stage": "reserved", "continuation_no": 0, "reason": None, "actor": request.actor,
                  "plan": plan, "original_request": raw, "command_fingerprint": command_fingerprint(raw),
                  "trace_id": "trace-" + uuid4().hex, "owner_epoch": self.owner_epoch, "result_template": None,
                  "backup_verified": False, "move_started": False, "continuation_ready": False,
                  "consumed_continuation": 0, "reload_required": self.default_project_id == project_id and self.default_root == self.projects_root / plan["source_directory"]}
        self.checkpoint("before_intent", record)
        self.operations.write_operation(record)
        self.checkpoint("after_intent", record)

    def bind(self, request, record, original=False):
        validate_record_scope(self, record)
        if (request.actor != record["actor"] or request.target["project_id"] != record["project_id"]
                or request.payload["plan_fingerprint"] != record["plan_fingerprint"]):
            raise ValueError("migration_idempotency_conflict")
        if original and command_fingerprint(request_data(request)) != record["command_fingerprint"]:
            raise ValueError("migration_idempotency_conflict")

    def execute_with_trace(self, request, trace_id):
        return self.execute(request, trace_id)

    def execute(self, request, trace_id):
        op = request.payload.get("operation_id") or request.target.get("operation_id")
        if op not in self.active:
            raise ValueError("migration_command_ownership_required")
        assert_operation_lease(self.projects_root, request.target["project_id"])
        record = self.operations.read_operation(op)
        try:
            if request.command_id == "reconcile_project_directory":
                from creative_os.project_migration_recovery import reconcile
                return reconcile(self, record)
            if request.command_id == "continue_project_directory":
                return self._continue(request, record)
            return self._start(record)
        except (ValueError, OSError, RuntimeError):
            record = self.operations.read_operation(op)
            # 不猜测rename是否发生；留存源、目标、备份与原reservation供明确核对。
            if record["stage"] not in {"verified", "failed"}:
                self.transition(record, "needs_reconciliation", reason="migration_io_or_evidence_failure", continuation_ready=False)
            return self.outcome("command_outcome_unknown")

    def _start(self, record):
        source, target, backup = validate_record_scope(self, record)
        self._idle(record, source)
        if not matches(record, source, self.projects_root) or target.exists():
            raise ValueError("migration_source_changed")
        self.transition(record, "backing_up")
        backup.parent.mkdir(parents=True, exist_ok=False)
        inventory = build_inventory(source)
        copy_verified(source, backup, inventory)
        write_manifest(record, backup, inventory)
        verified_backup(record, backup)
        self.transition(record, "backup_verified", backup_verified=True)
        return self._move(record)

    def _idle(self, record, source):
        assert_persistent_idle(self.projects_root, source, record["project_id"])
        self.registry.assert_cached_migration_idle(record["project_id"])

    def _move(self, record):
        source, target, backup = validate_record_scope(self, record)
        self._idle(record, source)
        if not verified_backup(record, backup) or not matches(record, source, self.projects_root) or target.exists():
            raise ValueError("migration_source_changed")
        self.transition(record, "moving", move_started=True, continuation_ready=False)
        self.checkpoint("before_rename", record)
        rename_no_replace(source, target)
        self.checkpoint("after_rename", record)
        if source.exists() or not matches(record, target, self.projects_root) or not verified_backup(record, backup):
            raise ValueError("migration_verification_failed")
        return self.finish_verified(record)

    def _continue(self, request, record):
        if (record["stage"] != "backup_verified" or not record["continuation_ready"]
                or request.payload["continuation_no"] != record["continuation_no"]
                or record["consumed_continuation"] >= record["continuation_no"]):
            return self.outcome("continuation_no_invalid", rejected=True)
        self.transition(record, "backup_verified", consumed_continuation=record["continuation_no"], continuation_ready=False)
        return self._move(record)

    def finish_verified(self, record):
        self.registry.invalidate_after_migration(record["project_id"])
        template = self.original_result(record, CommandStatus.ACCEPTED)
        self.transition(record, "verified", backup_verified=True, move_started=True, continuation_ready=False, reason=None, result_template=_encode_result(template))
        self.complete_original(record)
        return CommandHandlerResult(audit_ref="directory-migration:" + record["operation_id"],
                                    emitted_event_refs=("directory-migration:" + record["operation_id"] + ":verified",))

    def transition(self, record, stage, **changes):
        updated = {**record, **changes, "stage": stage, "owner_epoch": self.owner_epoch}
        self.checkpoint("before_" + stage, updated)
        self.operations.write_operation(updated)
        record.clear()
        record.update(updated)
        self.checkpoint("after_" + stage, record)

    @staticmethod
    def original_result(record, status, code=None):
        raw = record["original_request"]
        return CommandResult(status, raw["command_id"], raw["request_id"],
                             None if code is None else CommandError(code, "本次迁移已核对为未完成；原文件保留。", False),
                             "directory-migration:" + record["operation_id"], record["trace_id"],
                             ("directory-migration:" + record["operation_id"] + ":verified",) if status == CommandStatus.ACCEPTED else ())

    def complete_original(self, record):
        command_record_guard(self, record)
        raw = record["original_request"]
        result = _decode_result(record["result_template"])
        store = self.commands._store
        if store.read(raw["idempotency_key"]) is None:
            store.reserve(raw["idempotency_key"], record["command_fingerprint"])
        store.complete(raw["idempotency_key"], record["command_fingerprint"], result)

    @staticmethod
    def outcome(code, rejected=False):
        return CommandHandlerResult(CommandStatus.REJECTED if rejected else CommandStatus.FAILED,
                                    CommandError(code, "迁移尚未完成，请查看状态并明确核对或确认继续。", False))

    def status(self, operation_id):
        record = self.operations.read_operation(operation_id)
        if record is None:
            return None
        if record.get("record_version") == 2:
            validate_record_scope(self, record)
        unresolved = record["stage"] not in {"verified", "failed"}
        return {key: record[key] for key in ("operation_id", "project_id", "plan_fingerprint", "stage", "reason", "source_directory", "target_directory", "backup_directory", "continuation_no")} | {
            "reload_required": record.get("reload_required", False),
            "needs_reconciliation": unresolved and operation_id not in self.active,
            "actions": (["open"] if record["stage"] == "verified" else ["reconcile", "continue"] if record.get("continuation_ready") else ["reconcile"]),
            "entry_url": "/p/" + __import__("urllib.parse", fromlist=["quote"]).quote(record["project_id"], safe="") + "/"}

    def availability(self, project_id, root=None, *, writable=False):
        """任务5可映射为默认旧根503/409；本接口只读，不装配Runtime。"""
        for record in self.operations.read_operations().values():
            if record["project_id"] != project_id or record["stage"] == "failed":
                continue
            old = root is not None and Path(root).absolute() == self.projects_root / record["source_directory"]
            if old or record["stage"] != "verified":
                return {"available": False, "http_status": 409 if writable else 503,
                        "reason_code": "project_directory_reload_required" if old and record["stage"] == "verified" else "project_migration_unavailable",
                        "reload_required": old and record["stage"] == "verified"}
        return {"available": True, "reload_required": False}
