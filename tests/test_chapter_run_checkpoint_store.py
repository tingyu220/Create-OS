from pathlib import Path
import pytest
from creative_os.domains.chapter_run_checkpoint import ChapterRunCheckpoint, ChapterRunState
from creative_os.domains.chapter_run_checkpoint_store import ChapterRunCheckpointStore


def test_checkpoint_store_restarts_exactly_and_is_idempotent(tmp_path: Path):
    store = ChapterRunCheckpointStore(tmp_path)
    item = ChapterRunCheckpoint.initial("p", 1)
    assert store.append(item) == store.append(item)
    assert ChapterRunCheckpointStore(tmp_path).current("p", 1) == item


def test_checkpoint_store_rejects_tamper_and_conflicting_idempotency(tmp_path: Path):
    store = ChapterRunCheckpointStore(tmp_path)
    item = ChapterRunCheckpoint.initial("p", 1)
    store.append(item)
    from dataclasses import replace
    with pytest.raises(ValueError, match="conflict"):
        store.append(replace(item, checkpoint_hash="f" * 64))
    store.records_path.write_text(store.records_path.read_text(encoding="utf-8").replace('"sequence":1', '"sequence":2'), encoding="utf-8")
    with pytest.raises(ValueError, match="tampered"):
        store.recover()
