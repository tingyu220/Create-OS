from dataclasses import FrozenInstanceError, fields

import pytest

from creative_os.domains.narrative_decision import ChoiceStatus, ProtagonistChoice
from creative_os.domains.narrative_replay_model import (
    EvidenceRef,
    NarrativeReplayState,
    ReplayedChapterContract,
    ReplayedProtagonistChoice,
)


def _contract() -> ReplayedChapterContract:
    return ReplayedChapterContract(
        chapter_id="chapter_001",
        functions=("建立主角的初始困境",),
        dramatic_question="主角是否决定追查失踪事件？",
        protagonist_choice=ReplayedProtagonistChoice(
            status=ChoiceStatus.COMPLETE,
            actor="林澈",
            action="决定追查",
            alternatives=("离开雾城",),
            cost="暴露自身行踪",
            consequence="被监视者注意",
            missing_fields=(),
        ),
        evidence=(
            EvidenceRef(
                source_type="chapter",
                source_ref="production/final_chapters/chapter_001.md",
                excerpt="林澈决定追查林遥的去向。",
            ),
        ),
    )


def test_replayed_chapter_contract_requires_evidence_and_is_immutable():
    contract = _contract()

    contract.validate()
    with pytest.raises(FrozenInstanceError):
        contract.chapter_id = "chapter_002"


def test_replayed_chapter_contract_rejects_claim_without_evidence():
    contract = ReplayedChapterContract(
        chapter_id="chapter_001",
        functions=("推进主线",),
        dramatic_question="是否继续调查？",
        protagonist_choice=ReplayedProtagonistChoice(ChoiceStatus.UNKNOWN),
        evidence=(),
    )

    with pytest.raises(ValueError, match="evidence"):
        contract.validate()


def test_replay_model_rejects_formal_contract_choice_type():
    contract = _contract()
    formal = ProtagonistChoice("林澈", "追查", ("离开",), "暴露", "被监视")
    with pytest.raises(ValueError, match="audit-only"):
        ReplayedChapterContract(
            contract.chapter_id, contract.functions, contract.dramatic_question,
            formal, contract.evidence,
        ).validate()


def test_replay_state_does_not_store_manuscript_content():
    state = NarrativeReplayState(
        project_id="validation_novel",
        chapter_contracts=(_contract(),),
    )

    assert "prose" not in {field.name for field in fields(state)}
    assert "manuscript" not in {field.name for field in fields(state)}
