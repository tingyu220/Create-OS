from __future__ import annotations

from collections import deque

import pytest

from creative_os.projection.builder import (
    ProjectProjectionBuilder,
    ProjectProjectionRequest,
    ProjectionProjectMismatchError,
)
from creative_os.projection.provenance import SourceHead
from creative_os.projection.source import ProjectFacts


def _head(cursor: str) -> tuple[SourceHead, ...]:
    return (SourceHead("runtime_event_log", "runtime", cursor, "f" * 64),)


def _facts(project_id: str = "book-a") -> ProjectFacts:
    return ProjectFacts(project_id, (), (), (), (), (), (), ())


class SequencedSource:
    def __init__(self, heads: tuple[tuple[SourceHead, ...], ...], facts: ProjectFacts | None = None) -> None:
        self.heads = deque(heads)
        self.facts = facts or _facts()
        self.fact_reads = 0

    def read_head(self) -> tuple[SourceHead, ...]:
        return self.heads.popleft()

    def read_facts(self, cursor=None) -> ProjectFacts:
        self.fact_reads += 1
        return self.facts


def test_builder_discards_drifted_attempt_and_retries() -> None:
    """捕获把两个来源时刻拼进同一快照的实现。"""
    source = SequencedSource((_head("1:event-1"), _head("2:event-2"), _head("2:event-2"), _head("2:event-2")))
    builder = ProjectProjectionBuilder(source, max_attempts=2, clock=lambda: "2026-09-01T00:00:00+00:00")

    result = builder.build(ProjectProjectionRequest(project_id="book-a"))

    assert result.attempts == 2
    assert source.fact_reads == 2
    assert result.snapshot.source_heads == _head("2:event-2")
    assert result.refresh_mode == "full"


def test_builder_rejects_fact_package_from_another_project() -> None:
    source = SequencedSource((_head("1:event-1"), _head("1:event-1")), facts=_facts("book-b"))
    builder = ProjectProjectionBuilder(source, clock=lambda: "2026-09-01T00:00:00+00:00")

    with pytest.raises(ProjectionProjectMismatchError, match="projection_project_mismatch"):
        builder.build(ProjectProjectionRequest(project_id="book-a"))
