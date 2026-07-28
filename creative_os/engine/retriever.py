from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from creative_os.foundation.knowledge import KnowledgeItem, KnowledgeStore
from creative_os.foundation.task import Task


class RetrievalMode(StrEnum):
    RULE = "rule"
    SEMANTIC = "semantic"


@dataclass(slots=True)
class RetrievalResult:
    items: list[KnowledgeItem]
    mode: RetrievalMode = RetrievalMode.RULE
    reasons: dict[str, list[str]] = field(default_factory=dict)
    scanned_all: bool = False


class RuleBasedRetriever:
    def __init__(self, limit: int = 8) -> None:
        self.limit = limit

    def retrieve(self, task: Task, store: KnowledgeStore, domain: object) -> list[KnowledgeItem]:
        return self.retrieve_with_metadata(task, store, domain).items

    def retrieve_with_metadata(self, task: Task, store: KnowledgeStore, domain: object) -> RetrievalResult:
        domain_tags = set(getattr(domain, "default_retrieval_tags", set()))
        tags = set(task.tags) | domain_tags
        if not tags:
            return RetrievalResult(items=[], reasons={}, scanned_all=False)
        items = store.find_by_tags(tags, limit=self.limit)
        reasons = {item.id: sorted(item.tags & tags) for item in items}
        return RetrievalResult(items=items, reasons=reasons, scanned_all=False)
