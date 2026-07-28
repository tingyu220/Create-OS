from creative_os.capability.base import KnowledgeDraft, Result, ResultKind
from creative_os.domains.novel import NovelDomainPackage
from creative_os.engine.compiler import KnowledgeCompiler
from creative_os.engine.context import ContextBuilder
from creative_os.foundation.knowledge import KnowledgeCategory, KnowledgeStatus
from creative_os.foundation.state import ProjectState
from creative_os.foundation.task import Task


def _context(task_kind: str = "writing"):
    domain = NovelDomainPackage()
    task = Task(id="t1", title="写 Scene", kind=task_kind, domain="novel", goal="写场景", tags={"林澈"})
    state = ProjectState(current_phase="Draft", current_task_id="t1", current_goal="写场景", active_domain="novel")
    return ContextBuilder().build("输入", task=task, state=state, retrieved=[], domain=domain), domain


def test_compiler_extracts_entity_fact_relationship_and_summary_from_result():
    context, domain = _context()
    result = Result(
        kind=ResultKind.WRITING,
        content="\n".join(
            [
                "Entity: 林澈 | character | 主角",
                "Fact: 雾城夜晚不能点灯",
                "Relationship: 林澈 -> 妹妹 | 寻找",
                "Summary: 林澈进入雾城，发现夜晚不能点灯。",
            ]
        ),
    )

    compiled = KnowledgeCompiler().compile(result, context, domain)

    assert [item.kind for item in compiled.items] == ["entity", "fact", "relationship", "summary"]
    assert all(item.source_task_id == "t1" for item in compiled.items)
    assert compiled.items[0].category == KnowledgeCategory.PROJECT
    assert compiled.items[0].tags >= {"林澈", "entity", "novel"}


def test_compiler_turns_research_drafts_into_external_draft_knowledge():
    context, domain = _context(task_kind="research")
    result = Result(
        kind=ResultKind.RESEARCH,
        content="Research completed.",
        knowledge_drafts=[
            KnowledgeDraft(title="唐朝县令职责", body="县令负责地方行政。", tags={"唐朝", "县令"}, source="provider:web")
        ],
    )

    compiled = KnowledgeCompiler().compile(result, context, domain)

    assert len(compiled.items) == 1
    assert compiled.items[0].category == KnowledgeCategory.EXTERNAL
    assert compiled.items[0].status == KnowledgeStatus.DRAFT
    assert compiled.items[0].kind == "research_draft"
