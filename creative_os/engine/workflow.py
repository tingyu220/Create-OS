from __future__ import annotations

from creative_os.foundation.state import ProjectState


class WorkflowTransitionError(ValueError):
    pass


class Workflow:
    def __init__(self, phases: list[str]) -> None:
        if not phases:
            raise ValueError("Workflow requires at least one phase")
        if len(set(phases)) != len(phases):
            raise ValueError("Workflow phases must be unique")
        self._phases = phases

    @classmethod
    def default(cls) -> "Workflow":
        return cls(["Idea", "Proposal", "Outline", "Draft", "Review", "Publish"])

    @property
    def phases(self) -> list[str]:
        return list(self._phases)

    def next_phase(self, current: str) -> str | None:
        if current not in self._phases:
            raise WorkflowTransitionError(f"Unknown workflow phase: {current}")
        index = self._phases.index(current)
        if index + 1 >= len(self._phases):
            return None
        return self._phases[index + 1]

    def validate_transition(self, current: str, target: str) -> None:
        expected = self.next_phase(current)
        if expected != target:
            raise WorkflowTransitionError(f"Invalid workflow transition: {current} -> {target}")

    def advance(self, state: ProjectState, next_task_id: str, next_goal: str) -> ProjectState:
        target = self.next_phase(state.current_phase)
        if target is None:
            raise WorkflowTransitionError(f"Workflow is already at final phase: {state.current_phase}")
        return state.advance(current_phase=target, current_task_id=next_task_id, current_goal=next_goal)
