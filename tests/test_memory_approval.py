import json

import pytest

from creative_os.memory.approval import approve_candidate, archive_memory, reject_candidate
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryLifecycleError, MemoryScope, MemoryStatus
from creative_os.memory.store import JsonMemoryStore


def _seeded_store(tmp_path) -> JsonMemoryStore:
    store = JsonMemoryStore(tmp_path / "memory")
    store.add_candidate(
        MemoryItem.new_candidate(
            id="exp-001",
            kind=MemoryKind.EXPERIENCE,
            scope=MemoryScope.DOMAIN,
            scope_id="novel",
            title="控制章节开头",
            content="避免连续使用时间词开头。",
            evidence=[MemoryEvidence(source_type="review", source_id="review-1")],
        )
    )
    return store


def test_human_approval_activates_candidate_and_records_actor(tmp_path):
    store = _seeded_store(tmp_path)

    approved = approve_candidate(store, "exp-001", actor="tingyu", note="确认适用于长篇小说")

    assert approved.status == MemoryStatus.ACTIVE
    assert approved.approved_by == "tingyu"
    audit = json.loads(store.audit_path.read_text(encoding="utf-8").splitlines()[-1])
    assert audit["action"] == "approve"
    assert audit["actor"] == "tingyu"


def test_system_cannot_approve_candidate(tmp_path):
    store = _seeded_store(tmp_path)

    with pytest.raises(MemoryLifecycleError):
        approve_candidate(store, "exp-001", actor="system", note="automatic")

    assert store.get("exp-001").status == MemoryStatus.CANDIDATE


def test_candidate_can_be_rejected_and_active_memory_can_be_archived(tmp_path):
    rejected_store = _seeded_store(tmp_path / "rejected")
    rejected = reject_candidate(rejected_store, "exp-001", actor="tingyu", note="范围过宽")
    assert rejected.status == MemoryStatus.REJECTED

    active_store = _seeded_store(tmp_path / "active")
    approve_candidate(active_store, "exp-001", actor="tingyu", note="通过")
    archived = archive_memory(active_store, "exp-001", actor="tingyu", note="已过时")
    assert archived.status == MemoryStatus.ARCHIVED
