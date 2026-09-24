from __future__ import annotations

from creative_os.projection.chapters import ChapterSnapshot, ChapterStatus
from creative_os.projection.model import ProjectSnapshot
from creative_os.projection.overview import OverviewSnapshot, ProjectRunStatus
from creative_os.projection.provenance import SourceHead, SourceRef
from creative_os.projection.quality import QualityIssueSnapshot, QualitySnapshot
from creative_os.projection.trace import TraceSnapshot
from creative_os.workspace_dto import (
    Freshness,
    OperationsSnapshot,
    ProjectionEnvelope,
    ProjectionSection,
    SectionEnvelope,
)
from creative_os.workspace_view_models import WorkspaceViewModelAdapter


HASH = "a" * 64


def _envelope() -> ProjectionEnvelope:
    project_ref = SourceRef("project", "book-a", "project.json", HASH)
    snapshot = ProjectSnapshot.create(
        project_id="book-a",
        built_at="2026-09-21T00:00:00+00:00",
        source_heads=(SourceHead("project", "book-a", content_hash=HASH),),
        overview=OverviewSnapshot("review", ProjectRunStatus.RUNNING, 3, 1, (project_ref,)),
        chapters=(
            ChapterSnapshot("chapter-002", 2, "Review the turning point", ChapterStatus.RUNNING, 2, 4.5, (project_ref,)),
            ChapterSnapshot("chapter-001", 1, "Opening", ChapterStatus.PASSED, 1, 2.0, (project_ref,)),
            ChapterSnapshot("chapter-003", 3, "Blocked ending", ChapterStatus.BLOCKED, 1, 0.0, (project_ref,)),
        ),
        quality=QualitySnapshot(
            (QualityIssueSnapshot("issue-1", "continuity", "error", True, "chapter:3", (project_ref,)),),
            (),
            (project_ref,),
        ),
        trace=TraceSnapshot((), (project_ref,)),
    )
    operations = OperationsSnapshot.from_project(snapshot)
    return ProjectionEnvelope(
        project_id="book-a",
        snapshot=snapshot,
        operations=operations,
        overall=Freshness.PARTIAL,
        sections={
            ProjectionSection.PROJECT: SectionEnvelope(Freshness.FRESH),
            ProjectionSection.OPERATIONS: SectionEnvelope(Freshness.PARTIAL),
        },
        source_heads=snapshot.source_heads,
        refresh_id="refresh-1",
    )


def test_overview_vm_exposes_priority_metrics_without_raw_projection_fields():
    view = WorkspaceViewModelAdapter().to_overview(_envelope())

    assert view.project_id == "book-a"
    assert view.freshness == Freshness.PARTIAL
    assert view.chapter_summary.total == 3
    assert view.chapter_summary.blocked == 1
    assert view.quality_summary.blocking == 1
    assert not hasattr(view, "source_heads")
    assert not hasattr(view, "snapshot")


def test_chapter_list_vm_filters_and_preserves_detail_key():
    view = WorkspaceViewModelAdapter().to_chapter_list(_envelope(), query="review")

    assert [item.detail_key for item in view.items] == ["chapter:2"]
    assert all("review" in item.status_label.lower() or "review" in item.title.lower() for item in view.items)
    assert view.total == 1
    assert view.items[0].chapter_number == 2


def test_chapter_list_vm_sorts_by_chapter_number_and_maps_status_semantically():
    view = WorkspaceViewModelAdapter().to_chapter_list(_envelope())

    assert [item.chapter_number for item in view.items] == [1, 2, 3]
    assert view.items[0].status_label == "已通过"
    assert view.items[2].status_label == "已阻塞"


def test_chapter_detail_vm_contains_traceable_evidence_without_projection_objects():
    view = WorkspaceViewModelAdapter().to_chapter_detail(_envelope(), 2)

    assert view.detail_key == "chapter:2"
    assert view.title == "Review the turning point"
    assert view.status_label == "运行中"
    assert view.attributes["attempts"] == 2
    assert view.evidence[0].locator == "project.json"
    assert not hasattr(view, "source_heads")
    assert not hasattr(view, "snapshot")


def test_unavailable_envelope_returns_explicit_empty_view_state():
    envelope = ProjectionEnvelope(
        project_id="book-a",
        snapshot=None,
        operations=None,
        overall=Freshness.UNAVAILABLE,
        sections={
            ProjectionSection.PROJECT: SectionEnvelope(Freshness.UNAVAILABLE),
            ProjectionSection.OPERATIONS: SectionEnvelope(Freshness.UNAVAILABLE),
        },
        source_heads=(),
    )

    overview = WorkspaceViewModelAdapter().to_overview(envelope)
    chapters = WorkspaceViewModelAdapter().to_chapter_list(envelope)

    assert overview.freshness == Freshness.UNAVAILABLE
    assert overview.chapter_summary.total == 0
    assert chapters.freshness == Freshness.UNAVAILABLE
    assert chapters.items == ()
    assert chapters.diagnostics
