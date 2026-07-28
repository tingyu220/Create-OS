from __future__ import annotations

import hashlib

from creative_os.capability.base import Result, ResultKind
from creative_os.engine.context import Context
from creative_os.foundation.knowledge import CompiledKnowledge, KnowledgeCategory, KnowledgeItem, KnowledgeStatus


class KnowledgeCompiler:
    def compile(self, result: Result, context: Context, domain: object) -> CompiledKnowledge:
        if result.kind == ResultKind.RESEARCH:
            return self._compile_research(result, context)
        return self._compile_structured_result(result, context)

    def _compile_research(self, result: Result, context: Context) -> CompiledKnowledge:
        items: list[KnowledgeItem] = []
        for index, draft in enumerate(result.knowledge_drafts, start=1):
            item_id = f"research-{context.task.id}-{index}"
            items.append(
                KnowledgeItem(
                    id=item_id,
                    category=KnowledgeCategory.EXTERNAL,
                    kind="research_draft",
                    title=draft.title,
                    body=draft.body,
                    tags=set(draft.tags) | {context.task.domain, "research"},
                    status=KnowledgeStatus.DRAFT,
                    source_task_id=context.task.id,
                )
            )
        return CompiledKnowledge(items=items, issues=[issue.code for issue in result.issues])

    def _compile_structured_result(self, result: Result, context: Context) -> CompiledKnowledge:
        items: list[KnowledgeItem] = []
        summary_seen = False
        for line in result.content.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("Entity:"):
                items.append(self._entity_item(line.removeprefix("Entity:").strip(), context))
            elif line.startswith("Fact:"):
                items.append(self._simple_item("fact", line.removeprefix("Fact:").strip(), context))
            elif line.startswith("Relationship:"):
                items.append(self._relationship_item(line.removeprefix("Relationship:").strip(), context))
            elif line.startswith("Summary:"):
                summary_seen = True
                items.append(self._simple_item("summary", line.removeprefix("Summary:").strip(), context, stable_id=f"summary-{context.task.id}"))

        if not items or not summary_seen:
            items.append(
                KnowledgeItem(
                    id=f"summary-{context.task.id}",
                    category=KnowledgeCategory.PROJECT,
                    kind="summary",
                    title=f"{context.task.title} Summary",
                    body=result.content,
                    tags=set(context.task.tags) | {context.task.domain, context.task.kind, "summary"},
                    source_task_id=context.task.id,
                )
            )
        return CompiledKnowledge(items=items, issues=[issue.code for issue in result.issues])

    def _entity_item(self, payload: str, context: Context) -> KnowledgeItem:
        parts = [part.strip() for part in payload.split("|")]
        title = parts[0] if parts else "Entity"
        entity_kind = parts[1] if len(parts) > 1 else "entity"
        body = parts[2] if len(parts) > 2 else payload
        return KnowledgeItem(
            id=self._stable_id("entity", context.task.id, payload),
            category=KnowledgeCategory.PROJECT,
            kind="entity",
            title=title,
            body=body,
            tags=set(context.task.tags) | {context.task.domain, "entity", entity_kind, title},
            source_task_id=context.task.id,
        )

    def _relationship_item(self, payload: str, context: Context) -> KnowledgeItem:
        return KnowledgeItem(
            id=self._stable_id("relationship", context.task.id, payload),
            category=KnowledgeCategory.PROJECT,
            kind="relationship",
            title=payload.split("|")[0].strip(),
            body=payload,
            tags=set(context.task.tags) | {context.task.domain, "relationship"},
            source_task_id=context.task.id,
        )

    def _simple_item(self, kind: str, payload: str, context: Context, stable_id: str | None = None) -> KnowledgeItem:
        return KnowledgeItem(
            id=stable_id or self._stable_id(kind, context.task.id, payload),
            category=KnowledgeCategory.PROJECT,
            kind=kind,
            title=f"{context.task.title} {kind}",
            body=payload,
            tags=set(context.task.tags) | {context.task.domain, kind},
            source_task_id=context.task.id,
        )

    def _stable_id(self, prefix: str, task_id: str, payload: str) -> str:
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
        return f"{prefix}-{task_id}-{digest}"
