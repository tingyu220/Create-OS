from __future__ import annotations

from collections.abc import Mapping

from creative_os.workspace_command import CommandRejectedError
from creative_os.writer_draft_store import WriterDraftStore


class WriterDraftCommandHandler:
    """工作稿唯一写入入口。"""

    def __init__(self, project_id: str, store: WriterDraftStore) -> None:
        self.project_id = project_id
        self.store = store

    def validate(self, request) -> None:
        if request.command_id not in {"save_writer_draft", "restore_writer_version", "open_writer_chapter"}:
            raise CommandRejectedError("command_not_allowed", "当前命令不属于 Writer 工作台。")
        target = request.target
        if not isinstance(target, Mapping) or target.get("project_id") != self.project_id:
            raise CommandRejectedError("target_not_found", "目标小说项目不存在。")
        if type(target.get("chapter_number")) is not int or target["chapter_number"] <= 0:
            raise CommandRejectedError("validation_failed", "章节编号必须是正整数。")
        payload = request.payload
        if request.command_id == "save_writer_draft" and (not isinstance(payload.get("content"), str) or not payload["content"].strip()):
            raise CommandRejectedError("validation_failed", "工作稿正文不能为空。")
        if request.command_id == "restore_writer_version" and (type(payload.get("version")) is not int or payload["version"] <= 0):
            raise CommandRejectedError("validation_failed", "要恢复的版本无效。")

    def __call__(self, request):
        self.validate(request)
        chapter = request.target["chapter_number"]
        if request.command_id == "save_writer_draft":
            version = self.store.save(chapter, request.payload["content"], actor=request.actor, expected_version=request.expected_version)
            return (f"writer-draft:{chapter}:{version.version}",)
        if request.command_id == "restore_writer_version":
            version = self.store.restore(chapter, request.payload["version"], actor=request.actor, expected_version=request.expected_version)
            return (f"writer-restore:{chapter}:{version.version}",)
        return ()

