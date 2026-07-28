from creative_os.domains.novel import NovelDomainPackage
from creative_os.engine.retriever import RetrievalMode, RuleBasedRetriever
from creative_os.foundation.knowledge import KnowledgeItem, KnowledgeStatus, KnowledgeStore
from creative_os.foundation.task import Task


def test_retriever_returns_minimal_ranked_knowledge_with_reasons():
    store = KnowledgeStore()
    store.add(KnowledgeItem(id="k1", kind="character", title="林澈", body="主角。", tags={"林澈", "character"}))
    store.add(KnowledgeItem(id="k2", kind="world", title="雾城", body="夜晚不能点灯。", tags={"雾城", "world"}))
    store.add(KnowledgeItem(id="k3", kind="note", title="无关资料", body="不应进入。", tags={"无关"}))
    store.add(KnowledgeItem(id="k4", kind="old", title="归档资料", body="不应进入。", tags={"林澈"}, status=KnowledgeStatus.ARCHIVED))

    task = Task(id="t1", title="写雾城场景", kind="writing", domain="novel", goal="写林澈进入雾城", tags={"林澈", "雾城"})
    result = RuleBasedRetriever(limit=2).retrieve_with_metadata(task, store, NovelDomainPackage())

    assert result.mode == RetrievalMode.RULE
    assert [item.id for item in result.items] == ["k1", "k2"]
    assert result.scanned_all is False
    assert result.reasons["k1"] == ["林澈"]
    assert result.reasons["k2"] == ["雾城"]


def test_retriever_returns_empty_result_for_task_without_retrieval_tags():
    store = KnowledgeStore()
    store.add(KnowledgeItem(id="k1", kind="note", title="资料", body="不应被全量扫描。", tags={"资料"}))
    task = Task(id="t1", title="无标签任务", kind="writing", domain="novel", goal="不扫描全库")

    result = RuleBasedRetriever().retrieve_with_metadata(task, store, NovelDomainPackage())

    assert result.items == []
    assert result.scanned_all is False
