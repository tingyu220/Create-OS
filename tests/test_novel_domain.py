from creative_os.capability.writing import TemplateWritingCapability
from creative_os.domains.novel import NovelDomainPackage, NovelSchemaKind
from creative_os.engine.compiler import KnowledgeCompiler
from creative_os.engine.context import ContextBuilder
from creative_os.engine.retriever import RuleBasedRetriever
from creative_os.engine.workflow import Workflow
from creative_os.foundation.knowledge import KnowledgeItem, KnowledgeStore
from creative_os.foundation.state import ProjectState
from creative_os.foundation.task import Task, TaskStatus
from creative_os.pipeline import CreativePipeline


def test_novel_schema_defines_required_domain_objects_with_fields():
    domain = NovelDomainPackage()

    assert set(domain.schema) >= {
        "Character",
        "World",
        "Chapter",
        "Scene",
        "Timeline",
        "Relationship",
        "Foreshadow",
        "Conflict",
        "Style",
    }
    assert domain.schema_definition(NovelSchemaKind.CHARACTER).required_fields == ["name", "role", "goal", "state"]
    assert "characters" in domain.schema_definition(NovelSchemaKind.SCENE).required_fields


def test_novel_rules_are_grouped_for_review_workflow_and_writing():
    domain = NovelDomainPackage()

    assert "character_consistency" in domain.rules_for("review")
    assert "world_rule_consistency" in domain.rules_for("review")
    assert "chapter_goal_required" in domain.rules_for("workflow")
    assert "scene_conflict_required" in domain.rules_for("writing")


def test_novel_templates_are_available_for_required_objects():
    domain = NovelDomainPackage()

    character_template = domain.template("character")
    chapter_template = domain.template("chapter")
    world_template = domain.template("world")

    assert "Name:" in character_template
    assert "Knowledge Updates:" in chapter_template
    assert "Rule:" in world_template


def test_novel_workflow_matches_stage_four_plan_and_runs_engine_loop():
    domain = NovelDomainPackage()

    assert domain.workflow == [
        "Idea",
        "Proposal",
        "World",
        "Character",
        "Outline",
        "Chapter",
        "Scene",
        "Draft",
        "Review",
        "Knowledge Update",
    ]

    store = KnowledgeStore()
    store.add(KnowledgeItem(id="k1", kind="character", title="林澈", body="主角。", tags={"林澈", "character"}))
    task = Task(id="t-novel-1", title="写第一章 Scene", kind="writing", domain="novel", goal="写林澈进入雾城", tags={"林澈"})
    state = ProjectState(current_phase="Draft", current_task_id=task.id, current_goal=task.goal, active_domain="novel")
    pipeline = CreativePipeline(
        store=store,
        domain=domain,
        workflow=Workflow(domain.workflow),
        retriever=RuleBasedRetriever(),
        context_builder=ContextBuilder(),
        capability=TemplateWritingCapability(),
        compiler=KnowledgeCompiler(),
    )

    output = pipeline.run("保持悬疑感", task=task, state=state)

    assert output.task.status == TaskStatus.DONE
    assert output.next_task.kind == "review"
    assert any(item.source_task_id == task.id for item in store.items())
