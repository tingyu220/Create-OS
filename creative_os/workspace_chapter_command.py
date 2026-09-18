from __future__ import annotations

from collections.abc import Mapping

from creative_os.domains.chapter_production_orchestrator import ChapterProductionOrchestrator
from creative_os.workspace_command import CommandRejectedError, CommandRequest


class WorkspaceChapterRunCommandHandler:
    """通过章节生产编排器启动一次章节运行，不直接改写投影。"""

    def __init__(self, project_id: str, orchestrator: ChapterProductionOrchestrator) -> None:
        if not project_id.strip():
            raise ValueError("workspace_project_id_required")
        self._project_id = project_id.strip()
        self._orchestrator = orchestrator

    def validate(self, request: CommandRequest) -> None:
        if request.command_id != "start_chapter_run":
            raise CommandRejectedError("command_not_allowed", "当前只允许启动章节运行命令。")
        target = request.target
        if not isinstance(target, Mapping) or target.get("project_id") != self._project_id:
            raise CommandRejectedError("target_not_found", "目标小说项目不存在。")
        chapter_number = target.get("chapter_number")
        if type(chapter_number) is not int or chapter_number <= 0:
            raise CommandRejectedError("validation_failed", "章节编号必须是正整数。")
        if request.payload:
            raise CommandRejectedError("validation_failed", "章节运行命令载荷必须为空对象。")

    def __call__(self, request: CommandRequest) -> tuple[str, ...]:
        self.validate(request)
        target = request.target
        assert isinstance(target, Mapping)
        view = self._orchestrator.start(self._project_id, target["chapter_number"])
        return (f"chapter-run:{self._project_id}:{view.chapter_number}:{view.checkpoint_hash}",)
