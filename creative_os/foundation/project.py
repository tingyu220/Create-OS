from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ProjectLifecycleError(ValueError):
    pass


class ProjectPhase(StrEnum):
    IDEA = "Idea"
    PROPOSAL = "Proposal"
    PLANNING = "Planning"
    DRAFTING = "Drafting"
    REVIEW = "Review"
    PUBLISH = "Publish"
    ARCHIVED = "Archived"


class MilestoneStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    BLOCKED = "blocked"


@dataclass(slots=True)
class Milestone:
    id: str
    title: str
    status: MilestoneStatus = MilestoneStatus.PENDING


@dataclass(slots=True)
class Project:
    id: str
    name: str
    domain: str
    phase: ProjectPhase = ProjectPhase.IDEA
    milestones: list[Milestone] = field(default_factory=list)

    def __init__(
        self,
        id: str,
        name: str,
        domain: str,
        phase: ProjectPhase = ProjectPhase.IDEA,
        milestones: list[Milestone] | None = None,
        **extra: object,
    ) -> None:
        if extra:
            raise ValueError(f"Project cannot store extra content fields: {', '.join(sorted(extra))}")
        if not domain:
            raise ValueError("Project domain is required")
        self.id = id
        self.name = name
        self.domain = domain
        self.phase = phase
        self.milestones = list(milestones or [])

    @property
    def progress(self) -> float:
        if not self.milestones:
            return 0.0
        done_count = sum(1 for milestone in self.milestones if milestone.status == MilestoneStatus.DONE)
        return done_count / len(self.milestones)

    def transition_to(self, phase: ProjectPhase) -> None:
        allowed = self._allowed_next_phases(self.phase)
        if phase not in allowed:
            raise ProjectLifecycleError(f"Invalid Project phase transition: {self.phase} -> {phase}")
        self.phase = phase

    def add_milestone(self, milestone_id: str, title: str) -> Milestone:
        if any(milestone.id == milestone_id for milestone in self.milestones):
            raise ValueError(f"Milestone already exists: {milestone_id}")
        milestone = Milestone(id=milestone_id, title=title)
        self.milestones.append(milestone)
        return milestone

    def complete_milestone(self, milestone_id: str) -> Milestone:
        milestone = self._find_milestone(milestone_id)
        milestone.status = MilestoneStatus.DONE
        return milestone

    def _find_milestone(self, milestone_id: str) -> Milestone:
        for milestone in self.milestones:
            if milestone.id == milestone_id:
                return milestone
        raise KeyError(milestone_id)

    def _allowed_next_phases(self, current: ProjectPhase) -> set[ProjectPhase]:
        return {
            ProjectPhase.IDEA: {ProjectPhase.PROPOSAL, ProjectPhase.ARCHIVED},
            ProjectPhase.PROPOSAL: {ProjectPhase.PLANNING, ProjectPhase.IDEA, ProjectPhase.ARCHIVED},
            ProjectPhase.PLANNING: {ProjectPhase.DRAFTING, ProjectPhase.PROPOSAL, ProjectPhase.ARCHIVED},
            ProjectPhase.DRAFTING: {ProjectPhase.REVIEW, ProjectPhase.PLANNING, ProjectPhase.ARCHIVED},
            ProjectPhase.REVIEW: {ProjectPhase.PUBLISH, ProjectPhase.DRAFTING, ProjectPhase.ARCHIVED},
            ProjectPhase.PUBLISH: {ProjectPhase.ARCHIVED},
            ProjectPhase.ARCHIVED: {ProjectPhase.IDEA},
        }[current]
