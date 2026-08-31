from __future__ import annotations

from creative_os.domains.novel_writer import NovelWritingRequest
from creative_os.domains.novel_writer_prompt import (
    DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION,
    build_novel_writer_messages,
)
from creative_os.runtime import ModelMessage


def build_novel_writer_repair_messages(
    request: NovelWritingRequest,
    draft: str,
    missing_information: tuple[str, ...],
    system_instruction: str = DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION,
) -> list[ModelMessage]:
    """构造一次完整正文修复所需的模型消息。"""
    if not isinstance(draft, str) or not draft.strip() or not missing_information:
        raise ValueError("novel_writer_repair_input_invalid")
    if any(not isinstance(item, str) or not item.strip() for item in missing_information):
        raise ValueError("novel_writer_repair_input_invalid")

    original_messages = build_novel_writer_messages(request, system_instruction)
    missing = "\n".join(f"- {item}" for item in missing_information)
    repair_request = (
        "请完整重写下列小说正文，只输出可发布正文。"
        "重写完整章节，缺失信息必须逐字写入自然叙事，不得同义改写、概括或转述。"
        "不得输出分析、清单、代码块或系统术语。\n"
        f"缺失信息：\n{missing}\n"
        f"原正文：\n{draft}"
    )
    return [
        original_messages[0],
        ModelMessage("user", f"{original_messages[1].content}\n\n{repair_request}"),
    ]
