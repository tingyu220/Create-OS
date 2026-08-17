from dataclasses import FrozenInstanceError

import pytest

from creative_os.memory.model import (
    MemoryEvidence,
    MemoryItem,
    MemoryKind,
    MemoryLifecycleError,
    MemoryScope,
    MemoryStatus,
    MemoryValidationError,
)


def _candidate() -> MemoryItem:
    return MemoryItem.new_candidate(
        id="exp-001",
        kind=MemoryKind.EXPERIENCE,
        scope=MemoryScope.DOMAIN,
        scope_id="novel",
        title="避免模板化章节开头",
        content="章节开头不应连续使用统一时间词。",
        evidence=[MemoryEvidence(source_type="review", source_id="run-12", note="连续章节命中")],
    )


def test_experience_starts_as_candidate_with_scope_and_evidence():
    item = _candidate()

    assert item.status == MemoryStatus.CANDIDATE
    assert item.version == 1
    assert item.scope_id == "novel"
    assert item.evidence[0].source_id == "run-12"


def test_candidate_cannot_activate_without_manual_approval():
    with pytest.raises(MemoryLifecycleError):
        _candidate().activate(actor="system")


def test_human_can_activate_candidate_without_mutating_original():
    candidate = _candidate()

    active = candidate.activate(actor="tingyu")

    assert candidate.status == MemoryStatus.CANDIDATE
    assert active.status == MemoryStatus.ACTIVE
    assert active.approved_by == "tingyu"
    with pytest.raises(FrozenInstanceError):
        active.content = "changed"  # type: ignore[misc]


def test_candidate_requires_scope_id_and_evidence():
    with pytest.raises(MemoryValidationError):
        MemoryItem.new_candidate(
            id="exp-invalid",
            kind=MemoryKind.EXPERIENCE,
            scope=MemoryScope.DOMAIN,
            scope_id="",
            title="无作用域",
            content="不能保存。",
            evidence=[],
        )
