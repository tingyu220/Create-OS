from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import Any, Iterator

from creative_os.domains.narrative_evidence import EvidenceRef, EvidenceRole


class NarrativeValidationError(ValueError):
    pass


class ArcPhase(StrEnum):
    SETUP = "setup"
    ESCALATION = "escalation"
    TURN = "turn"
    AFTERMATH = "aftermath"
    CLOSURE = "closure"


class WrittenTextStrategy(StrEnum):
    KEEP = "keep"
    LOCAL_REVISION = "local_revision"
    REWRITE_CANDIDATE = "rewrite_candidate"
    ARCHIVE = "archive"


class NarrativeChangeStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"


class ChoiceStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class CandidateKind(StrEnum):
    FORESHADOW_NEXT_ACTION = "foreshadow_next_action"
    RELATIONSHIP_CHANGE = "relationship_change"
    SCENE_TRANSITION = "scene_transition"


class CandidateValueState(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"


class CandidateImpact(StrEnum):
    YES = "yes"
    NO = "no"
    UNDETERMINED = "undetermined"


class CandidateDecisionBy(StrEnum):
    RULE = "rule"
    HUMAN = "human"


@dataclass(frozen=True, slots=True)
class StoryContract:
    core_question: str
    reader_promise: tuple[str, ...]
    theme_conflict: str
    invariants: tuple[str, ...]

    def validate(self) -> None:
        _require_text(self.core_question, "story contract core_question")
        _require_items(self.reader_promise, "story contract reader_promise")
        _require_text(self.theme_conflict, "story contract theme_conflict")
        _require_items(self.invariants, "story contract invariants")


@dataclass(frozen=True, slots=True)
class StoryVolume:
    id: str
    goal: str
    irreversible_change: str

    def validate(self) -> None:
        _require_text(self.id, "volume id")
        _require_text(self.goal, "volume goal")
        _require_text(self.irreversible_change, "volume irreversible_change")


@dataclass(frozen=True, slots=True)
class StoryArc:
    id: str
    volume_id: str
    goal: str
    phase: ArcPhase

    def validate(self) -> None:
        _require_text(self.id, "arc id")
        _require_text(self.volume_id, "arc volume_id")
        _require_text(self.goal, "arc goal")


@dataclass(frozen=True, slots=True)
class NarrativeProjectProfile:
    id: str
    story_contract: StoryContract
    volumes: tuple[StoryVolume, ...]
    arcs: tuple[StoryArc, ...]

    def validate(self) -> None:
        _require_text(self.id, "profile id")
        self.story_contract.validate()
        _require_non_empty_tuple(self.volumes, "profile volumes")
        _require_non_empty_tuple(self.arcs, "profile arcs")
        volume_ids: set[str] = set()
        for volume in self.volumes:
            volume.validate()
            if volume.id in volume_ids:
                raise NarrativeValidationError(f"duplicate volume id: {volume.id}")
            volume_ids.add(volume.id)
        for arc in self.arcs:
            arc.validate()
            if arc.volume_id not in volume_ids:
                raise NarrativeValidationError(f"arc references unknown volume: {arc.volume_id}")

    def to_json(self) -> str:
        self.validate()
        return _to_json(self)

    @classmethod
    def from_json(cls, content: str) -> "NarrativeProjectProfile":
        payload = _load_object(content)
        contract = payload.get("story_contract", {})
        profile = cls(
            id=str(payload.get("id", "")),
            story_contract=StoryContract(
                core_question=str(contract.get("core_question", "")),
                reader_promise=_string_tuple(contract.get("reader_promise")),
                theme_conflict=str(contract.get("theme_conflict", "")),
                invariants=_string_tuple(contract.get("invariants")),
            ),
            volumes=tuple(
                StoryVolume(
                    id=str(item.get("id", "")),
                    goal=str(item.get("goal", "")),
                    irreversible_change=str(item.get("irreversible_change", "")),
                )
                for item in _object_list(payload.get("volumes"), "volumes")
            ),
            arcs=tuple(
                StoryArc(
                    id=str(item.get("id", "")),
                    volume_id=str(item.get("volume_id", "")),
                    goal=str(item.get("goal", "")),
                    phase=_enum(ArcPhase, item.get("phase"), "arc phase"),
                )
                for item in _object_list(payload.get("arcs"), "arcs")
            ),
        )
        profile.validate()
        return profile


@dataclass(frozen=True, slots=True)
class ProtagonistChoice:
    actor: str | None
    action: str | None
    alternatives: tuple[str, ...]
    cost: str | None
    consequence: str | None
    status: ChoiceStatus = ChoiceStatus.COMPLETE
    missing_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, ChoiceStatus):
            object.__setattr__(self, "status", _require_enum_member(ChoiceStatus, self.status, "choice status"))

    def validate(self) -> None:
        if not isinstance(self.status, ChoiceStatus):
            raise NarrativeValidationError(f"invalid choice status: {self.status}")
        for name, value in (
            ("actor", self.actor),
            ("action", self.action),
            ("cost", self.cost),
            ("consequence", self.consequence),
        ):
            if value is not None and not isinstance(value, str):
                raise NarrativeValidationError(f"protagonist choice {name} must be text or null")
        _require_string_tuple(self.alternatives, "protagonist choice alternatives", allow_empty=True)
        _require_string_tuple(self.missing_fields, "protagonist choice missing_fields", allow_empty=True)
        missing = tuple(
            name
            for name, value in (
                ("actor", self.actor),
                ("action", self.action),
                ("alternatives", self.alternatives),
                ("cost", self.cost),
                ("consequence", self.consequence),
            )
            if not value or (isinstance(value, str) and not value.strip())
        )
        if self.status == ChoiceStatus.COMPLETE:
            if missing or self.missing_fields:
                raise NarrativeValidationError("complete protagonist choice cannot have missing fields")
            _require_items(self.alternatives, "protagonist choice alternatives")
            return
        if self.status == ChoiceStatus.PARTIAL:
            if not missing or self.missing_fields != missing:
                raise NarrativeValidationError("partial protagonist choice must list every missing field")
            return
        expected = ("actor", "action", "alternatives", "cost", "consequence")
        if missing != expected or self.missing_fields != expected:
            raise NarrativeValidationError("unknown protagonist choice cannot carry speculative values")


