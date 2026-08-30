from __future__ import annotations

from creative_os.domains.narrative_decision import ChapterContract
from creative_os.domains.pov_strategy_model import ChapterNeeds


def chapter_needs_from_contract(contract: ChapterContract) -> ChapterNeeds:
    """从冻结合同提取稳定的 POV 需求，避免绑定自然语言场景动作。"""
    return ChapterNeeds(
        contract.functions,
        contract.dramatic_question,
        (),
        contract.scene_plan.required_world_slice,
        tuple(technology.id for technology in contract.technology_plan.technologies),
    )
