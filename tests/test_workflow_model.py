import pytest

from creative_os.engine.workflow import Workflow, WorkflowTransitionError
from creative_os.foundation.state import ProjectState


def test_workflow_advances_state_by_explicit_order_without_domain_assumption():
    workflow = Workflow.default()
    state = ProjectState(
        current_phase="Idea",
        current_task_id="t1",
        current_goal="确认方向",
        active_domain="article",
    )

    next_state = workflow.advance(state, next_task_id="t2", next_goal="生成提案")

    assert next_state.current_phase == "Proposal"
    assert next_state.active_domain == "article"
    assert workflow.next_phase("Proposal") == "Outline"


def test_workflow_rejects_unknown_phase_and_skipping():
    workflow = Workflow.default()

    with pytest.raises(WorkflowTransitionError):
        workflow.next_phase("World")

    with pytest.raises(WorkflowTransitionError):
        workflow.validate_transition("Idea", "Draft")


def test_workflow_can_be_extended_by_domain_package_without_changing_engine():
    workflow = Workflow(["Idea", "Proposal", "World", "Character", "Draft"])

    workflow.validate_transition("Proposal", "World")

    assert workflow.next_phase("Character") == "Draft"