@dataclass(frozen=True, slots=True)
class NullablePlan:
    values: tuple[str, ...]
    not_applicable_reason: str | None = None

    def validate(self) -> None:
        _require_string_tuple(self.values, "nullable plan values", allow_empty=True)
        if self.not_applicable_reason is not None:
            _require_text(self.not_applicable_reason, "not_applicable_reason")
        if self.values and self.not_applicable_reason is not None:
            raise NarrativeValidationError("nullable plan values and not_applicable_reason are mutually exclusive")

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    def __bool__(self) -> bool:
        return bool(self.values)


@dataclass(frozen=True, slots=True)
class OptionalCandidateResolution:
    candidate_id: str
    kind: CandidateKind | str
    value_state: CandidateValueState | str
    proposed_value: str | None
    dependency_inputs: tuple[str, ...]
    affects_current_chapter: CandidateImpact | str
    rationale: str
    decided_by: CandidateDecisionBy | str
    decision_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _require_enum_member(CandidateKind, self.kind, "candidate kind"))
        object.__setattr__(
            self,
            "value_state",
            _require_enum_member(CandidateValueState, self.value_state, "candidate value_state"),
        )
        object.__setattr__(
            self,
            "affects_current_chapter",
            _require_enum_member(CandidateImpact, self.affects_current_chapter, "candidate affects_current_chapter"),
        )
        object.__setattr__(
            self,
            "decided_by",
            _require_enum_member(CandidateDecisionBy, self.decided_by, "candidate decided_by"),
        )

    def validate(self) -> None:
        _require_text(self.candidate_id, "candidate_id")
        _require_enum_member(CandidateKind, self.kind, "candidate kind")
        value_state = _require_enum_member(CandidateValueState, self.value_state, "candidate value_state")
        _require_items(self.dependency_inputs, "candidate dependency_inputs")
        _require_enum_member(CandidateImpact, self.affects_current_chapter, "candidate affects_current_chapter")
        _require_text(self.rationale, "candidate rationale")
        _require_enum_member(CandidateDecisionBy, self.decided_by, "candidate decided_by")
        _require_text(self.decision_ref, "candidate decision_ref")
        if value_state == CandidateValueState.KNOWN:
            _require_text(self.proposed_value, "candidate proposed_value")
        elif self.proposed_value is not None:
            raise NarrativeValidationError("unknown candidate cannot include proposed_value")


