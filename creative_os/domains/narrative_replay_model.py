from __future__ import annotations

from dataclasses import dataclass

from creative_os.domains.narrative_decision import ProtagonistChoice


UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source_type: str
    source_ref: str
    excerpt: str

    def validate(self) -> None:
        if not self.source_type.strip() or not self.source_ref.strip() or not self.excerpt.strip():
            raise ValueError("evidence requires source_type, source_ref and excerpt")


@dataclass(frozen=True, slots=True)
class ReaderState:
    known: tuple[str, ...] = ()
    suspected: tuple[str, ...] = ()
    misbeliefs: tuple[str, ...] = ()
    expectations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgencyEntry:
    actor: str
    desire: str
    choice: str
    cost: str
    consequence: str
    source_chapter: str
    evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class ForeshadowAction:
    foreshadow_id: str
    action: str
    next_action: str
    source_chapter: str
    evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class ReplayedChapterContract:
    """Evidence-backed audit projection; never replaces an approved ChapterContract."""

    chapter_id: str
    functions: tuple[str, ...]
    dramatic_question: str
    protagonist_choice: ProtagonistChoice | None
    evidence: tuple[EvidenceRef, ...]
    reader_before: str = UNKNOWN
    reader_after: str = UNKNOWN
    pressure_start: str = UNKNOWN
    pressure_end: str = UNKNOWN
    ending_shift: str = UNKNOWN

    def validate(self) -> None:
        if not self.chapter_id.strip() or not self.functions or not self.dramatic_question.strip():
            raise ValueError("replayed chapter contract requires id, functions and dramatic question")
        if any(not item.strip() for item in self.functions):
            raise ValueError("replayed chapter contract functions must be non-empty")
        if not self.evidence:
            raise ValueError("replayed chapter contract requires evidence")
        for evidence in self.evidence:
            evidence.validate()


@dataclass(frozen=True, slots=True)
class ReplayNarrativeIssue:
    code: str
    severity: str
    message: str
    evidence: tuple[EvidenceRef, ...]
    repair_hint: str


@dataclass(frozen=True, slots=True)
class NarrativeReplayState:
    project_id: str
    version: int = 0
    chapter_contracts: tuple[ReplayedChapterContract, ...] = ()
    reader_state: ReaderState = ReaderState()
    agency_ledger: tuple[AgencyEntry, ...] = ()
    foreshadow_actions: tuple[ForeshadowAction, ...] = ()

    def validate(self) -> None:
        if not self.project_id.strip():
            raise ValueError("narrative replay state requires project_id")
        if self.version < 0:
            raise ValueError("narrative replay state version cannot be negative")
        for contract in self.chapter_contracts:
            contract.validate()
