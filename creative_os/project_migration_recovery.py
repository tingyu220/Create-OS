"""显式核对迁移；只按原操作证据分类，不自动搬运或回填。"""

from creative_os.project_migration_evidence import (validate_record_scope, matches, verified_backup,
                                                    command_record_guard)
from creative_os.workspace_command import CommandStatus, _encode_result


def reconcile(service, record):
    source, target, backup = validate_record_scope(service, record)
    command_record_guard(service, record)
    if record["stage"] == "failed":
        service.complete_original(record)
        return service.outcome("migration_failed")
    source_exists, target_exists = source.exists(), target.exists()
    if source_exists == target_exists:
        return _conflict(service, record)
    present = source if source_exists else target
    service._idle(record, present)
    if not matches(record, present, service.projects_root):
        return _conflict(service, record)
    try:
        inventory = verified_backup(record, backup)
    except (ValueError, OSError):
        inventory = None
    if inventory is not None:
        if target_exists:
            return service.finish_verified(record)
        if record["stage"] == "verified":
            return _conflict(service, record)
        current_key = f"directory-continue:{record['operation_id']}:{record['continuation_no']}"
        if not record["continuation_ready"] or service.commands._store.read(current_key) is not None:
            no = record["continuation_no"] + 1
            while service.commands._store.read(f"directory-continue:{record['operation_id']}:{no}") is not None:
                no += 1
            service.transition(record, "backup_verified", backup_verified=True, continuation_ready=True,
                               continuation_no=no, reason=None)
        return service.outcome("migration_confirmation_required", rejected=True)
    if source_exists and not record["move_started"] and not record["backup_verified"]:
        result = service.original_result(record, CommandStatus.FAILED, "migration_failed")
        service.transition(record, "failed", reason="migration_failed", result_template=_encode_result(result), continuation_ready=False)
        service.complete_original(record)
        return service.outcome("migration_failed")
    return _conflict(service, record)


def _conflict(service, record):
    if record["stage"] == "verified":
        # 已完成事实不可被一次后续目录变化改写；保留成功历史，响应另报冲突。
        return service.outcome("migration_evidence_conflict", rejected=True)
    service.transition(record, "needs_reconciliation", reason="migration_evidence_conflict", continuation_ready=False)
    return service.outcome("migration_needs_reconciliation", rejected=True)
