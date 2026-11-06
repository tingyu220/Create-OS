import json

import pytest

from creative_os.publication_models import ChapterSnapshot, PauseMode, PublicationStatus, UnknownStatusError
from creative_os.publication_queue import PublicationQueue


def snap(book, number, revision="r1", content=None):
    return ChapterSnapshot(book, number, revision, content or f"{book}-{number}-{revision}")


def test_same_book_runs_in_chapter_order_and_other_books_are_independent():
    queue = PublicationQueue()
    queue.enqueue(snap("a", 2), "platform", "work-a")
    queue.enqueue(snap("a", 1), "platform", "work-a")
    queue.enqueue(snap("b", 2), "platform", "work-b")
    assert queue.next_ready("a").snapshot.chapter_number == 1
    assert queue.next_ready("b").snapshot.chapter_number == 2


def test_published_chapter_cannot_be_republished():
    queue = PublicationQueue()
    task = queue.enqueue(snap("a", 1), "p", "w")
    queue.start(task.operation_id)
    queue.complete(task.operation_id)
    assert queue.enqueue(snap("a", 1), "p", "w").operation_id == task.operation_id
    with pytest.raises(ValueError):
        queue.start(task.operation_id)


def test_revision_conflict_is_paused():
    queue = PublicationQueue()
    queue.enqueue(snap("a", 1, "r1"), "p", "w")
    conflict = queue.enqueue(snap("a", 1, "r2"), "p", "w")
    assert conflict.status is PublicationStatus.PAUSED
    assert conflict.pause_reason == "version_conflict"


def test_unknown_requires_reconcile_before_resume():
    queue = PublicationQueue()
    task = queue.enqueue(snap("a", 1), "p", "w")
    queue.start(task.operation_id)
    queue.mark_unknown(task.operation_id)
    with pytest.raises(UnknownStatusError):
        queue.resume(task.operation_id)
    queue.reconcile(task.operation_id, PublicationStatus.FAILED)
    queue.resume(task.operation_id)
    assert queue.get(task.operation_id).status is PublicationStatus.READY_TO_PUBLISH


def test_safe_pause_waits_for_checkpoint_and_immediate_pause_interrupts():
    queue = PublicationQueue()
    safe = queue.enqueue(snap("a", 1), "p", "w")
    queue.start(safe.operation_id)
    queue.pause("a", PauseMode.SAFE)
    assert queue.get(safe.operation_id).status is PublicationStatus.PUBLISHING
    queue.checkpoint(safe.operation_id, "fill_done")
    assert queue.get(safe.operation_id).status is PublicationStatus.PAUSED

    immediate = queue.enqueue(snap("b", 1), "p", "w2")
    queue.start(immediate.operation_id)
    queue.pause("b", PauseMode.IMMEDIATE)
    assert queue.get(immediate.operation_id).status is PublicationStatus.PAUSED
    assert queue.get(immediate.operation_id).checkpoint is not None


def test_duplicate_enqueue_reuses_operation_id_and_snapshot_round_trips():
    queue = PublicationQueue()
    first = queue.enqueue(snap("a", 1), "p", "w")
    second = queue.enqueue(snap("a", 1), "p", "w")
    assert first.operation_id == second.operation_id
    restored = PublicationQueue.from_json(queue.to_json())
    assert restored.get(first.operation_id).snapshot == first.snapshot
