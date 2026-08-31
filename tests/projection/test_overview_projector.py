from __future__ import annotations

from creative_os.projection.chapters import ChapterSnapshot, ChapterStatus
from creative_os.projection.overview import ProjectRunStatus
from creative_os.projection.projectors.overview import project_overview
from creative_os.projection.provenance import Derivation, SourceRef
from creative_os.projection.quality import GateResultSnapshot, QualitySnapshot
from creative_os.projection.trace import TraceSnapshot


def test_overview_reports_blocker_with_original_derivation() -> None:
    """捕获 Overview 丢失阻塞原因来源或自行编造原因的实现。"""
    reference = SourceRef("review_gate", "gate-029", "gates/029.json", "e" * 64)
    blocker = Derivation("chapter.blocked_by_gate", (reference,), "gate-029")
    chapter = ChapterSnapshot(
        chapter_id="chapter-029",
        chapter_number=29,
        title="unknown",
        status=ChapterStatus.BLOCKED,
        attempts=1,
        elapsed_seconds=4.0,
        source_refs=(reference,),
        blocked_by=(blocker,),
    )

    overview = project_overview(
        chapters=(chapter,),
        quality=QualitySnapshot((), (GateResultSnapshot("gate-029", "failed", (reference,)),), (reference,)),
        trace=TraceSnapshot((), ()),
    )

    assert overview.run_status is ProjectRunStatus.BLOCKED
    assert overview.blocked_chapter_count == 1
    assert overview.blockers[0].derivation == blocker


def test_overview_with_no_authoritative_progress_is_unknown() -> None:
    overview = project_overview(
        chapters=(),
        quality=QualitySnapshot((), (), ()),
        trace=TraceSnapshot((), ()),
    )

    assert overview.current_stage == "unknown"
    assert overview.run_status is ProjectRunStatus.UNKNOWN
