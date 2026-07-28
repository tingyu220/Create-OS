import pytest

from creative_os.foundation.knowledge import (
    KnowledgeCategory,
    KnowledgeItem,
    KnowledgeLifecycleError,
    KnowledgeReferenceError,
    KnowledgeStatus,
    KnowledgeStore,
)


def test_knowledge_item_has_category_and_enforced_lifecycle():
    store = KnowledgeStore()
    store.add(
        KnowledgeItem(
            id="k1",
            category=KnowledgeCategory.PROJECT,
            kind="fact",
            title="主角目标",
            body="林澈要寻找失踪的妹妹。",
            status=KnowledgeStatus.DRAFT,
            tags={"林澈"},
        )
    )

    with pytest.raises(KnowledgeLifecycleError):
        store.transition("k1", KnowledgeStatus.ACTIVE)

    store.transition("k1", KnowledgeStatus.VERIFIED)
    store.transition("k1", KnowledgeStatus.ACTIVE)

    item = store.get("k1")
    assert item.category == KnowledgeCategory.PROJECT
    assert item.status == KnowledgeStatus.ACTIVE


def test_references_block_hard_delete_and_archive_removes_from_retrieval():
    store = KnowledgeStore()
    store.add(
        KnowledgeItem(
            id="character-lin",
            category=KnowledgeCategory.PROJECT,
            kind="character",
            title="林澈",
            body="主角。",
            tags={"林澈"},
        )
    )
    store.add(
        KnowledgeItem(
            id="scene-1",
            category=KnowledgeCategory.PROJECT,
            kind="event",
            title="进入雾城",
            body="林澈进入雾城。",
            references={"character-lin"},
            tags={"雾城"},
        )
    )

    assert store.references_to("character-lin") == ["scene-1"]

    with pytest.raises(KnowledgeReferenceError):
        store.delete("character-lin")

    store.archive("character-lin")

    assert store.get("character-lin").status == KnowledgeStatus.ARCHIVED
    assert store.find_by_tags({"林澈"}) == []


def test_delete_keeps_backup_before_removing_unreferenced_item():
    store = KnowledgeStore()
    store.add(
        KnowledgeItem(
            id="external-1",
            category=KnowledgeCategory.EXTERNAL,
            kind="source",
            title="唐朝县令资料",
            body="外部资料草稿。",
            status=KnowledgeStatus.DRAFT,
            tags={"唐朝"},
        )
    )

    deleted = store.delete("external-1")

    assert deleted.id == "external-1"
    assert store.deleted_backups()[0].id == "external-1"
    assert "external-1" not in [item.id for item in store.items(include_archived=True)]
