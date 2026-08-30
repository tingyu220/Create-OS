import dataclasses

import pytest

from creative_os.domains.pov_strategy_model import CharacterPressure, MainlineCapability
from creative_os.domains.pov_strategy_planner import POVStrategyPlanner, POVStrategyPlanningError
from creative_os.domains.pov_strategy_policy import POVStrategyPolicy
from tests.pov_strategy_helpers import evidence, state_ref, strategy_input


def test_planner_prefers_function_capability_not_history_rotation():
    pressures = (
        CharacterPressure("observer", (state_ref(),), (state_ref(),), (state_ref(),),
                          (MainlineCapability("observe", ("观察",), "side", (evidence(),)),)),
        CharacterPressure("engineer", (state_ref(),), (state_ref(),), (state_ref(),),
                          (MainlineCapability("block", ("阻断事故",), "plant", (evidence(),)),)),
    )
    value = strategy_input(needs_function="阻断事故", pressures=pressures)
    result = POVStrategyPlanner().plan(value, POVStrategyPolicy(protagonist_id="hero"))
    assert result.recommended.primary_owner == "engineer"


def test_candidate_id_is_bound_to_the_input_fingerprint():
    value = strategy_input()

    result = POVStrategyPlanner().plan(value, POVStrategyPolicy())

    assert result.id == f"pov-strategy-027-{value.baseline_fingerprint}"


def test_planner_outlook_does_not_freeze_future_assignments():
    result = POVStrategyPlanner().plan(strategy_input(), POVStrategyPolicy())
    assert result.rhythm_outlook.horizon_chapters in {3, 4}
    assert "chapter_assignments" not in {field.name for field in dataclasses.fields(result.rhythm_outlook)}


def test_planner_blocks_when_no_character_can_serve_function():
    with pytest.raises(POVStrategyPlanningError, match="no_viable_pov_candidate"):
        POVStrategyPlanner().plan(strategy_input(needs_function="未知功能", pressures=()), POVStrategyPolicy())
