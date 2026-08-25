from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace


class POVStrategyValidationError(ValueError):
    pass


def _text(value: str, name: str) -> None:
    if not value.strip():
        raise POVStrategyValidationError(f"{name} is required")


def _hash(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source_id: str
    source_version: str
    source_content_hash: str
    locator: str
    assertion: str

    def validate(self) -> None:
        for name in ("source_id", "source_version", "locator", "assertion"):
            _text(getattr(self, name), f"evidence {name}")
        if not _hash(self.source_content_hash):
            raise POVStrategyValidationError("evidence source_content_hash must be sha256")


@dataclass(frozen=True, slots=True)
class StateRef:
    id: str
    value: str
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class ConsequenceRef:
    id: str
    value: str
    affects_protagonist: bool
    owner_ids: tuple[str, ...]
    status: str
    materialized_after_chapter: int | None
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class MainlineCapability:
    id: str
    serves_functions: tuple[str, ...]
    target_state_ref: str
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class RecentPOVEntry:
    chapter: int
    primary_owner: str
    protagonist_present: bool
    chapter_functions: tuple[str, ...]
    mainline_outcomes: tuple[StateRef, ...]
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class ProtagonistLoad:
    consecutive_absence: int
    consecutive_primary_pov: int
    cold_start: bool
    unresolved_consequences: tuple[ConsequenceRef, ...]


@dataclass(frozen=True, slots=True)
class CharacterPressure:
    character_id: str
    unfinished_goals: tuple[StateRef, ...]
    pending_choices: tuple[StateRef, ...]
    unpaid_costs: tuple[StateRef, ...]
    agency_capabilities: tuple[MainlineCapability, ...]


@dataclass(frozen=True, slots=True)
class ArcState:
    arc_id: str
    phase: str
    core_question: str
    current_pressure: str
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class StorylineState:
    id: str
    status: str
    pressures: tuple[StateRef, ...]
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class ChapterNeeds:
    functions: tuple[str, ...]
    dramatic_question: str
    required_scene_capabilities: tuple[str, ...]
    required_world_slice: str
    technology_roles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class POVStrategyInput:
    project_id: str
    target_chapter: int
    assembled_at: str
    policy_version: str
    recent_pov_history: tuple[RecentPOVEntry, ...]
    protagonist_load: ProtagonistLoad
    character_pressures: tuple[CharacterPressure, ...]
    arc_state: ArcState
    storyline_states: tuple[StorylineState, ...]
    unclaimed_consequences: tuple[ConsequenceRef, ...]
    chapter_needs: ChapterNeeds
    evidence: tuple[EvidenceRef, ...]
    baseline_fingerprint: str = ""

    def with_fingerprint(self) -> POVStrategyInput:
        return replace(self, baseline_fingerprint=fingerprint_input(self))

    def validate_fingerprint(self) -> None:
        if self.target_chapter < 1 or not self.chapter_needs.functions:
            raise POVStrategyValidationError("missing_pov_strategy_input")
        if self.baseline_fingerprint != fingerprint_input(self):
            raise POVStrategyValidationError("stale_pov_strategy_candidate")


@dataclass(frozen=True, slots=True)
class SupportingAgencyBoundary:
    actor: str
    goal_ref: StateRef
    resistance_ref: StateRef
    choice_boundary: str
    plausible_cost_ref: StateRef | None


@dataclass(frozen=True, slots=True)
class MainlineChangeProposal:
    target_state_ref: str
    change_type: str
    capability: str
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class TransitionReason:
    from_recent_pov: str
    arc_reason: str
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class POVOption:
    id: str
    primary_owner: str
    protagonist_present: bool
    rationale: str
    function_fits: tuple[str, ...]
    benefits: tuple[str, ...]
    tradeoffs: tuple[str, ...]
    cannot_serve: tuple[str, ...]
    mainline_change: MainlineChangeProposal
    agency: SupportingAgencyBoundary
    transition: TransitionReason
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class RhythmOutlook:
    horizon_chapters: int
    pressures_to_revisit: tuple[str, ...]
    suggested_pov_functions: tuple[str, ...]
    flexibility_notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class POVRisk:
    code: str
    severity: str
    evidence_refs: tuple[EvidenceRef, ...]
    explanation: str


@dataclass(frozen=True, slots=True)
class POVStrategyCandidateSet:
    id: str
    target_chapter: int
    input_fingerprint: str
    policy_version: str
    generated_at: str
    expires_when: tuple[str, ...]
    recommended: POVOption
    alternatives: tuple[POVOption, ...]
    rhythm_outlook: RhythmOutlook
    risks: tuple[POVRisk, ...]

    def validate(self) -> None:
        if not _hash(self.input_fingerprint):
            raise POVStrategyValidationError("candidate input_fingerprint must be sha256")
        if self.rhythm_outlook.horizon_chapters not in {3, 4}:
            raise POVStrategyValidationError("rhythm horizon must be 3 or 4")
        ids = [self.recommended.id, *(item.id for item in self.alternatives)]
        if len(ids) != len(set(ids)):
            raise POVStrategyValidationError("candidate option ids must be unique")


@dataclass(frozen=True, slots=True)
class HumanPOVOverride:
    option: POVOption
    reason: str
    evidence_refs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class POVSelectionRecord:
    candidate_id: str
    option_id: str
    selection_kind: str
    actor: str
    input_fingerprint: str
    selected_at: str
    override: HumanPOVOverride | None = None


@dataclass(frozen=True, slots=True)
class POVStrategyAuditRecord:
    candidate: POVStrategyCandidateSet
    status: str
    actor: str
    updated_at: str
    content_hash: str


def fingerprint_input(value: POVStrategyInput) -> str:
    payload = asdict(replace(value, baseline_fingerprint=""))
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
