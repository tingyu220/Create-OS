from __future__ import annotations

from creative_os.llm_writer import ModelMessage


LOCAL_ONLY_ISSUES = {"time_word_opener"}
LOCAL_PREFIXES = ("reader_term:",)


def detect_repair_scope(issues: list[str]) -> str:
    for issue in issues:
        if issue in LOCAL_ONLY_ISSUES:
            continue
        if issue.startswith(LOCAL_PREFIXES):
            continue
        return "full"
    return "local"


def build_local_repair_messages(chapter_text: str, issues: list[str]) -> list[ModelMessage]:
    return [
        ModelMessage(role="system", content="你是小说局部修复 Agent。只输出修复后的完整章节正文。"),
        ModelMessage(
            role="user",
            content=(
                "请只修复以下读者可见问题，不改变剧情事实、人物关系和章节长度：\n"
                + "\n".join(f"- {issue}" for issue in issues)
                + "\n\n原章节：\n"
                + chapter_text
            ),
        ),
    ]
