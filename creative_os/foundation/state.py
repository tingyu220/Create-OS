from __future__ import annotations

from dataclasses import dataclass, field


class StateBoundaryError(ValueError):
    pass


@dataclass(slots=True)
class ProjectState:
    current_phase: str
    current_task_id: str
    current_goal: str
    active_domain: str
    risks: list[str] = field(default_factory=list)

    def __init__(
        self,
        current_phase: str,
        current_task_id: str,
        current_goal: str,
        active_domain: str,
        risks: list[str] | None = None,
        **extra: object,
    ) -> None:
        if extra:
            raise StateBoundaryError(f"State cannot store extra fields: {', '.join(sorted(extra))}")
        risks = list(risks or [])
        if len(risks) > 10:
            raise StateBoundaryError("State risks must stay compact: max 10")
        self.current_phase = current_phase
        self.current_task_id = current_task_id
        self.current_goal = current_goal
        self.active_domain = active_domain
        self.risks = risks

    def compact(self) -> dict[str, object]:
        return {
            "current_phase": self.current_phase,
            "current_task_id": self.current_task_id,
            "current_goal": self.current_goal,
            "active_domain": self.active_domain,
            "risks": list(self.risks),
        }

    def advance(
        self,
        current_phase: str,
        current_task_id: str,
        current_goal: str,
        risks: list[str] | None = None,
    ) -> "ProjectState":
        return ProjectState(
            current_phase=current_phase,
            current_task_id=current_task_id,
            current_goal=current_goal,
            active_domain=self.active_domain,
            risks=list(self.risks if risks is None else risks),
        )
