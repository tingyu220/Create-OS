from __future__ import annotations

from creative_os.console_dashboard import render_console_dashboard
from creative_os.projection.chapters import ChapterSnapshot, ChapterStatus
from creative_os.projection.model import ProjectSnapshot
from creative_os.projection.overview import OverviewBlocker, OverviewSnapshot, ProjectRunStatus
from creative_os.projection.provenance import Derivation, SourceHead, SourceRef
from creative_os.projection.quality import GateResultSnapshot, QualityIssueSnapshot, QualitySnapshot
from creative_os.projection.trace import TraceEntrySnapshot, TraceSnapshot


def _snapshot() -> ProjectSnapshot:
    reference = SourceRef("review_gate", "gate-002", "reviews/002.json", "a" * 64)
    derivation = Derivation("chapter.blocked_by_gate", (reference,), "gate-002")
    chapters = (
        ChapterSnapshot("chapter-001", 1, "第一章", ChapterStatus.PASSED, 1, 3.2, (reference,)),
        ChapterSnapshot(
            "chapter-002", 2, "第二章", ChapterStatus.BLOCKED, 2, 8.5,
            (reference,), blocked_by=(derivation,),
        ),
    )
    quality = QualitySnapshot(
        issues=(QualityIssueSnapshot("issue-2", "missing_fact", "error", True, "chapter-002", (reference,)),),
        gate_results=(GateResultSnapshot("gate-002", "failed", (reference,)),),
        source_refs=(reference,),
    )
    trace = TraceSnapshot(
        entries=(TraceEntrySnapshot(
            "event", 1, "event-1", "TaskFailed", "2026-09-01T00:00:00+00:00",
            "chapter-002", "execution-1", "TaskFailed task=chapter-002", (reference,),
        ),),
        source_refs=(reference,),
    )
    return ProjectSnapshot.create(
        project_id="book-a",
        built_at="2026-09-01T00:00:00+00:00",
        source_heads=(SourceHead("review", "review", "1", "b" * 64),),
        overview=OverviewSnapshot(
            "review", ProjectRunStatus.BLOCKED, 2, 1, (reference,),
            (OverviewBlocker("chapter_blocked:chapter-002", "第二章被阻塞", derivation),),
        ),
        chapters=chapters,
        quality=quality,
        trace=trace,
    )


def test_render_console_dashboard_reads_only_snapshot() -> None:
    """捕获控制台重新读取项目文件并拼接领域逻辑的实现。"""
    output = render_console_dashboard(_snapshot())

    assert "项目：book-a" in output
    assert "当前阶段：review" in output
    assert "通过：1" in output
    assert "阻塞：1" in output
    assert "chapter-002 blocked" in output
    assert "missing_fact" in output
    assert "TaskFailed task=chapter-002" in output


def test_render_console_dashboard_handles_empty_snapshot() -> None:
    empty = ProjectSnapshot.create(
        project_id="book-a",
        built_at="2026-09-01T00:00:00+00:00",
        source_heads=(SourceHead("project", "project", "1", "c" * 64),),
        overview=OverviewSnapshot("unknown", ProjectRunStatus.UNKNOWN, 0, 0, ()),
        chapters=(),
        quality=QualitySnapshot((), (), ()),
        trace=TraceSnapshot((), ()),
    )

    output = render_console_dashboard(empty)

    assert "暂无章节投影" in output
    assert "暂无质量问题" in output
    assert "暂无运行轨迹" in output
