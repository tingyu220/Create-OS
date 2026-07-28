from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class KnowledgeStatus(StrEnum):
    DRAFT = "draft"
    VERIFIED = "verified"
    ACTIVE = "active"
    ARCHIVED = "archived"


class KnowledgeCategory(StrEnum):
    DOMAIN = "domain"
    PROJECT = "project"
    EXTERNAL = "external"
    USER = "user"


class KnowledgeLifecycleError(ValueError):
    pass


class KnowledgeReferenceError(ValueError):
    pass


@dataclass(slots=True)
class KnowledgeItem:
    id: str
    kind: str
    title: str
    body: str
    category: KnowledgeCategory = KnowledgeCategory.PROJECT
    tags: set[str] = field(default_factory=set)
    references: set[str] = field(default_factory=set)
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE
    source_task_id: str | None = None


@dataclass(slots=True)
class CompiledKnowledge:
    items: list[KnowledgeItem] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


class KnowledgeStore:
    def __init__(self) -> None:
        self._items: dict[str, KnowledgeItem] = {}
        self._tag_index: dict[str, set[str]] = {}
        self._reference_index: dict[str, set[str]] = {}
        self._deleted_backups: list[KnowledgeItem] = []

    def add(self, item: KnowledgeItem) -> None:
        if item.id in self._items:
            raise ValueError(f"Knowledge already exists: {item.id}")
        self._validate_references(item)
        self._items[item.id] = item
        self._index(item)

    def apply(self, compiled: CompiledKnowledge) -> None:
        for item in compiled.items:
            self.upsert(item)

    def upsert(self, item: KnowledgeItem) -> None:
        old = self._items.get(item.id)
        self._validate_references(item)
        if old:
            self._unindex(old)
        self._items[item.id] = item
        self._index(item)

    def get(self, item_id: str) -> KnowledgeItem:
        return self._items[item_id]

    def items(self, include_archived: bool = False) -> list[KnowledgeItem]:
        values = list(self._items.values())
        if include_archived:
            return values
        return [item for item in values if item.status != KnowledgeStatus.ARCHIVED]

    def find_by_tags(self, tags: set[str], limit: int | None = None) -> list[KnowledgeItem]:
        if not tags:
            return []

        candidate_ids: set[str] = set()
        for tag in tags:
            candidate_ids.update(self._tag_index.get(tag, set()))

        ranked = sorted(
            (self._items[item_id] for item_id in candidate_ids),
            key=lambda item: (-len(item.tags & tags), item.id),
        )
        active = [item for item in ranked if item.status == KnowledgeStatus.ACTIVE]
        return active[:limit] if limit is not None else active

    def archive(self, item_id: str) -> None:
        item = self._items[item_id]
        self.upsert(
            KnowledgeItem(
                id=item.id,
                kind=item.kind,
                title=item.title,
                body=item.body,
                category=item.category,
                tags=item.tags,
                references=item.references,
                status=KnowledgeStatus.ARCHIVED,
                source_task_id=item.source_task_id,
            )
        )

    def transition(self, item_id: str, status: KnowledgeStatus) -> KnowledgeItem:
        item = self._items[item_id]
        if status not in self._allowed_next_statuses(item.status):
            raise KnowledgeLifecycleError(f"Invalid Knowledge lifecycle transition: {item.status} -> {status}")
        item.status = status
        return item

    def references_to(self, item_id: str) -> list[str]:
        referrers = self._reference_index.get(item_id, set())
        return sorted(referrer for referrer in referrers if referrer in self._items)

    def delete(self, item_id: str) -> KnowledgeItem:
        referrers = self.references_to(item_id)
        if referrers:
            raise KnowledgeReferenceError(f"Knowledge is referenced by: {', '.join(referrers)}")

        item = self._items[item_id]
        self._deleted_backups.append(item)
        self._unindex(item)
        del self._items[item_id]
        return item

    def deleted_backups(self) -> list[KnowledgeItem]:
        return list(self._deleted_backups)

    def _index(self, item: KnowledgeItem) -> None:
        for tag in item.tags:
            self._tag_index.setdefault(tag, set()).add(item.id)
        for reference in item.references:
            self._reference_index.setdefault(reference, set()).add(item.id)

    def _unindex(self, item: KnowledgeItem) -> None:
        for tag in item.tags:
            ids = self._tag_index.get(tag)
            if not ids:
                continue
            ids.discard(item.id)
            if not ids:
                del self._tag_index[tag]
        for reference in item.references:
            ids = self._reference_index.get(reference)
            if not ids:
                continue
            ids.discard(item.id)
            if not ids:
                del self._reference_index[reference]

    def _validate_references(self, item: KnowledgeItem) -> None:
        missing = [reference for reference in item.references if reference not in self._items and reference != item.id]
        if missing:
            raise KnowledgeReferenceError(f"Unknown Knowledge references: {', '.join(sorted(missing))}")

    def _allowed_next_statuses(self, current: KnowledgeStatus) -> set[KnowledgeStatus]:
        return {
            KnowledgeStatus.DRAFT: {KnowledgeStatus.VERIFIED, KnowledgeStatus.ARCHIVED},
            KnowledgeStatus.VERIFIED: {KnowledgeStatus.ACTIVE, KnowledgeStatus.DRAFT, KnowledgeStatus.ARCHIVED},
            KnowledgeStatus.ACTIVE: {KnowledgeStatus.ARCHIVED},
            KnowledgeStatus.ARCHIVED: {KnowledgeStatus.DRAFT},
        }[current]