@dataclass(frozen=True, slots=True)
class FieldEvidenceBinding:
    field_path: str
    evidence: tuple[EvidenceRef, ...]

    def validate(self, contract_id: str, contract_version: int) -> None:
        _require_text(self.field_path, "evidence binding field_path")
        if not isinstance(self.evidence, tuple) or not self.evidence:
            raise NarrativeValidationError("evidence binding requires a non-empty evidence tuple")
        for ref in self.evidence:
            if not isinstance(ref, EvidenceRef) or ref.is_legacy_replay_ref:
                raise NarrativeValidationError("frozen contract requires field EvidenceRef")
            try:
                ref.validate()
            except ValueError as error:
                raise NarrativeValidationError(f"invalid evidence binding: {error}") from error
            if ref.contract_id != contract_id or ref.contract_version != contract_version:
                raise NarrativeValidationError("evidence binding contract identity mismatch")
            if ref.field_path != self.field_path:
                raise NarrativeValidationError("evidence binding field_path mismatch")
            if ref.role not in (EvidenceRole.INTENT, EvidenceRole.NON_APPLICABILITY):
                raise NarrativeValidationError("frozen contract evidence role must be intent or non_applicability")


@dataclass(frozen=True, slots=True)
class LegacyUnclassifiedEvidence:
    source_type: str
    source_ref: str
    excerpt: str
    classification: str = "legacy_unclassified"

    def validate(self) -> None:
        _require_text(self.source_type, "legacy evidence source_type")
        _require_text(self.source_ref, "legacy evidence source_ref")
        _require_text(self.excerpt, "legacy evidence excerpt")
        if self.classification != "legacy_unclassified":
            raise NarrativeValidationError("invalid legacy evidence classification")


@dataclass(frozen=True, slots=True)
class ReaderChange:
    before: str
    after: str

    def validate(self) -> None:
        _require_text(self.before, "reader change before")
        _require_text(self.after, "reader change after")


@dataclass(frozen=True, slots=True)
class InformationPlan:
    reveal: tuple[str, ...]
    withhold: tuple[str, ...]
    misdirect: NullablePlan | tuple[str, ...]

    def __post_init__(self) -> None:
        if isinstance(self.misdirect, tuple):
            object.__setattr__(self, "misdirect", NullablePlan(values=self.misdirect))

    def validate(self) -> None:
        _require_items(self.reveal, "information reveal")
        _require_items(self.withhold, "information withhold")
        if not isinstance(self.misdirect, NullablePlan):
            raise NarrativeValidationError("information misdirect must be a NullablePlan")
        self.misdirect.validate()


@dataclass(frozen=True, slots=True)
class PressureCurve:
    start: str
    turn: str
    end: str

    def validate(self) -> None:
        _require_text(self.start, "pressure curve start")
        _require_text(self.turn, "pressure curve turn")
        _require_text(self.end, "pressure curve end")


