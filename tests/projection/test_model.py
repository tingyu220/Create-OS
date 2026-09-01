from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from creative_os.projection.chapters import ChapterSnapshot, ChapterStatus
from creative_os.projection.model import ProjectSnapshot
from creative_os.projection.overview import OverviewSnapshot, ProjectRunStatus
from creative_os.projection.provenance import Derivation, SourceHead, SourceRef
from creative_os.projection.quality import QualitySnapshot
from creative_os.projection.trace import TraceSnapshot


def _source_ref() -> SourceRef:
    return SourceRef(
        source_kind="chapter_status",
        source_id="chapter-029",
        locator="production/runs/status/chapter_029_status.json",
        content_hash="a" * 64,
    )


def _snapshot(built_at: str) -> ProjectSnapshot:
    reference = _source_ref()
    derivation = Derivation("chapter.status_from_task", (reference,))
    chapter = ChapterSnapshot(
        chapter_id="chapter-029",
        chapter_number=29,
        title="自主的旧硬盘",
        status=ChapterStatus.BLOCKED,
        attempts=1,
        elapsed_seconds=3.5,
        source_refs=(reference,),
        derivations=(derivation,),
    )
    return ProjectSnapshot.create(
        project_id="文明升阶",
        built_at=built_at,
        source_heads=(SourceHead("chapter_status", "status", "29", "b" * 64),),
        overview=OverviewSnapshot(
            current_stage="review",
            run_status=ProjectRunStatus.BLOCKED,
            chapter_count=1,
            blocked_chapter_count=1,
            source_refs=(reference,),
        ),
        chapters=(chapter,),
        quality=QualitySnapshot(issues=(), gate_results=(), source_refs=(reference,)),
        trace=TraceSnapshot(entries=(), source_refs=(reference,)),
    )


def test_project_snapshot_id_is_independent_of_built_at() -> None:
    """捕获把观察时间混进同一来源切面身份的实现。"""
    first = _snapshot("2026-09-01T00:00:00+00:00")
    second = _snapshot("2026-09-01T00:01:00+00:00")

    assert first.snapshot_id == second.snapshot_id


def test_project_snapshot_id_changes_with_source_head() -> None:
    first = _snapshot("2026-09-01T00:00:00+00:00")
    second = ProjectSnapshot.create(
        project_id=first.project_id,
        built_at=first.built_at,
        source_heads=(SourceHead("chapter_status", "status", "30", "c" * 64),),
        overview=first.overview,
        chapters=first.chapters,
        quality=first.quality,
        trace=first.trace,
    )

    assert first.snapshot_id != second.snapshot_id


def test_project_snapshot_is_immutable() -> None:
    snapshot = _snapshot("2026-09-01T00:00:00+00:00")

    with pytest.raises(FrozenInstanceError):
        snapshot.project_id = "other"  # type: ignore[misc]


def test_unknown_is_not_encoded_as_empty_project_stage() -> None:
    """捕获用空字符串掩盖未知状态的实现。"""
    with pytest.raises(ValueError, match="overview_current_stage_required"):
        OverviewSnapshot(
            current_stage="",
            run_status=ProjectRunStatus.UNKNOWN,
            chapter_count=0,
            blocked_chapter_count=0,
            source_refs=(),
        )
