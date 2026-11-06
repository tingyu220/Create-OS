"""经验命令边界及恢复日志；日志只记录操作，不另建经验存储。"""

from dataclasses import replace
import json

from creative_os.domains.project_authority import project_authority_lock
from creative_os.memory.approval import approve_candidate, reject_candidate, archive_memory
from creative_os.memory.model import MemoryStatus
from creative_os.memory.store import _item_to_dict, _item_from_dict
from creative_os.writer_lesson import canonical
from creative_os.workspace_command import (CommandBoundary, CommandRejectedError, ReserveStatus,
                                          CommandResult, CommandStatus, CommandError, CommandRecordState, FileCommandResultStore)


class WriterLessonCommandBoundary(CommandBoundary):
    def execute(self, request):
        with project_authority_lock(self._handler.service.root):
            return super().execute(request)

    def _reservation_result(self, outcome, request):
        # 原指纹已匹配；操作日志先于副作用落盘，可按原请求安全续办。
        if outcome.status is ReserveStatus.RESERVED and outcome.record is not None:
            return None
        return super()._reservation_result(outcome, request)


class WriterLessonCommandHandler:
    def __init__(self, service):
        self.service = service
        self.root = service.root / ".creative_os/agent/lesson_operations"

    def validate(self, request):
        payload = request.payload
        if request.command_id != "manage_writer_lesson" or not isinstance(request.target, dict):
            raise CommandRejectedError("validation_failed", "经验命令或目标无效。")
        if request.expected_version is not None or not request.actor.strip() or request.actor.strip().casefold() == "system":
            raise CommandRejectedError("validation_failed", "经验操作需要明确的作者身份。")
        action = payload.get("action")
        if not isinstance(action, str):
            raise CommandRejectedError("validation_failed", "经验操作必须是文字。")
        if action == "create":
            if (set(payload) != {"action", "title", "content", "range"}
                    or any(not isinstance(payload[key], str) or not payload[key].strip() for key in ("title", "content"))
                    or len(payload["title"]) > 120 or len(payload["content"]) > 2000
                    or not isinstance(payload["range"], str) or payload["range"] not in {"chapter", "project"}):
                raise CommandRejectedError("validation_failed", "请填写可复用经验、标题和适用范围；无经验时无需创建。")
        elif action in {"approve", "reject", "archive"}:
            if (set(payload) != {"action", "memory_id", "version", "note"}
                    or type(payload["version"]) is not int or payload["version"] < 1
                    or not isinstance(payload["memory_id"], str)
                    or not isinstance(payload["note"], str) or not payload["note"].strip()):
                raise CommandRejectedError("validation_failed", "审阅需要经验编号、版本及作者说明。")
        else:
            raise CommandRejectedError("validation_failed", "不支持的经验操作。")
        self.service.feedback(request.target)

    def __call__(self, request):
        self.validate(request)
        service, payload = self.service, request.payload
        action = payload["action"]
        if action == "create":
            item = service.candidate(request.target, payload)
            slot = item.id + "-create"
        else:
            item = service.scoped_item(request.target, payload["memory_id"])
            slot = item.id + f"-v{payload['version']}-" + ("archive" if action == "archive" else "review")
        path = self.root / f"{slot}.json"
        identity = {"target": request.target, "payload": payload, "actor": request.actor}
        command = {"key": request.idempotency_key or request.request_id, "request_id": request.request_id}
        if path.exists():
            operation = json.loads(path.read_text(encoding="utf-8"))
            if operation["identity"] != identity:
                raise CommandRejectedError("lesson_decision_conflict", "该经验已有不同的创建或审阅决定。")
        else:
            if action != "create":
                allowed = {"approve": {MemoryStatus.CANDIDATE}, "reject": {MemoryStatus.CANDIDATE},
                           "archive": {MemoryStatus.ACTIVE, MemoryStatus.REJECTED}}[action]
                if item.version != payload["version"] or item.status not in allowed:
                    raise CommandRejectedError("lesson_version_conflict", "经验版本或状态已变化，请刷新后审阅。")
            operation = {"identity": identity, "item": _item_to_dict(item), "commands": [], "done": False}
        if command not in operation["commands"]:
            operation["commands"].append(command)
        self._write(path, operation)
        try:
            return self._finish(path, operation)
        except CommandRejectedError as error:
            operation["error"] = {"code": error.code, "message": error.message}
            self._write(path, operation)
            raise

    def _finish(self, path, operation):
        service = self.service
        item = _item_from_dict(operation["item"])
        identity = operation["identity"]
        action = identity["payload"]["action"]
        refs = (f"memory:{item.id}:{action}",)
        if operation.get("error"):
            raise CommandRejectedError(**operation["error"])
        if operation["done"]:
            return refs
        store = service.store
        note = canonical({"operation": path.stem, "note": identity["payload"].get("note", "作者创建经验候选")})
        if action == "create":
            try:
                current = store.get_strict(item.id)
            except KeyError:
                store.add_candidate(item)
                current = item
            if current != item:
                raise CommandRejectedError("lesson_version_conflict", "经验候选已发生变化。")
            audit_action = "create_lesson"
        else:
            current = store.get_strict(item.id)
            desired = {"approve": MemoryStatus.ACTIVE, "reject": MemoryStatus.REJECTED, "archive": MemoryStatus.ARCHIVED}[action]
            if current == item:
                transition = {"approve": approve_candidate, "reject": reject_candidate, "archive": archive_memory}[action]
                current = transition(store, item.id, actor=identity["actor"], note=note)
            elif (current.status != desired
                  or replace(current, status=item.status, updated_at=item.updated_at, approved_by=item.approved_by) != item
                  or (action == "approve" and current.approved_by != identity["actor"].strip())):
                raise CommandRejectedError("lesson_version_conflict", "恢复时经验内容、版本或状态冲突。")
            audit_action = action
        # Memory 状态落盘与审计追加之间中断时，补齐原操作审计，避免重复审批。
        audits = [json.loads(line) for line in store.audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not any(row.get("memory_id") == item.id and row.get("action") == audit_action and row.get("note") == note for row in audits):
            store.append_audit(audit_action, current, actor=identity["actor"], from_status=item.status, note=note)
        operation["done"] = True
        self._write(path, operation)
        return refs

    def recover(self):
        with project_authority_lock(self.service.root):
            commands = FileCommandResultStore(self.service.root)
            for path in sorted(self.root.glob("*.json")):
                operation = json.loads(path.read_text(encoding="utf-8"))
                error = None
                refs = ()
                try:
                    refs = self._finish(path, operation)
                except CommandRejectedError as rejected:
                    operation["error"] = {"code": rejected.code, "message": rejected.message}
                    self._write(path, operation)
                    error = CommandError(rejected.code, rejected.message, rejected.retryable)
                for command in operation["commands"]:
                    record = commands.read(command["key"])
                    if record and record.state is CommandRecordState.RESERVED:
                        commands.complete(command["key"], record.fingerprint,
                                          CommandResult(CommandStatus.REJECTED if error else CommandStatus.ACCEPTED,
                                                        "manage_writer_lesson", command["request_id"], error=error, emitted_event_refs=refs))

    @staticmethod
    def _write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(canonical(value), encoding="utf-8")
        temporary.replace(path)