@dataclass(frozen=True, slots=True)
class EngagementObligation:
    action: str
    expectation_id: str
    intent_evidence: tuple[EvidenceRef, ...]
    projection_hash: str
    deadline_chapter: int | None = None

    def validate(self, contract_id: str, contract_version: int) -> None:
        if self.action not in {"establish", "escalate", "pay", "withhold"}:
            raise NarrativeValidationError("invalid engagement obligation action")
        _require_text(self.expectation_id, "engagement expectation_id")
        _require_text(self.projection_hash, "engagement projection_hash")
        if not self.intent_evidence:
            raise NarrativeValidationError("engagement intent evidence is required")
        for ref in self.intent_evidence:
            if not isinstance(ref, EvidenceRef) or ref.is_legacy_replay_ref:
                raise NarrativeValidationError("engagement evidence must be exact EvidenceRef")
            ref.validate()
            if ref.contract_id != contract_id or ref.contract_version != contract_version:
                raise NarrativeValidationError("engagement evidence contract identity mismatch")
            if ref.role is not EvidenceRole.INTENT:
                raise NarrativeValidationError("engagement evidence role must be intent")
        if self.deadline_chapter is not None and (isinstance(self.deadline_chapter, bool) or self.deadline_chapter <= 0):
            raise NarrativeValidationError("engagement deadline must be positive")


@dataclass(frozen=True, slots=True)
class SceneContract:
    id: str
    order: int
    place_id: str
    place_label: str
    place_class: str
    interior_exterior: str
    time_window: str
    participants: tuple[str, ...]
    viewpoint: str
    ordinary_people_present: bool
    goal: str
    conflict: str
    action: str
    information_change: str
    state_change: str
    entry_reason: str
    exit_trigger: str
    inherited_from_previous: bool = False

    def validate(self) -> None:
        for name in ("id", "place_id", "place_label", "place_class", "interior_exterior", "time_window", "viewpoint", "goal", "conflict", "action", "entry_reason", "exit_trigger"):
            _require_text(str(getattr(self, name)), f"scene {name}")
        if self.order < 1:
            raise NarrativeValidationError("scene order must be positive")
        _require_items(self.participants, "scene participants")
        if not self.information_change.strip() and not self.state_change.strip():
            raise NarrativeValidationError("scene requires information_change or state_change")


@dataclass(frozen=True, slots=True)
class ScenePlan:
    scenes: tuple[SceneContract, ...] = ()
    chapter_spatial_intent: str = ""
    required_world_slice: str = ""
    allowed_same_place_run: int = 3
    exception_reason: str = ""

    def validate(self, *, required: bool = False) -> None:
        if required and not self.scenes:
            raise NarrativeValidationError("scene plan requires scenes")
        if not self.scenes:
            return
        _require_text(self.chapter_spatial_intent, "scene plan chapter_spatial_intent")
        if self.allowed_same_place_run < 1:
            raise NarrativeValidationError("scene plan allowed_same_place_run must be positive")
        orders = []
        for scene in self.scenes:
            scene.validate()
            orders.append(scene.order)
        if orders != list(range(1, len(self.scenes) + 1)):
            raise NarrativeValidationError("scene orders must be unique and contiguous")


@dataclass(frozen=True, slots=True)
class TechnologyContract:
    id: str
    name: str
    role: str
    birth_reason: str
    source: str
    prerequisites: tuple[str, ...]
    validation_stage: str
    first_application: str
    social_diffusion: tuple[str, ...]
    cost: str
    changed_domains: tuple[str, ...]

    def validate(self) -> None:
        for field_name in ("id", "name", "role", "birth_reason", "source", "validation_stage", "first_application", "cost"):
            _require_text(str(getattr(self, field_name)), f"technology {field_name}")
        if self.role not in {"core", "supporting", "background"}:
            raise NarrativeValidationError("technology role must be core, supporting, or background")
        if self.role in {"core", "supporting"}:
            _require_items(self.prerequisites, "technology prerequisites")
            _require_items(self.social_diffusion, "technology social_diffusion")
            _require_items(self.changed_domains, "technology changed_domains")


