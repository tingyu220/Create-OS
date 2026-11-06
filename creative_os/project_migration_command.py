"""目录迁移意图与核对编号的持久边界；实际 IO 留给后续任务。"""

from creative_os.project_migration_store import ProjectMigrationStore
from creative_os.project_directory import validated_project


class ProjectMigrationCommand:
    def __init__(self, projects_root):
        self.store = ProjectMigrationStore(projects_root)

    def reserve(self, request, *, actor):
        _validate_request(request, actor)
        existing = self.store.read_operation(request["operation_id"])
        record = {"operation_id": request["operation_id"], "project_id": request["project_id"],
                  "plan_fingerprint": request["plan_fingerprint"], "source_directory": request["source_directory"],
                  "target_directory": request["target_directory"], "backup_directory": f".backup/project-directory-migrations/{request['operation_id']}/project",
                  "stage": "reserved", "continuation_no": 0, "reason": None, "actor": actor}
        if existing is not None:
            if any(existing.get(key) != record[key] for key in ("actor", "project_id", "plan_fingerprint", "source_directory", "target_directory")):
                raise ValueError("migration_idempotency_conflict")
            return existing
        # 首次登记验证当前目录；既有操作只重放原记录，允许源已迁至目标。
        source, _ = validated_project(self.store.root, request["project_id"])
        if source.name != request["source_directory"]:
            raise ValueError("project_scope_mismatch")
        self.store.write_operation(record)
        return record

    def continue_operation(self, operation_id, continuation_no):
        record = self.store.read_operation(operation_id)
        if record is None:
            raise ValueError("migration_operation_not_found")
        if type(continuation_no) is not int or continuation_no != record["continuation_no"] + 1:
            raise ValueError("continuation_no_invalid")
        updated = dict(record)
        updated["continuation_no"] = continuation_no
        updated["stage"] = "backup_verified"
        self.store.write_operation(updated)
        return updated

    def status(self, operation_id):
        return self.store.read_operation(operation_id)


def _validate_request(request, actor):
    if not isinstance(request, dict) or any(not isinstance(request.get(key), str) or not request[key].strip() for key in ("operation_id", "project_id", "plan_fingerprint", "source_directory", "target_directory")):
        raise ValueError("migration_request_invalid")
    if len(request["plan_fingerprint"]) != 64 or not isinstance(actor, str) or not actor.strip():
        raise ValueError("migration_request_invalid")
