from dataclasses import replace

import pytest

from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import (
    NarrativeValidationError,
    SceneClosure,
)
from tests.test_narrative_director import _v2_decision


def _complete_scene():
    scene = _v2_decision().chapter_contract.scene_plan.scenes[0]
    return replace(
        scene,
        narrative_purpose="迫使主角以现场行动确认旧图缺失",
        essential_information=("旧图缺失", "试验暂停"),
        emotional_change="从怀疑转为承担停机代价",
        closure=SceneClosure(True, True, True, True),
    )


@pytest.mark.parametrize(
    "changes,match",
    [
        ({"narrative_purpose": ""}, "narrative_purpose"),
        ({"essential_information": ()}, "essential_information"),
        ({"emotional_change": ""}, "emotional_change"),
        ({"closure": SceneClosure(True, True, False, True)}, "closure"),
    ],
)
def test_scene_contract_requires_novel_semantics_when_domain_gate_is_active(changes, match):
    scene = replace(_complete_scene(), **changes)

    with pytest.raises(NarrativeValidationError, match=match):
        scene.validate(novel_required=True)


def test_scene_contract_novel_semantics_survive_codec_round_trip():
    decision = _v2_decision()
    scene = _complete_scene()
    plan = replace(decision.chapter_contract.scene_plan, scenes=(scene,))
    decision = replace(decision, chapter_contract=replace(decision.chapter_contract, scene_plan=plan))

    decoded = NarrativeDecisionCodec.decode_v2(NarrativeDecisionCodec.encode_v2(decision))

    assert decoded == decision
    assert decoded.chapter_contract.scene_plan.scenes[0].closure.complete