@dataclass(frozen=True, slots=True)
class TechnologyPlan:
    technologies: tuple[TechnologyContract, ...] = ()

    def validate(self) -> None:
        for technology in self.technologies:
            technology.validate()


@dataclass(frozen=True, slots=True)
class SupportingAgencyContract:
    actor: str
    independent_goal: str
    resistance: str
    choice: str
    cost: str
    result: str
    mainline_change: str

    def validate(self) -> None:
        for field_name in (
            "actor", "independent_goal", "resistance", "choice", "cost", "result", "mainline_change",
        ):
            _require_text(str(getattr(self, field_name)), f"supporting agency {field_name}")


@dataclass(frozen=True, slots=True)
class PointOfViewPlan:
    primary_owner: str = ""
    mode: str = ""
    protagonist_present: bool = True
    supporting_agency: tuple[SupportingAgencyContract, ...] = ()
    rationale: str = ""

    def validate(self, *, required: bool = False) -> None:
        if not self.primary_owner and not required:
            return
        _require_text(self.primary_owner, "POV primary_owner")
        if self.mode not in {"limited", "first_person", "omniscient_limited"}:
            raise NarrativeValidationError("POV mode is invalid")
        _require_text(self.rationale, "POV rationale")
        if required and not self.supporting_agency:
            raise NarrativeValidationError("POV requires supporting agency")
        for agency in self.supporting_agency:
            agency.validate()

