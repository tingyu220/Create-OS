from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class POVStrategyPolicyError(ValueError):
    pass


ALLOWED_KEYS = {
    "version", "history_window", "cold_start_minimum", "absence_review_after",
    "monopoly_review_after", "blocking_risks", "protagonist_id", "eligible_pov_ids",
}
DEFAULT_BLOCKING_RISKS = ("supporting_pov_without_agency", "pov_cannot_serve_chapter_function")
DEFAULT_PROTAGONIST_ID = "protagonist"


@dataclass(frozen=True, slots=True)
class POVStrategyPolicy:
    version: str = "v1"
    history_window: int = 8
    cold_start_minimum: int = 1
    absence_review_after: int = 3
    monopoly_review_after: int = 4
    blocking_risks: tuple[str, ...] = DEFAULT_BLOCKING_RISKS
    protagonist_id: str = DEFAULT_PROTAGONIST_ID
    eligible_pov_ids: tuple[str, ...] = ()

    def validate(self) -> None:
        if not 6 <= self.history_window <= 10:
            raise POVStrategyPolicyError("invalid_pov_history_window")
        if min(self.cold_start_minimum, self.absence_review_after, self.monopoly_review_after) < 1:
            raise POVStrategyPolicyError("review thresholds must be positive")
        if not self.version.strip() or not self.protagonist_id.strip():
            raise POVStrategyPolicyError("policy identity is required")


def load_pov_strategy_policy(project_root: str | Path) -> POVStrategyPolicy:
    path = Path(project_root) / ".creative_os" / "pov_strategy_policy.json"
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    unknown = set(payload) - ALLOWED_KEYS
    if unknown:
        raise POVStrategyPolicyError(f"pov_strategy_policy_error: unsupported keys {sorted(unknown)}")
    policy = POVStrategyPolicy(
        version=str(payload.get("version", "v1")),
        history_window=int(payload.get("history_window", 8)),
        cold_start_minimum=int(payload.get("cold_start_minimum", 1)),
        absence_review_after=int(payload.get("absence_review_after", 3)),
        monopoly_review_after=int(payload.get("monopoly_review_after", 4)),
        blocking_risks=tuple(str(x) for x in payload.get("blocking_risks", DEFAULT_BLOCKING_RISKS)),
        protagonist_id=str(payload.get("protagonist_id", DEFAULT_PROTAGONIST_ID)),
        eligible_pov_ids=tuple(str(x) for x in payload.get("eligible_pov_ids", ())),
    )
    policy.validate()
    return policy
