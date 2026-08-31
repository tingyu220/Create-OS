from dataclasses import replace

import pytest

from creative_os.domains.narrative_decision import SceneClosure
from creative_os.domains.novel_writer import NovelWritingRequest
from creative_os.domains.novel_writer_prompt import build_novel_writer_messages
from tests.test_narrative_director import _v2_decision
from tests.test_novel_scene_contract import _complete_scene


@pytest.fixture
def approved_decision():
    decision = _v2_decision()
    scene_plan = replace(decision.chapter_contract.scene_plan, scenes=(_complete_scene(),))
    return replace(
        decision,
        chapter_contract=replace(decision.chapter_contract, scene_plan=scene_plan),
    )


def _writing_request(decision, instruction: str) -> NovelWritingRequest:
    return NovelWritingRequest.from_narrative_decision(
        decision,
        context_fingerprint="a" * 64,
        instruction=instruction,
    )


def test_prompt_projects_approved_contract_without_work_specific_terms(approved_decision):
    request = _writing_request(approved_decision, "保持克制的现实语气")
    messages = build_novel_writer_messages(request, "只输出小说正文")
    rendered = "\n".join(item.content for item in messages)
    assert [item.role for item in messages] == ["system", "user"]
    assert "戏剧问题" in rendered
    assert "必要信息" in rendered
    assert "闭合要求" in rendered
    assert "保持克制的现实语气" in rendered
    assert "文明升阶" not in rendered


def test_prompt_strips_empty_system_and_supplemental_instructions(approved_decision):
    request = _writing_request(approved_decision, "   ")
    messages = build_novel_writer_messages(request, "  ")
    assert messages[0].content == ""
    assert "补充指令：无" in messages[1].content


def test_prompt_projects_enhanced_scene_semantics_and_closure(approved_decision):
    scene = approved_decision.chapter_contract.scene_plan.scenes[0]
    messages = build_novel_writer_messages(
        _writing_request(approved_decision, "补充语气"),
        "系统要求",
    )
    rendered = messages[1].content
    assert f"目的：{scene.narrative_purpose}" in rendered
    assert f"目标：{scene.goal}" in rendered
    assert f"冲突：{scene.conflict}" in rendered
    assert f"行动：{scene.action}" in rendered
    assert f"必要信息：{'；'.join(scene.essential_information)}" in rendered
    assert f"情绪变化：{scene.emotional_change}" in rendered
    assert "闭合要求：目标=True；冲突=True；选择=True；结果=True" in rendered


def test_prompt_requires_each_essential_information_verbatim_in_draft(approved_decision):
    messages = build_novel_writer_messages(
        _writing_request(approved_decision, "补充语气"),
        "系统要求",
    )
    rendered = messages[1].content

    assert "每条必要信息必须在正文中逐字出现" in rendered
    assert "不得同义改写" in rendered


def test_prompt_requires_complete_novel_scene_contract(approved_decision):
    chapter_contract = approved_decision.chapter_contract
    scene = chapter_contract.scene_plan.scenes[0]
    incomplete = replace(scene, closure=SceneClosure(True, True, True, False))
    scene_plan = replace(chapter_contract.scene_plan, scenes=(incomplete,))
    contract = replace(chapter_contract, scene_plan=scene_plan)
    decision = replace(approved_decision, chapter_contract=contract)

    with pytest.raises(ValueError, match="closure"):
        build_novel_writer_messages(_writing_request(decision, ""), "系统")
