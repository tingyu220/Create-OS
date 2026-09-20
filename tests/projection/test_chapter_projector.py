from __future__ import annotations

from creative_os.projection.chapters import ChapterStatus
from creative_os.projection.projectors.chapters import project_chapters
from creative_os.projection.provenance import SourceRef
from creative_os.projection.source import (
    ChapterStatusFact,
    ChapterCheckpointFact,
    GateResultFact,
    ProjectFacts,
)


def _ref(kind: str, source_id: str) -> SourceRef:
    return SourceRef(kind, source_id, f"facts/{source_id}.json", "a" * 64)


def test_failed_gate_blocks_chapter_and_keeps_derivation() -> None:
    """捕获把阻塞状态压成无依据字符串的实现。"""
    status_ref = _ref("chapter_status", "chapter-029")
    gate_ref = _ref("review_gate", "gate-029")
    facts = ProjectFacts(
        project_id="book-a",
        chapter_statuses=(ChapterStatusFact(29, "pass", 1, 4.0, (), status_ref),),
        quality_issues=(),
        gate_results=(GateResultFact("gate-029", "failed", 29, gate_ref),),
        execution_events=(),
        runtime_reports=(),
        diagnostics=(),
        source_refs=(status_ref, gate_ref),
    )

    chapter = project_chapters(facts)[0]

    assert chapter.status is ChapterStatus.BLOCKED
    assert chapter.blocked_by[0].rule_id == "chapter.blocked_by_gate"
    assert chapter.blocked_by[0].inputs == (gate_ref,)


def test_missing_status_is_unknown_not_not_started() -> None:
    """捕获把缺失权威数据误写为“尚未开始”的实现。"""
    gate_ref = _ref("review_gate", "gate-001")
    facts = ProjectFacts(
        project_id="book-a",
        chapter_statuses=(),
        quality_issues=(),
        gate_results=(GateResultFact("gate-001", "passed", 1, gate_ref),),
        execution_events=(),
        runtime_reports=(),
        diagnostics=(),
        source_refs=(gate_ref,),
    )

    chapter = project_chapters(facts)[0]

    assert chapter.status is ChapterStatus.UNKNOWN


def test_checkpoint_state_is_projected_with_provenance() -> None:
    checkpoint_ref = _ref("chapter_checkpoint", "chapter-007")
    facts = ProjectFacts(
        project_id="book-a", chapter_statuses=(), quality_issues=(), gate_results=(),
        execution_events=(), runtime_reports=(), diagnostics=(), source_refs=(checkpoint_ref,),
        chapter_checkpoints=(ChapterCheckpointFact(7, "readiness_approved", 2, "b" * 64, ("readiness",), checkpoint_ref),),
    )

    chapter = project_chapters(facts)[0]

    assert chapter.checkpoint_state == "readiness_approved"
    assert checkpoint_ref in chapter.source_refs
    assert chapter.derivations[-1].rule_id == "chapter.checkpoint_state"
