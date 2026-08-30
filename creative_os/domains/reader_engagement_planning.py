from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from creative_os.domains.project_authority import project_authority_lock
from creative_os.domains.reader_engagement_store import ReaderEngagementStore


@dataclass(frozen=True, slots=True)
class PlanDecisionRecorder:
    store: ReaderEngagementStore

    def record(self, plan_id: str, plan_hash: str, curve_id: str, curve_hash: str, actor: str, reason: str, disposition: str = "approved"):
        if disposition != "approved" or not actor.strip() or not reason.strip():
            raise ValueError("decision_invalid")
        payload = {"plan_id": plan_id, "plan_hash": plan_hash, "curve_id": curve_id,
                   "curve_hash": curve_hash, "actor": actor, "reason": reason,
                   "disposition": disposition}
        return self.store.append_raw_decision(payload)


@dataclass(frozen=True, slots=True)
class PlanActivationService:
    store: ReaderEngagementStore

    def activate_plan(self, plan_id: str, decision_id: str, expected_active_hash: str):
        with project_authority_lock(self.store.project_root):
            return self.store.activate_plan_locked(plan_id, decision_id, expected_active_hash)


class ReaderEngagementPlanningService:
    def __init__(self, project_root: str | Path | None = None) -> None:
        self.project_root = Path(project_root) if project_root is not None else None
        self.store = ReaderEngagementStore(self.project_root) if self.project_root else None

    def propose(self, input: object, candidate: object) -> object:
        if self.store is None:
            raise ValueError("project store required")
        return self.store.append_plan_candidate(candidate)

    def plan_decision_recorder(self) -> PlanDecisionRecorder:
        if self.store is None:
            raise ValueError("project store required")
        return PlanDecisionRecorder(self.store)

    def plan_activation_service(self) -> PlanActivationService:
        if self.store is None:
            raise ValueError("project store required")
        return PlanActivationService(self.store)

    def project_chapter(self, project_id: str, chapter_number: int):
        if self.store is None:
            raise ValueError("active plan required")
        return self.store.project_chapter_locked(project_id, chapter_number)
