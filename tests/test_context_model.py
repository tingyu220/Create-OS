import pytest

from creative_os.domains.novel import NovelDomainPackage
from creative_os.engine.context import ContextBuilder, ContextBoundaryError
from creative_os.foundation.knowledge import KnowledgeItem
from creative_os.foundation.state import ProjectState
from creative_os.foundation.task import Task


def test_context_builder_composes_runtime_package_with_size_limits():
    domain = NovelDomainPackage()
    task = Task(id="t1", title="写 Scene", kind="writing", domain="novel", goal="写场景", tags={"林澈"})
    state = ProjectState(
        current_phase="Draft",
        current_task_id="t1",
        current_goal="完成 Scene",
        active_domain="novel",
    )
    retrieved = [
        KnowledgeItem(id="k1", kind="character", title="林澈", body="主角", tags={"林澈"}),
        KnowledgeItem(id="k2", kind="world", title="雾城", body="不能点灯", tags={"雾城"}),
    ]

    context = ContextBuilder(max_items=1, max_chars=1000).build(
        user_input="保持悬疑",
        task=task,
        state=state,
        retrieved=retrieved,
        domain=domain,
    )

    assert context.task.id == "t1"
    assert context.state.current_task_id == "t1"
    assert [item.id for item in context.knowledge] == ["k1"]
    assert "character_consistency" in context.domain_rules
    assert context.size_chars <= 1000


def test_context_builder_rejects_domain_and_task_mismatch():
    domain = NovelDomainPackage()
    task = Task(id="t1", title="写文章", kind="writing", domain="article", goal="写文章")
    state = ProjectState(
        current_phase="Draft",
        current_task_id="t1",
        current_goal="写文章",
        active_domain="article",
    )

    with pytest.raises(ContextBoundaryError):
        ContextBuilder().build("输入", task=task, state=state, retrieved=[], domain=domain)


def test_context_builder_rejects_oversized_runtime_package():
    domain = NovelDomainPackage()
    task = Task(id="t1", title="写 Scene", kind="writing", domain="novel", goal="写场景")
    state = ProjectState(
        current_phase="Draft",
        current_task_id="t1",
        current_goal="完成 Scene",
        active_domain="novel",
    )
    retrieved = [KnowledgeItem(id="k1", kind="note", title="长资料", body="x" * 200, tags={"note"})]

    with pytest.raises(ContextBoundaryError):
        ContextBuilder(max_items=8, max_chars=50).build("输入", task=task, state=state, retrieved=retrieved, domain=domain)