@dataclass(frozen=True, slots=True)
class ChapterContract:
    functions: tuple[str, ...]
    dramatic_question: str
    protagonist_choice: ProtagonistChoice
    reader_change: ReaderChange
    information: InformationPlan
    pressure_curve: PressureCurve
    foreshadow_actions: NullablePlan | tuple[str, ...]
    ending_shift: str
    target_chinese_chars: int
    forbidden: NullablePlan | tuple[str, ...]
    chapter_id: str = ""
    optional_candidates: tuple[OptionalCandidateResolution, ...] = ()
    intent_evidence_bindings: tuple[FieldEvidenceBinding, ...] = ()
    engagement_obligations: tuple[EngagementObligation, ...] = ()
    scene_plan: ScenePlan = ScenePlan()
    technology_plan: TechnologyPlan = TechnologyPlan()
    pov_plan: PointOfViewPlan = PointOfViewPlan()

    def __post_init__(self) -> None:
        if isinstance(self.foreshadow_actions, tuple):
            object.__setattr__(self, "foreshadow_actions", NullablePlan(values=self.foreshadow_actions))
        if isinstance(self.forbidden, tuple):
            object.__setattr__(self, "forbidden", NullablePlan(values=self.forbidden))
        if isinstance(self.intent_evidence_bindings, tuple) and all(
            isinstance(binding, FieldEvidenceBinding) for binding in self.intent_evidence_bindings
        ):
            object.__setattr__(
                self,
                "intent_evidence_bindings",
                tuple(sorted(self.intent_evidence_bindings, key=lambda binding: binding.field_path)),
            )

    def validate(self, contract_id: str | None = None, contract_version: int | None = None) -> None:
        _require_text(self.chapter_id, "chapter_id")
        _require_items(self.functions, "chapter functions")
        _require_text(self.dramatic_question, "chapter dramatic_question")
        if not isinstance(self.protagonist_choice, ProtagonistChoice):
            raise NarrativeValidationError("protagonist_choice must be a ProtagonistChoice")
        self.protagonist_choice.validate()
        if not isinstance(self.reader_change, ReaderChange):
            raise NarrativeValidationError("reader_change must be a ReaderChange")
        self.reader_change.validate()
        if not isinstance(self.information, InformationPlan):
            raise NarrativeValidationError("information must be an InformationPlan")
        self.information.validate()
        if not isinstance(self.pressure_curve, PressureCurve):
            raise NarrativeValidationError("pressure_curve must be a PressureCurve")
        self.pressure_curve.validate()
        if not isinstance(self.foreshadow_actions, NullablePlan):
            raise NarrativeValidationError("foreshadow_actions must be a NullablePlan")
        self.foreshadow_actions.validate()
        _require_text(self.ending_shift, "chapter ending_shift")
        _require_positive_integer(self.target_chinese_chars, "chapter target_chinese_chars")
        if not isinstance(self.forbidden, NullablePlan):
            raise NarrativeValidationError("forbidden must be a NullablePlan")
        self.forbidden.validate()
        if not isinstance(self.optional_candidates, tuple):
            raise NarrativeValidationError("optional_candidates must be a tuple")
        for candidate in self.optional_candidates:
            if not isinstance(candidate, OptionalCandidateResolution):
                raise NarrativeValidationError("optional_candidates must contain resolutions")
            candidate.validate()
        if not isinstance(self.intent_evidence_bindings, tuple):
            raise NarrativeValidationError("intent_evidence_bindings must be a tuple")
        if self.intent_evidence_bindings and (contract_id is None or contract_version is None):
            raise NarrativeValidationError("contract identity is required to validate evidence bindings")
        seen_paths: set[str] = set()
        for binding in self.intent_evidence_bindings:
            if not isinstance(binding, FieldEvidenceBinding):
                raise NarrativeValidationError("intent_evidence_bindings must contain field bindings")
            if binding.field_path in seen_paths:
                raise NarrativeValidationError(f"duplicate evidence binding: {binding.field_path}")
            seen_paths.add(binding.field_path)
            assert contract_id is not None and contract_version is not None
            binding.validate(contract_id, contract_version)
        if not isinstance(self.engagement_obligations, tuple):
            raise NarrativeValidationError("engagement_obligations must be a tuple")
        for obligation in self.engagement_obligations:
            if not isinstance(obligation, EngagementObligation):
                raise NarrativeValidationError("engagement_obligations must contain obligations")
            if contract_id is None or contract_version is None:
                raise NarrativeValidationError("contract identity is required for engagement obligations")
            obligation.validate(contract_id, contract_version)
        if not isinstance(self.scene_plan, ScenePlan):
            raise NarrativeValidationError("scene_plan must be a ScenePlan")
        if not isinstance(self.technology_plan, TechnologyPlan):
            raise NarrativeValidationError("technology_plan must be a TechnologyPlan")
        if not isinstance(self.pov_plan, PointOfViewPlan):
            raise NarrativeValidationError("pov_plan must be a PointOfViewPlan")
        self.scene_plan.validate()
        self.technology_plan.validate()
        self.pov_plan.validate()


