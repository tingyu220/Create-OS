from pathlib import Path

from creative_os.domains.chapter_production_orchestrator import ChapterProductionOrchestrator
from creative_os.domains.chapter_run_checkpoint import ChapterRunState


def test_start_stops_before_director_when_readiness_or_plan_not_active(tmp_path: Path):
    writer = type("Writer", (), {"calls": 0})()
    view = ChapterProductionOrchestrator(tmp_path, writer=writer).start("p", 1)
    assert view.state == ChapterRunState.AWAITING_READINESS_APPROVAL
    assert writer.calls == 0


def test_start_records_ready_then_projection_without_calling_writer(tmp_path: Path):
    readiness = type("Readiness", (), {"audit": lambda self: type("R", (), {"status": "ready"})()})()
    projection = type("Projection", (), {"content_hash": "a" * 64})()
    engagement = type("Engagement", (), {"project_chapter_locked": lambda self, project, chapter: projection})()
    writer = type("Writer", (), {"calls": 0})()
    view = ChapterProductionOrchestrator(tmp_path, readiness=readiness, engagement=engagement, writer=writer).start("p", 1)
    assert view.state == ChapterRunState.DIRECTOR_PROPOSED
    assert writer.calls == 0
