from dataclasses import replace

import pytest

from creative_os.domains.novel_writer import NovelWritingRequest
from creative_os.domains.novel_writer_prompt import (
    DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION,
)
from creative_os.domains.novel_writer_repair_prompt import (
    build_novel_writer_repair_messages,
)
from tests.test_narrative_director import _v2_decision
from tests.test_novel_scene_contract import _complete_scene


@pytest.fixture
def writing_request() -> NovelWritingRequest:
    decision = _v2_decision()
    scene_plan = replace(decision.chapter_contract.scene_plan, scenes=(_complete_scene(),))
    contract = replace(decision.chapter_contract, scene_plan=scene_plan)
    return NovelWritingRequest("chapter_001", contract, "a" * 64, "保持克制的现实语气")


def test_repair_messages_request_complete_rewrite_without_story_hardcoding(writing_request):
    messages = build_novel_writer_repair_messages(
        writing_request,
        "已有正文",
        ("事实甲", "事实乙"),
        DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION,
    )

    assert [item.role for item in messages] == ["system", "user"]
    assert "已有正文" in messages[1].content
    assert "事实甲" in messages[1].content and "事实乙" in messages[1].content
    assert "完整重写" in messages[1].content
    assert "逐字" in messages[1].content
    assert "只输出可发布正文" in messages[0].content
    assert "戏剧问题" in messages[1].content
    assert "保持克制的现实语气" in messages[1].content
    assert "文明升阶" not in messages[1].content


@pytest.mark.parametrize(
    ("draft", "missing_information"),
    [("   ", ("事实甲",)), ("已有正文", ())],
)
def test_repair_messages_rejects_empty_inputs(writing_request, draft, missing_information):
    with pytest.raises(ValueError, match="novel_writer_repair_input_invalid"):
        build_novel_writer_repair_messages(writing_request, draft, missing_information)


def test_repair_messages_rejects_blank_missing_information(writing_request):
    with pytest.raises(ValueError, match="novel_writer_repair_input_invalid"):
        build_novel_writer_repair_messages(writing_request, "已有正文", ("事实甲", "  "))
