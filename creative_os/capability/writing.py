from __future__ import annotations

from creative_os.capability.base import Result, ResultKind
from creative_os.engine.context import Context


class TemplateWritingCapability:
    def run(self, context: Context) -> Result:
        knowledge_titles = ", ".join(item.title for item in context.knowledge) or "无"
        content = (
            f"Task: {context.task.title}\n"
            f"Goal: {context.task.goal}\n"
            f"User Input: {context.user_input}\n"
            f"Knowledge Used: {knowledge_titles}\n"
            f"Draft: 围绕「{context.user_input}」生成一段可继续扩展的创作结果。"
        )
        return Result(content=content, kind=ResultKind.WRITING)
