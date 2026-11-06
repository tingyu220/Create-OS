import hashlib
import json
import pytest

from creative_os.publication_models import (
    PublicationStatus, PauseMode, ChapterSnapshot, PublicationCheckpoint,
    PublicationLedgerEntry, IdempotencyRegistry, UnknownStatusError,
)


def test_status_and_pause_enums_cover_contract():
    assert {s.value for s in PublicationStatus} == {
        "writing", "checking", "ready_to_fill", "filling", "ready_to_publish",
        "publishing", "verifying", "published", "failed", "unknown", "paused",
    }
    assert {p.value for p in PauseMode} == {"safe", "immediate"}


def test_snapshot_hash_and_immutable():
    snap = ChapterSnapshot("book-1", 2, "rev-3", "正文")
    assert snap.content_sha256 == hashlib.sha256("正文".encode()).hexdigest()
    with pytest.raises((AttributeError, TypeError)):
        snap.content = "改写"


def test_checkpoint_serialization_roundtrip_and_unknown_gate():
    cp = PublicationCheckpoint("book-1", 2, "rev-3", "verifying", "op-1", "abc", PauseMode.immediate, "query platform")
    restored = PublicationCheckpoint.from_json(cp.to_json())
    assert restored == cp
    with pytest.raises(UnknownStatusError):
        restored.require_reconciled()
    reconciled = restored.mark_reconciled(PublicationStatus.published)
    assert reconciled.status is PublicationStatus.published


def test_ledger_roundtrip():
    entry = PublicationLedgerEntry("tomato", "work-1", "chapter-2", PublicationStatus.published, "2026-10-28T10:00:00Z", "evidence://1", "op-1")
    assert PublicationLedgerEntry.from_dict(json.loads(entry.to_json())) == entry


def test_idempotency_same_key_returns_same_operation_id():
    registry = IdempotencyRegistry()
    first = registry.submit("tomato", "work-1", 2, "rev-3", "hash")
    second = registry.submit("tomato", "work-1", 2, "rev-3", "hash")
    assert first == second
    assert registry.key("tomato", "work-1", 2, "rev-3", "hash")
