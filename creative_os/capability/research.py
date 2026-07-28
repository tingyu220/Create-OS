from __future__ import annotations

from collections.abc import Callable

from creative_os.capability.base import KnowledgeDraft, Result, ResultKind
from creative_os.engine.context import Context


class ProviderResearchCapability:
    def __init__(self, provider: Callable[[str], str] | None = None) -> None:
        self.provider = provider or (lambda query: "")

    def run(self, context: Context) -> Result:
        draft = self.provider(context.task.goal)
        body = draft or f"Knowledge Draft: {context.task.goal}"
        knowledge_draft = KnowledgeDraft(
            title=context.task.goal,
            body=body,
            tags=set(context.task.tags),
            source="provider",
        )
        return Result(content=body, kind=ResultKind.RESEARCH, knowledge_drafts=[knowledge_draft])
