from creative_os.capability.writing import TemplateWritingCapability
from creative_os.domains.novel import NovelDomainPackage
from creative_os.engine.compiler import KnowledgeCompiler
from creative_os.engine.context import ContextBuilder
from creative_os.engine.retriever import RuleBasedRetriever
from creative_os.engine.workflow import Workflow
from creative_os.foundation.knowledge import KnowledgeItem, KnowledgeStore
from creative_os.foundation.state import ProjectState
from creative_os.foundation.task import Task, TaskStatus
from creative_os.pipeline import CreativePipeline


def test_task_drives_minimal_context_without_full_knowledge_scan():
    store = KnowledgeStore()
    store.add(KnowledgeItem(id="k1", kind="character", title="林澈", body="主角，目标是寻找失踪的妹妹。", tags={"character", "林澈"}))
    store.add(KnowledgeItem(id="k2", kind="world", title="雾城规则", body="雾城夜晚不能点灯。", tags={"world", "雾城"}))
    store.add(KnowledgeItem(id="k3", kind="archive", title="无关旧稿", body="不应进入本次上下文。", tags={"archive"}))

    task = Task(id="t1", title="写雾城第一场景", kind="writing", domain="novel", goal="写出主角进入雾城", tags={"林澈", "雾城"})
    state = ProjectState(current_phase="Draft", current_task_id="t1", current_goal="完成第一章 Scene 1", active_domain="novel")
    domain = NovelDomainPackage()

    retrieved = RuleBasedRetriever().retrieve(task, store, domain)
    context = ContextBuilder(max_items=3).build(user_input="保持悬疑感", task=task, state=state, retrieved=retrieved, domain=domain)

    assert [item.id for item in context.knowledge] == ["k1", "k2"]
    assert context.task.id == "t1"
    assert "character_consistency" in context.domain_rules


def test_result_must_go_through_compiler_before_updating_knowledge():
    store = KnowledgeStore()
    task = Task(id="t2", title="写第一章场景", kind="writing", domain="novel", goal="生成场景", tags={"林澈"})
    state = ProjectState(current_phase="Draft", current_task_id="t2", current_goal="完成 Scene", active_domain="novel")
    domain = NovelDomainPackage()
    context = ContextBuilder().build(user_input="写一个短场景", task=task, state=state, retrieved=[], domain=domain)

    result = TemplateWritingCapability().run(context)
    assert len(store.items()) == 0

    compiled = KnowledgeCompiler().compile(result, context, domain)
    store.apply(compiled)

    assert len(store.items()) == 1
    item = store.get(compiled.items[0].id)
    assert item.kind == "summary"
    assert item.source_task_id == "t2"
    assert "写一个短场景" in item.body


def test_pipeline_runs_creative_os_v1_closed_loop_and_creates_next_task():
    store = KnowledgeStore()
    store.add(KnowledgeItem(id="k1", kind="character", title="林澈", body="主角。", tags={"林澈"}))
    domain = NovelDomainPackage()
    workflow = Workflow(domain.workflow)
    task = Task(id="t3", title="写第一章 Scene 1", kind="writing", domain="novel", goal="生成场景", tags={"林澈"})
    state = ProjectState(current_phase="Draft", current_task_id="t3", current_goal="完成 Scene 1", active_domain="novel")

    pipeline = CreativePipeline(
        store=store,
        domain=domain,
        workflow=workflow,
        retriever=RuleBasedRetriever(),
        context_builder=ContextBuilder(),
        capability=TemplateWritingCapability(),
        compiler=KnowledgeCompiler(),
    )

    output = pipeline.run(user_input="主角第一次进入雾城", task=task, state=state)

    assert output.task.status == TaskStatus.DONE
    assert output.next_task is not None
    assert output.next_task.kind == "review"
    assert store.find_by_tags({"林澈"})
    assert any(item.source_task_id == "t3" for item in store.items())
