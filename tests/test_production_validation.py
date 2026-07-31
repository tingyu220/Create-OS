from creative_os.agents import AgentRole, default_novel_agent_contracts
from creative_os.production import (
    ProductionLog,
    ProjectWorkspace,
    create_default_validation_project,
)


def test_validation_project_has_required_milestones_and_next_step():
    validation_project = create_default_validation_project(code_version="test-sha")

    validation_project.brief.validate()

    assert validation_project.project.domain == "novel"
    assert validation_project.project.phase.value == "Proposal"
    assert [milestone.id for milestone in validation_project.project.milestones] == [
        "m1-project",
        "m2-agents",
        "m3-design",
        "m4-first-chapter",
        "m5-ten-chapters",
        "m6-draft-complete",
        "m7-full-review",
        "m8-v1-1",
    ]
    assert validation_project.next_step() == "创建 Project Proposal 并进入前期设计"


def test_project_workspace_can_restore_state_after_close(tmp_path):
    validation_project = create_default_validation_project(code_version="test-sha")
    validation_project.production_log.record(
        input_task_id="proposal-001",
        input_summary="建立项目提案",
        context_sources=["brief"],
        capability="planner",
        output_summary="生成 Project Proposal 草案",
        review_result="pending",
        knowledge_updates=[],
    )

    workspace = ProjectWorkspace(tmp_path / "雾城回声")
    workspace.save(validation_project)
    restored = workspace.load()

    assert restored.project.id == "novel-validation-001"
    assert restored.state.current_task_id == "proposal-001"
    assert restored.brief.name == "雾城回声"
    assert restored.baseline.code_version == "test-sha"
    assert restored.production_log.entries()[0].context_sources == ["brief"]


def test_production_log_records_required_runtime_fields():
    log = ProductionLog()

    entry = log.record(
        input_task_id="scene-001",
        input_summary="写第一章 Scene 1",
        context_sources=["character-lin-che", "world-fog-city"],
        capability="writer",
        output_summary="生成 2300 字草稿",
        review_result="pass",
        knowledge_updates=["summary-scene-001", "timeline-scene-001"],
        human_intervention="A类：确认主角职业",
    )

    assert entry.id == "run-0001"
    assert entry.context_sources == ["character-lin-che", "world-fog-city"]
    assert entry.review_result == "pass"
    assert entry.human_intervention.startswith("A类")


def test_default_novel_agents_are_fixed_and_not_universal():
    contracts = default_novel_agent_contracts()

    assert set(contracts) == set(AgentRole)
    assert "直接写章节正文" in contracts[AgentRole.DIRECTOR].forbidden
    assert "直接读写 Knowledge" in contracts[AgentRole.WRITER].forbidden
    assert "Knowledge Patch" in contracts[AgentRole.COMPILER].outputs
