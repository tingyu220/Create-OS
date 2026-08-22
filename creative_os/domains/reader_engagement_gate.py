from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from creative_os.domains.reader_engagement_store import ReaderEngagementStore


@dataclass(frozen=True, slots=True)
class ReaderEngagementExitGateResult:
    passed: bool
    issues: tuple[str, ...]


def evaluate_reader_engagement_exit_gate(project_root: Path) -> ReaderEngagementExitGateResult:
    try:
        records = ReaderEngagementStore(project_root).recover()
    except Exception:
        return ReaderEngagementExitGateResult(False, ("authority_store_unreadable",))
    issues: list[str] = []
    if not any(r.record_type == "plan_activation" for r in records):
        issues.append("active_plan_missing")
    if not any(r.record_type == "plan" for r in records):
        issues.append("plan_missing")
    if not any(r.record_type == "opening_checkpoint" for r in records):
        issues.append("human_opening_checkpoint_missing")
    return ReaderEngagementExitGateResult(not issues, tuple(issues))
