from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EngagementMigrationReport:
    legacy_fields: tuple[str, ...]
    missing_authority: tuple[str, ...]
    requires_human_plan: bool
    materialized_transitions: tuple[str, ...]


class ReaderEngagementMigration:
    """Read-only audit; never infers expectation state or writes authority records."""

    @staticmethod
    def inspect(project_root: str | Path) -> EngagementMigrationReport:
        root = Path(project_root)
        legacy = tuple(sorted(p.name for p in (root / ".creative_os").glob("*brief*") if p.is_file()))
        return EngagementMigrationReport(legacy, ("active_plan", "ledger", "curve", "human_decision"), True, ())
