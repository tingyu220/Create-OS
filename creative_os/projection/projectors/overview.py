from __future__ import annotations

from creative_os.projection.chapters import ChapterSnapshot, ChapterStatus, StageStatus
from creative_os.projection.overview import OverviewBlocker, OverviewSnapshot, ProjectRunStatus
from creative_os.projection.quality import QualitySnapshot
from creative_os.projection.trace import TraceSnapshot


def project_overview(
    *,
    chapters: tuple[ChapterSnapshot, ...],
    quality: QualitySnapshot,
    trace: TraceSnapshot,
) -> OverviewSnapshot:
    blocked = tuple(item for item in chapters if item.status is ChapterStatus.BLOCKED)
    failed = tuple(item for item in chapters if item.status is ChapterStatus.FAILED)
    running = tuple(item for item in chapters if item.status is ChapterStatus.RUNNING)
    if blocked or quality.blocking_count or any(item.status == "failed" for item in quality.gate_results):
        run_status = ProjectRunStatus.BLOCKED
    elif failed:
        run_status = ProjectRunStatus.FAILED
    elif running:
        run_status = ProjectRunStatus.RUNNING
    elif chapters and all(item.status is ChapterStatus.PASSED for item in chapters):
        run_status = ProjectRunStatus.PASSED
    else:
        run_status = ProjectRunStatus.UNKNOWN

    blockers = tuple(
        OverviewBlocker(
            code=f"chapter_blocked:{chapter.chapter_id}",
            message=f"{chapter.chapter_id} 被权威 Gate 或 Issue 阻塞。",
            derivation=derivation,
        )
        for chapter in blocked
        for derivation in chapter.blocked_by
    )
    references = tuple(dict.fromkeys([
        *(ref for chapter in chapters for ref in chapter.source_refs),
        *quality.source_refs,
        *trace.source_refs,
    ]))
    return OverviewSnapshot(
        current_stage=_current_stage(chapters),
        run_status=run_status,
        chapter_count=len(chapters),
        blocked_chapter_count=len(blocked),
        source_refs=references,
        blockers=blockers,
    )


def _current_stage(chapters: tuple[ChapterSnapshot, ...]) -> str:
    if not chapters:
        return "unknown"
    latest = max(chapters, key=lambda item: item.chapter_number)
    for stage in latest.stages:
        if stage.status in {StageStatus.RUNNING, StageStatus.BLOCKED, StageStatus.FAILED}:
            return stage.stage.value
    if latest.stages and all(stage.status is StageStatus.PASSED for stage in latest.stages):
        return "complete"
    return "unknown"
