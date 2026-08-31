from __future__ import annotations

from dataclasses import dataclass

from creative_os.projection.provenance import Derivation, SourceRef


@dataclass(frozen=True, slots=True)
class QualityIssueSnapshot:
    issue_id: str
    code: str
    severity: str
    blocking: bool
    scope: str
    source_refs: tuple[SourceRef, ...]


@dataclass(frozen=True, slots=True)
class GateResultSnapshot:
    gate_id: str
    status: str
    source_refs: tuple[SourceRef, ...]
    derivations: tuple[Derivation, ...] = ()


@dataclass(frozen=True, slots=True)
class QualitySnapshot:
    issues: tuple[QualityIssueSnapshot, ...]
    gate_results: tuple[GateResultSnapshot, ...]
    source_refs: tuple[SourceRef, ...]

    @property
    def blocking_count(self) -> int:
        return sum(1 for issue in self.issues if issue.blocking)
