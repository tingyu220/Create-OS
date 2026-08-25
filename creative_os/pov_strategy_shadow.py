from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from creative_os.domains.pov_strategy_input import assemble_pov_strategy_input
from creative_os.domains.pov_strategy_model import ChapterNeeds, POVStrategyCandidateSet
from creative_os.domains.pov_strategy_planner import POVStrategyPlanner
from creative_os.domains.pov_strategy_policy import load_pov_strategy_policy
from creative_os.domains.pov_strategy_review import review_pov_strategy
from creative_os.runtime.pov_strategy_store import POVStrategyAuditStore


@dataclass(frozen=True, slots=True)
class ShadowRunResult:
    status: str
    candidates: POVStrategyCandidateSet | None
    issues: tuple[str, ...]


def run_pov_strategy_shadow(
    project_root: str | Path,
    target_chapter: int,
    chapter_needs: ChapterNeeds,
    *,
    write_audit: bool = True,
) -> ShadowRunResult:
    try:
        root = Path(project_root)
        profile = root / ".creative_os" / "memory" / "items" / "narrative-project-profile.json"
        previous = root / "production" / "final_chapters" / f"chapter_{target_chapter - 1:03d}.md"
        if not profile.exists() or not previous.exists():
            return ShadowRunResult("blocked", None, ("missing_pov_strategy_input",))
        policy = load_pov_strategy_policy(project_root)
        input_value = assemble_pov_strategy_input(project_root, target_chapter, chapter_needs, policy)
        candidates = POVStrategyPlanner().plan(input_value, policy)
        candidates = replace(candidates, risks=review_pov_strategy(input_value, candidates, policy))
        if write_audit:
            POVStrategyAuditStore(project_root).append_candidate(candidates)
        return ShadowRunResult("candidate", candidates, tuple(risk.code for risk in candidates.risks))
    except (OSError, ValueError, IndexError) as exc:
        code = getattr(exc, "code", type(exc).__name__)
        return ShadowRunResult("blocked", None, (str(code),))
