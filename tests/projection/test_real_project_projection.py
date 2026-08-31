from __future__ import annotations

from pathlib import Path

from creative_os.projection.builder import ProjectProjectionBuilder, ProjectProjectionRequest
from creative_os.projection.chapters import ChapterStatus
from creative_os.projection.filesystem_source import FilesystemProjectSource


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_independent_writer_validation_builds_traceable_snapshot() -> None:
    """证明统一投影读取真实独立 Writer 产物，而非测试伪数据。"""
    project = REPO_ROOT / "projects" / "novel_domain_validation"
    source = FilesystemProjectSource(project)

    result = ProjectProjectionBuilder(source).build(
        ProjectProjectionRequest(project_id="novel-domain-validation")
    )

    snapshot = result.snapshot
    assert snapshot.project_id == "novel-domain-validation"
    assert snapshot.overview.current_stage == "complete"
    assert snapshot.chapters[0].status is ChapterStatus.PASSED
    assert snapshot.chapters[0].source_refs
    assert len(snapshot.quality.gate_results) == 2
    assert {entry.trace_kind for entry in snapshot.trace.entries} == {"runtime_report"}
    assert all(not reference.locator.startswith(("/", "D:", "C:")) for reference in snapshot.overview.source_refs)


def test_civilization_project_uses_status_and_event_log_without_modifying_them() -> None:
    project = REPO_ROOT / "projects" / "文明升阶"
    source = FilesystemProjectSource(project)
    before = source.read_head()

    result = ProjectProjectionBuilder(source).build(ProjectProjectionRequest(project_id="文明升阶"))

    assert [item.chapter_number for item in result.snapshot.chapters][-4:] == [29, 30, 31, 32]
    assert result.snapshot.trace.entries
    assert source.read_head() == before


def test_real_project_snapshot_exposes_story_threads_section() -> None:
    project = REPO_ROOT / "projects" / "文明升阶"

    result = ProjectProjectionBuilder(FilesystemProjectSource(project)).build(
        ProjectProjectionRequest(project_id="文明升阶")
    )

    assert len(result.snapshot.story_threads) == 5
    assert {item.thread_type for item in result.snapshot.story_threads} == {"foreshadow"}
    assert all(item.open_loop is None for item in result.snapshot.story_threads)
    assert any(item.code == "story_thread_open_loop_unproven" for item in result.snapshot.diagnostics)
