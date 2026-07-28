from creative_os.capability.base import ResultKind
from creative_os.capability.research import ProviderResearchCapability
from creative_os.capability.review import RuleFirstReviewCapability
from creative_os.capability.writing import TemplateWritingCapability
from creative_os.domains.novel import NovelDomainPackage
from creative_os.engine.compiler import KnowledgeCompiler
from creative_os.engine.context import ContextBuilder
from creative_os.foundation.knowledge import KnowledgeItem, KnowledgeStore
from creative_os.foundation.state import ProjectState
from creative_os.foundation.task import Task


def _context(task: Task, retrieved=None):
    domain = NovelDomainPackage()
    state = ProjectState(current_phase="Draft", current_task_id=task.id, current_goal=task.goal, active_domain=task.domain)
    return ContextBuilder().build("用户输入", task=task, state=state, retrieved=retrieved or [], domain=domain), domain


def test_writing_capability_only_uses_context_and_returns_writing_result():
    task = Task(id="t1", title="写 Scene", kind="writing", domain="novel", goal="写雾城", tags={"林澈"})
    context, _domain = _context(task, [KnowledgeItem(id="k1", kind="character", title="林澈", body="主角。", tags={"林澈"})])

    result = TemplateWritingCapability().run(context)

    assert result.kind == ResultKind.WRITING
    assert "林澈" in result.content
    assert result.knowledge_drafts == []
    assert result.follow_up_tasks == []


def test_review_capability_outputs_issue_and_fix_task():
    task = Task(id="t2", title="审核结果", kind="review", domain="novel", goal="检查一致性")
    context, _domain = _context(task)

    result = RuleFirstReviewCapability().run(context)

    assert result.kind == ResultKind.REVIEW
    assert result.issues[0].code == "missing_retrieved_knowledge"
    assert result.follow_up_tasks[0].kind == "fix"
    assert result.follow_up_tasks[0].dependencies == ["t2"]


def test_research_capability_outputs_draft_without_writing_knowledge_directly():
    store = KnowledgeStore()
    task = Task(id="t3", title="研究唐朝县令", kind="research", domain="novel", goal="唐朝县令职责", tags={"唐朝"})
    context, domain = _context(task)
    capability = ProviderResearchCapability(provider=lambda query: f"{query}: 负责地方行政。")

    result = capability.run(context)

    assert result.kind == ResultKind.RESEARCH
    assert len(store.items(include_archived=True)) == 0
    assert result.knowledge_drafts[0].title == "唐朝县令职责"

    compiled = KnowledgeCompiler().compile(result, context, domain)
    store.apply(compiled)

    assert store.items()[0].kind == "research_draft"
