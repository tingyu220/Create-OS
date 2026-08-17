from __future__ import annotations

from dataclasses import dataclass, field

from creative_os.memory.model import MemoryItem, MemoryScope, MemoryStatus
from creative_os.memory.store import JsonMemoryStore


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    task_id: str
    project_id: str
    user_id: str
    domain: str
    task_kind: str
    tags: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class MemoryRetrievalResult:
    items: list[MemoryItem]
    reasons: dict[str, list[str]]


class MemoryRetriever:
    def retrieve(
        self,
        query: MemoryQuery,
        stores: list[JsonMemoryStore],
        limit: int = 8,
    ) -> MemoryRetrievalResult:
        candidates: dict[str, MemoryItem] = {}
        reasons: dict[str, list[str]] = {}
        for store in stores:
            for item in store.list():
                item_reasons = self._match_reasons(item, query)
                if item_reasons is None:
                    continue
                candidates.setdefault(item.id, item)
                reasons[item.id] = item_reasons

        ranked = sorted(candidates.values(), key=lambda item: self._rank(item, query))[:limit]
        selected_reasons = {item.id: reasons[item.id] for item in ranked}
        return MemoryRetrievalResult(items=ranked, reasons=selected_reasons)

    def _match_reasons(self, item: MemoryItem, query: MemoryQuery) -> list[str] | None:
        if item.status != MemoryStatus.ACTIVE:
            return None
        expected_scope_id = {
            MemoryScope.TASK: query.task_id,
            MemoryScope.PROJECT: query.project_id,
            MemoryScope.USER: query.user_id,
            MemoryScope.DOMAIN: query.domain,
            MemoryScope.GLOBAL: item.scope_id,
        }[item.scope]
        if item.scope_id != expected_scope_id:
            return None
        if item.applicability and query.task_kind not in item.applicability:
            return None

        reasons = [f"scope:{item.scope.value}"]
        reasons.extend(f"tag:{tag}" for tag in sorted(item.tags & query.tags))
        if item.applicability:
            reasons.append(f"applicability:{query.task_kind}")
        return reasons

    def _rank(self, item: MemoryItem, query: MemoryQuery) -> tuple[int, int, float, str]:
        scope_rank = {
            MemoryScope.TASK: 0,
            MemoryScope.PROJECT: 1,
            MemoryScope.USER: 2,
            MemoryScope.DOMAIN: 3,
            MemoryScope.GLOBAL: 4,
        }[item.scope]
        return (-len(item.tags & query.tags), scope_rank, -item.confidence, item.id)
