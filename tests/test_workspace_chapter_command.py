from types import SimpleNamespace

import pytest

from creative_os.workspace_chapter_command import WorkspaceChapterRunCommandHandler
from creative_os.workspace_command import CommandRejectedError, CommandRequest


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    def start(self, project_id, chapter_number):
        self.calls.append((project_id, chapter_number))
        return SimpleNamespace(chapter_number=chapter_number, checkpoint_hash="a" * 64)


def _request(target, payload=None):
    return CommandRequest("start_chapter_run", "r1", "writer", target, payload or {}, idempotency_key="k1")


def test_chapter_run_command_delegates_to_orchestrator_and_emits_checkpoint_ref():
    orchestrator = FakeOrchestrator()
    handler = WorkspaceChapterRunCommandHandler("novel-1", orchestrator)

    refs = handler(_request({"project_id": "novel-1", "chapter_number": 7}))

    assert orchestrator.calls == [("novel-1", 7)]
    assert refs == ("chapter-run:novel-1:7:" + "a" * 64,)


@pytest.mark.parametrize(
    "command_request",
    [_request({"project_id": "other", "chapter_number": 7}), _request({"project_id": "novel-1", "chapter_number": 0}), _request({"project_id": "novel-1", "chapter_number": 7}, {"x": 1})],
)
def test_chapter_run_command_rejects_invalid_boundary_input(command_request):
    with pytest.raises(CommandRejectedError):
        WorkspaceChapterRunCommandHandler("novel-1", FakeOrchestrator()).validate(command_request)
