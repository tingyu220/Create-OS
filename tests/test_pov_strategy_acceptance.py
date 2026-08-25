import dataclasses
import hashlib
import json
from pathlib import Path

from creative_os.domains.pov_strategy_model import (
    CharacterPressure, ConsequenceRef, EvidenceRef, MainlineCapability, ProtagonistLoad,
)
from creative_os.domains.pov_strategy_planner import POVStrategyPlanner
from creative_os.domains.pov_strategy_policy import POVStrategyPolicy
from creative_os.domains.pov_strategy_review import review_pov_strategy
from tests.pov_strategy_helpers import state_ref, strategy_input


def test_24_26_consequences_recommend_protagonist_without_chapter_special_case():
    value, policy, expected = load_fixture("chapter_024_026_state")
    result = POVStrategyPlanner().plan(value, policy)
    assert result.recommended.primary_owner == expected
    assert result.recommended.protagonist_present is True
    assert {ref.source_id for ref in result.recommended.evidence_refs} >= {"chapter-024", "chapter-025", "chapter-026"}


def test_immediate_overseas_incident_can_keep_supporting_pov_with_arc_reason():
    value, policy, expected = load_fixture("overseas_incident_state")
    result = POVStrategyPlanner().plan(value, policy)
    assert result.recommended.primary_owner == expected
    assert result.recommended.protagonist_present is False
    assert "pov_transition_without_arc_reason" not in {risk.code for risk in review_pov_strategy(value, result, policy)}


def load_fixture(name):
    payload = json.loads((Path("tests/fixtures/pov_strategy") / f"{name}.json").read_text(encoding="utf-8"))
    refs = tuple(_evidence(source) for source in payload["unclaimed_sources"])
    consequences = tuple(ConsequenceRef(f"outcome-{index}", source, True, ("lin-zixuan",), "unclaimed", 24 + index, (ref,)) for index, (source, ref) in enumerate(zip(payload["unclaimed_sources"], refs)))
    protagonist = CharacterPressure(
        "lin-zixuan", (state_ref(),), (state_ref(),), (state_ref(),),
        (MainlineCapability("integrate", ("整合工程社会国际后果",), "mainline", refs),),
    )
    engineer = CharacterPressure(
        "overseas-engineer", (state_ref(),), (state_ref(),), (state_ref(),),
        (MainlineCapability("block-incident", ("阻断境外现场不可逆事故",), "overseas-site", refs),),
    )
    value = strategy_input(target=payload["target_chapter"], needs_function=payload["chapter_function"], pressures=(protagonist, engineer))
    value = dataclasses.replace(
        value,
        protagonist_load=ProtagonistLoad(3, 0, False, consequences),
        unclaimed_consequences=consequences,
        chapter_needs=dataclasses.replace(value.chapter_needs, required_scene_capabilities=(payload["required_capability"],)),
        evidence=refs,
        baseline_fingerprint="",
    ).with_fingerprint()
    return value, POVStrategyPolicy(protagonist_id="lin-zixuan"), payload["recommended"]


def _evidence(source):
    return EvidenceRef(source, "1", hashlib.sha256(source.encode()).hexdigest(), "contract:pov", "后果尚未承接")