@dataclass(frozen=True, slots=True)
class NarrativeDecision:
    chapter: int
    profile_id: str
    volume_id: str
    arc_id: str
    arc_phase: ArcPhase
    arc_goal: str
    inherited_pressure: str
    future_pressures: tuple[str, ...]
    chapter_contract: ChapterContract
    contract_id: str = ""
    contract_version: int = 1
    legacy_unclassified_evidence: tuple[LegacyUnclassifiedEvidence, ...] = ()
    schema_version: int = 2
    kind: str = "narrative_decision"

    def __post_init__(self) -> None:
        if _is_positive_integer(self.chapter):
            if not self.contract_id and not self.chapter_contract.chapter_id:
                object.__setattr__(self, "contract_id", f"narrative-chapter-{self.chapter:03d}")
                object.__setattr__(
                    self,
                    "chapter_contract",
                    ChapterContract(
                        functions=self.chapter_contract.functions,
                        dramatic_question=self.chapter_contract.dramatic_question,
                        protagonist_choice=self.chapter_contract.protagonist_choice,
                        reader_change=self.chapter_contract.reader_change,
                        information=self.chapter_contract.information,
                        pressure_curve=self.chapter_contract.pressure_curve,
                        foreshadow_actions=self.chapter_contract.foreshadow_actions,
                        ending_shift=self.chapter_contract.ending_shift,
                        target_chinese_chars=self.chapter_contract.target_chinese_chars,
                        forbidden=self.chapter_contract.forbidden,
                        chapter_id=f"chapter_{self.chapter:03d}",
                        optional_candidates=self.chapter_contract.optional_candidates,
                        intent_evidence_bindings=self.chapter_contract.intent_evidence_bindings,
                        engagement_obligations=self.chapter_contract.engagement_obligations,
                        scene_plan=self.chapter_contract.scene_plan,
                        technology_plan=self.chapter_contract.technology_plan,
                        pov_plan=self.chapter_contract.pov_plan,
                    ),
                )

    def with_chapter(
        self,
        chapter: int,
        *,
        chapter_contract: ChapterContract | None = None,
    ) -> "NarrativeDecision":
        if isinstance(chapter, bool) or not isinstance(chapter, int) or chapter < 1:
            raise NarrativeValidationError("decision chapter must be a positive integer")
        contract = chapter_contract or self.chapter_contract
        return replace(
            self,
            chapter=chapter,
            contract_id=f"narrative-chapter-{chapter:03d}",
            chapter_contract=replace(contract, chapter_id=f"chapter_{chapter:03d}"),
        )

    def validate(self) -> None:
        if type(self.schema_version) is not int or self.schema_version not in (2, 3) or self.kind != "narrative_decision":
            raise NarrativeValidationError("unsupported narrative decision schema")
        _require_positive_integer(self.chapter, "decision chapter")
        if self.contract_id != f"narrative-chapter-{self.chapter:03d}":
            raise NarrativeValidationError("decision contract_id does not match chapter")
        _require_positive_integer(self.contract_version, "decision contract_version")
        if not isinstance(self.chapter_contract, ChapterContract):
            raise NarrativeValidationError("chapter_contract must be a ChapterContract")
        if self.chapter_contract.chapter_id != f"chapter_{self.chapter:03d}":
            raise NarrativeValidationError("chapter_contract chapter_id does not match chapter")
        if not isinstance(self.arc_phase, ArcPhase):
            raise NarrativeValidationError("decision arc_phase must be an ArcPhase")
        _require_text(self.profile_id, "decision profile_id")
        _require_text(self.volume_id, "decision volume_id")
        _require_text(self.arc_id, "decision arc_id")
        _require_text(self.arc_goal, "decision arc_goal")
        _require_text(self.inherited_pressure, "decision inherited_pressure")
        _require_items(self.future_pressures, "decision future_pressures")
        self.chapter_contract.validate(self.contract_id, self.contract_version)
        if self.schema_version == 3 and not self.chapter_contract.engagement_obligations:
            raise NarrativeValidationError("engagement projection is unsatisfied")
        if not isinstance(self.legacy_unclassified_evidence, tuple):
            raise NarrativeValidationError("legacy_unclassified_evidence must be a tuple")
        for evidence in self.legacy_unclassified_evidence:
            if not isinstance(evidence, LegacyUnclassifiedEvidence):
                raise NarrativeValidationError("legacy_unclassified_evidence contains invalid item")
            evidence.validate()

    def to_json(self) -> str:
        from creative_os.domains.narrative_codec import NarrativeDecisionCodec

        return NarrativeDecisionCodec.encode_v2(self)

    @classmethod
    def from_json(cls, content: str) -> "NarrativeDecision":
        from creative_os.domains.narrative_codec import NarrativeDecisionCodec

        return NarrativeDecisionCodec.decode(content)


