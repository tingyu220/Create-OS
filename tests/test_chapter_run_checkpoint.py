import pytest
from creative_os.domains.chapter_run_checkpoint import ChapterRunState, ChapterRunCheckpoint, CheckpointError


def test_checkpoint_rejects_skipping_writer_and_quality_states():
    checkpoint = ChapterRunCheckpoint.initial("p", 1)
    with pytest.raises(CheckpointError, match="invalid_transition"):
        checkpoint.advance(ChapterRunState.CHAPTER_COMMITTED)


def test_checkpoint_accepts_explicit_prewrite_sequence_and_is_immutable():
    checkpoint = ChapterRunCheckpoint.initial("p", 1)
    next_checkpoint = checkpoint.advance(ChapterRunState.READINESS_APPROVED)
    assert next_checkpoint.sequence == 2
    assert checkpoint.state == ChapterRunState.AWAITING_READINESS_APPROVAL
