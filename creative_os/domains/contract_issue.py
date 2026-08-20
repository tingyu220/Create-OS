from __future__ import annotations

from dataclasses import dataclass


def _required(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} is required")


@dataclass(frozen=True, slots=True)
class EvidenceCheck:
    """One deterministic check performed against field evidence."""

    code: str
    passed: bool
    detail: str

    def __post_init__(self) -> None:
        _required(self.code, "code")
        _required(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class ContractIssue:
    """A field-scoped issue that can block contract admission."""

    code: str
    severity: str
    blocking: bool
    field_path: str
    evidence_checks: tuple[EvidenceCheck, ...]
    repair_hint: str

    def __post_init__(self) -> None:
        _required(self.code, "code")
        _required(self.severity, "severity")
        _required(self.field_path, "field_path")
        _required(self.repair_hint, "repair_hint")
        if not isinstance(self.blocking, bool):
            raise ValueError("blocking must be a bool")
        if not isinstance(self.evidence_checks, tuple):
            raise ValueError("evidence_checks must be a tuple")
        if not all(isinstance(check, EvidenceCheck) for check in self.evidence_checks):
            raise ValueError("evidence_checks must contain EvidenceCheck values")
