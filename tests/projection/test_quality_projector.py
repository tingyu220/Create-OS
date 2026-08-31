from __future__ import annotations

from creative_os.projection.projectors.quality import project_quality
from creative_os.projection.provenance import SourceRef
from creative_os.projection.source import ProjectFacts, QualityIssueFact


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
