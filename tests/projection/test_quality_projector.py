from __future__ import annotations

from creative_os.projection.projectors.quality import project_quality
from creative_os.projection.provenance import SourceRef
from creative_os.projection.source import ExecutionEventFact, ProjectFacts, QualityIssueFact


def test_quality_preserves_warning_without_promoting_it() -> None:
    """捕获 Projection 擅自创造领域严重度或阻塞事实的实现。"""
    reference = SourceRef("review", "review-001", "reviews/001.json", "b" * 64)
    facts = ProjectFacts(
        project_id="book-a",
        chapter_statuses=(),
        quality_issues=(QualityIssueFact("issue-1", "repetition", "warning", False, "chapter_001", reference),),
        gate_results=(),
        execution_events=(),
        runtime_reports=(),
        diagnostics=(),
        source_refs=(reference,),
    )

    quality = project_quality(facts)

    assert quality.issues[0].severity == "warning"
    assert quality.issues[0].blocking is False
    assert quality.blocking_count == 0
    assert quality.issues[0].source_refs == (reference,)


def test_quality_matches_accepted_event_by_issue_id() -> None:
    issue_ref = SourceRef("review", "review-001", "reviews/001.json", "b" * 64)
    event_ref = SourceRef("event", "event-001", "events/001.json", "c" * 64)
    facts = ProjectFacts(
        project_id="book-a",
        chapter_statuses=(),
        quality_issues=(QualityIssueFact("issue-1", "repetition", "warning", False, "chapter_001", issue_ref),),
        gate_results=(),
        execution_events=(ExecutionEventFact(
            "event-001", "ReviewIssueAccepted", "2026-09-14T00:00:00+00:00", 1,
            None, None, '{"issue_id":"issue-1"}', event_ref,
        ),),
        runtime_reports=(),
        diagnostics=(),
        source_refs=(issue_ref, event_ref),
    )

    quality = project_quality(facts)

    assert quality.issues[0].disposition_status == "accepted"
    assert quality.issues[0].source_refs == (issue_ref, event_ref)
