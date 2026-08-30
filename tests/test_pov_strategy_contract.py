from creative_os.domains.pov_strategy_contract import chapter_needs_from_contract
from tests.test_narrative_director import _v2_decision


def test_contract_needs_use_stable_technology_ids_not_scene_prose_or_role_labels():
    """防止场景文案或 core/supporting 标签变化导致已审批 POV 候选失效。"""
    contract = _v2_decision().chapter_contract

    needs = chapter_needs_from_contract(contract)

    assert needs.functions == contract.functions
    assert needs.dramatic_question == contract.dramatic_question
    assert needs.required_scene_capabilities == ()
    assert needs.required_world_slice == contract.scene_plan.required_world_slice
    assert needs.technology_roles == tuple(item.id for item in contract.technology_plan.technologies)
