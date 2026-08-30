import pytest

from creative_os.domains.narrative_decision import ChoiceStatus
from creative_os.domains.narrative_replay_model import (
    EvidenceRef, ReplayedChapterContract, ReplayedProtagonistChoice,
)
from creative_os.domains.narrative_replay_store import NarrativeReplayEvent, NarrativeReplayStore


@pytest.fixture
def valid_contract() -> ReplayedChapterContract:
    return ReplayedChapterContract(
        chapter_id="chapter_001",
        functions=("建立困境",),
        dramatic_question="主角会继续调查吗？",
        protagonist_choice=ReplayedProtagonistChoice(ChoiceStatus.UNKNOWN),
        evidence=(EvidenceRef("chapter", "production/final_chapters/chapter_001.md", "主角回城。"),),
    )


def test_store_rejects_non_contiguous_event_version(valid_contract):
    store = NarrativeReplayStore(project_id="validation_novel")

    with pytest.raises(ValueError, match="version"):
        store.append(NarrativeReplayEvent(2, "chapter_replayed", "chapter_001", valid_contract))


def test_store_rejects_event_chapter_mismatch(valid_contract):
    store = NarrativeReplayStore(project_id="validation_novel")

    with pytest.raises(ValueError, match="chapter"):
        store.append(NarrativeReplayEvent(1, "chapter_replayed", "chapter_002", valid_contract))


def test_store_projects_replayed_contract_as_frozen_snapshot(valid_contract):
    store = NarrativeReplayStore(project_id="validation_novel")

    state = store.append(NarrativeReplayEvent(1, "chapter_replayed", "chapter_001", valid_contract))

    assert state.version == 1
    assert state.chapter_contracts == (valid_contract,)
    assert store.snapshot() == state
    assert store.events() == (
        NarrativeReplayEvent(1, "chapter_replayed", "chapter_001", valid_contract),
    )