@dataclass(frozen=True, slots=True)
class NarrativeChangeRequest:
    id: str
    reason: str
    old_plan: str
    new_plan: str
    affected_chapters: tuple[int, ...]
    affected_state_subjects: tuple[str, ...]
    affected_hooks: tuple[str, ...]
    written_text_strategy: WrittenTextStrategy
    status: NarrativeChangeStatus = NarrativeChangeStatus.PROPOSED
    schema_version: int = 1
    kind: str = "narrative_change_request"

    def validate(self) -> None:
        if self.schema_version != 1 or self.kind != "narrative_change_request":
            raise NarrativeValidationError("unsupported narrative change request schema")
        _require_text(self.id, "change request id")
        _require_text(self.reason, "change request reason")
        _require_text(self.old_plan, "change request old_plan")
        _require_text(self.new_plan, "change request new_plan")
        if not self.affected_chapters or any(chapter < 1 for chapter in self.affected_chapters):
            raise NarrativeValidationError("change request affected_chapters must contain positive chapters")
        _require_items(self.affected_state_subjects, "change request affected_state_subjects")
        _require_items(self.affected_hooks, "change request affected_hooks")

    def to_json(self) -> str:
        self.validate()
        return _to_json(self)

    @classmethod
    def from_json(cls, content: str) -> "NarrativeChangeRequest":
        payload = _load_object(content)
        request = cls(
            id=str(payload.get("id", "")),
            reason=str(payload.get("reason", "")),
            old_plan=str(payload.get("old_plan", "")),
            new_plan=str(payload.get("new_plan", "")),
            affected_chapters=tuple(_integer(value, "affected_chapter") for value in _list(payload.get("affected_chapters"), "affected_chapters")),
            affected_state_subjects=_string_tuple(payload.get("affected_state_subjects")),
            affected_hooks=_string_tuple(payload.get("affected_hooks")),
            written_text_strategy=_enum(WrittenTextStrategy, payload.get("written_text_strategy"), "written_text_strategy"),
            status=_enum(NarrativeChangeStatus, payload.get("status", NarrativeChangeStatus.PROPOSED), "status"),
            schema_version=_integer(payload.get("schema_version", 1), "schema_version"),
            kind=str(payload.get("kind", "")),
        )
        request.validate()
        return request


def _to_json(value: object) -> str:
    return json.dumps(asdict(value), ensure_ascii=False, sort_keys=True)


def _load_object(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise NarrativeValidationError("narrative content must be valid JSON") from error
    return _object(payload, "root")


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NarrativeValidationError(f"{name} must be an object")
    return value


def _object_list(value: object, name: str) -> list[dict[str, Any]]:
    return [_object(item, name) for item in _list(value, name)]


def _list(value: object, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise NarrativeValidationError(f"{name} must be a list")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in _list(value, "string list"))


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise NarrativeValidationError(f"{name} must be an integer")
    return value


def _enum(enum_type: type[StrEnum], value: object, name: str) -> StrEnum:
    try:
        return enum_type(value)
    except ValueError as error:
        raise NarrativeValidationError(f"invalid {name}: {value}") from error


def _require_text(value: str | None, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise NarrativeValidationError(f"{name} is required")


def _require_items(values: tuple[object, ...], name: str) -> None:
    _require_string_tuple(values, name)


def _require_non_empty_tuple(values: object, name: str) -> None:
    if not isinstance(values, tuple) or not values:
        raise NarrativeValidationError(f"{name} requires a non-empty tuple")


def _require_string_tuple(values: object, name: str, *, allow_empty: bool = False) -> None:
    if not isinstance(values, tuple):
        raise NarrativeValidationError(f"{name} must be a tuple")
    if not allow_empty and not values:
        raise NarrativeValidationError(f"{name} requires non-empty items")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise NarrativeValidationError(f"{name} must contain non-empty strings")


def _is_positive_integer(value: object) -> bool:
    return type(value) is int and value > 0


def _require_positive_integer(value: object, name: str) -> None:
    if not _is_positive_integer(value):
        raise NarrativeValidationError(f"{name} must be a positive integer")


def _require_enum_member(enum_type: type[StrEnum], value: object, name: str) -> StrEnum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise NarrativeValidationError(f"invalid {name}: {value}") from error
