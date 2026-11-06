"""作者显式编辑、确认的命令边界；模型不能取得此权限。"""

from creative_os.domains.project_authority import project_authority_lock
from creative_os.workspace_command import CommandBoundary, CommandRejectedError, FileCommandResultStore, ReserveStatus
from creative_os.story_architecture_store import content_hash, validate_content
from dataclasses import replace


class StoryCommandBoundary(CommandBoundary):
    def execute(self, request):
        with project_authority_lock(self._handler.store.root):
            fingerprint = content_hash({"command_id": request.command_id, "actor": request.actor, "target": request.target,
                                        "payload": request.payload, "expected_version": request.expected_version})
            return super().execute(replace(request, request_fingerprint=fingerprint))

    def _reservation_result(self, outcome, request):
        # 同指纹 reservation 可恢复：领域操作与 operation receipt 原子提交，无分离副作用。
        if outcome.status is ReserveStatus.RESERVED:
            return None
        return super()._reservation_result(outcome, request)


class StoryCommandHandler:
    def __init__(self, store):
        self.store = store

    def validate(self, request):
        target, payload = request.target, request.payload
        if request.command_id not in {"edit_story_candidate", "confirm_story_candidate", "adopt_combat_candidate"} or request.expected_version is not None:
            raise CommandRejectedError("command_not_allowed", "仅支持明确的故事候选编辑或确认。")
        if not isinstance(target, dict) or set(target) != {"project_id", "scope", "session_id"} or target != {"project_id": self.store.project_id, "scope": "story", "session_id": self.store.session_id}:
            raise CommandRejectedError("story_scope_mismatch", "故事项目、作用域或会话不匹配。")
        fields = ({"blocks", "open_questions", "expected_revision"} if request.command_id == "edit_story_candidate"
                  else {"result_id", "expected_revision"} if request.command_id == "adopt_combat_candidate"
                  else {"revision", "hash", "expected_confirmed_version"})
        if not isinstance(payload, dict) or set(payload) != fields:
            raise CommandRejectedError("story_payload_invalid", "故事命令字段不匹配。")
        try:
            if request.actor != "作者":
                raise ValueError("story_author_required")
            if request.command_id == "edit_story_candidate":
                if type(payload["expected_revision"]) is not int or payload["expected_revision"] < 0:
                    raise ValueError("story_revision_invalid")
                validate_content(payload["blocks"], payload["open_questions"])
            elif request.command_id == "adopt_combat_candidate":
                if (type(payload["expected_revision"]) is not int or payload["expected_revision"] < 0
                        or not isinstance(payload["result_id"], str) or not payload["result_id"].strip()):
                    raise ValueError("combat_result_id_required")
            elif (type(payload["revision"]) is not int or payload["revision"] <= 0
                  or type(payload["expected_confirmed_version"]) is not int or payload["expected_confirmed_version"] < 0
                  or not isinstance(payload["hash"], str) or not payload["hash"].strip()):
                raise ValueError("story_confirmation_invalid")
        except (ValueError, TypeError) as error:
            raise CommandRejectedError(str(error), "故事命令参数无效。") from error

    def __call__(self, request):
        self.validate(request)
        try:
            operation_id = "command:" + (request.idempotency_key or request.request_id)
            if request.command_id == "adopt_combat_candidate":
                from creative_os.combat_story_candidate import stage_combat_candidate
                item = stage_combat_candidate(self.store, request.payload["result_id"],
                    expected_revision=request.payload["expected_revision"], actor=request.actor, operation_id=operation_id)
                return (f"story-candidate:{item['revision']}:{item['hash']}",)
            if request.command_id == "edit_story_candidate":
                item = self.store.propose(request.target["session_id"], actor=request.actor, operation_id=operation_id, **request.payload)
                return (f"story-candidate:{item['revision']}:{item['hash']}",)
            payload = request.payload
            item = self.store.confirm(request.target["session_id"], payload["revision"], payload["hash"],
                                      expected_confirmed_version=payload["expected_confirmed_version"], actor=request.actor, operation_id=operation_id)
            return (f"story-confirmed:{item['version']}:{item['hash']}",)
        except (ValueError, TypeError) as error:
            raise CommandRejectedError(str(error), "故事设定未修改：" + str(error)) from error


def story_commands(store):
    handler = StoryCommandHandler(store)
    return StoryCommandBoundary(handler, version_reader=lambda _: None, store=FileCommandResultStore(store.root), request_validator=handler.validate)
