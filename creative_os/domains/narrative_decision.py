from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


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
        _require_items(self.volumes, "profile volumes")
        _require_items(self.arcs, "profile arcs")
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
    actor: str
    action: str
    alternatives: tuple[str, ...]
    cost: str
    consequence: str

    def validate(self) -> None:
        _require_text(self.actor, "protagonist choice actor")
        _require_text(self.action, "protagonist choice action")
        _require_items(self.alternatives, "protagonist choice alternatives")
        _require_text(self.cost, "protagonist choice cost")
        _require_text(self.consequence, "protagonist choice consequence")


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
    misdirect: tuple[str, ...]

    def validate(self) -> None:
        _require_items(self.reveal, "information reveal")
        _require_items(self.withhold, "information withhold")


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
    foreshadow_actions: tuple[str, ...]
    ending_shift: str
    target_chinese_chars: int
    forbidden: tuple[str, ...]
    scene_plan: ScenePlan = ScenePlan()
    technology_plan: TechnologyPlan = TechnologyPlan()
    pov_plan: PointOfViewPlan = PointOfViewPlan()

    def validate(self) -> None:
        _require_items(self.functions, "chapter functions")
        _require_text(self.dramatic_question, "chapter dramatic_question")
        self.protagonist_choice.validate()
        self.reader_change.validate()
        self.information.validate()
        self.pressure_curve.validate()
        _require_items(self.foreshadow_actions, "chapter foreshadow_actions")
        _require_text(self.ending_shift, "chapter ending_shift")
        if self.target_chinese_chars <= 0:
            raise NarrativeValidationError("chapter target_chinese_chars must be positive")
        _require_items(self.forbidden, "chapter forbidden")
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
    schema_version: int = 1
    kind: str = "narrative_decision"

    def validate(self) -> None:
        if self.schema_version not in {1, 2} or self.kind != "narrative_decision":
            raise NarrativeValidationError("unsupported narrative decision schema")
        if self.chapter < 1:
            raise NarrativeValidationError("decision chapter must be positive")
        _require_text(self.profile_id, "decision profile_id")
        _require_text(self.volume_id, "decision volume_id")
        _require_text(self.arc_id, "decision arc_id")
        _require_text(self.arc_goal, "decision arc_goal")
        _require_text(self.inherited_pressure, "decision inherited_pressure")
        _require_items(self.future_pressures, "decision future_pressures")
        self.chapter_contract.validate()
        if self.schema_version == 2:
            self.chapter_contract.scene_plan.validate(required=True)

    def to_json(self) -> str:
        self.validate()
        return _to_json(self)

    @classmethod
    def from_json(cls, content: str) -> "NarrativeDecision":
        payload = _load_object(content)
        contract = _object(payload.get("chapter_contract"), "chapter_contract")
        choice = _object(contract.get("protagonist_choice"), "protagonist_choice")
        reader = _object(contract.get("reader_change"), "reader_change")
        information = _object(contract.get("information"), "information")
        pressure = _object(contract.get("pressure_curve"), "pressure_curve")
        scene_plan = _object(contract.get("scene_plan", {}), "scene_plan")
        technology_plan = _object(contract.get("technology_plan", {}), "technology_plan")
        pov_plan = _object(contract.get("pov_plan", {}), "pov_plan")
        decision = cls(
            chapter=_integer(payload.get("chapter"), "chapter"),
            profile_id=str(payload.get("profile_id", "")),
            volume_id=str(payload.get("volume_id", "")),
            arc_id=str(payload.get("arc_id", "")),
            arc_phase=_enum(ArcPhase, payload.get("arc_phase"), "arc_phase"),
            arc_goal=str(payload.get("arc_goal", "")),
            inherited_pressure=str(payload.get("inherited_pressure", "")),
            future_pressures=_string_tuple(payload.get("future_pressures")),
            chapter_contract=ChapterContract(
                functions=_string_tuple(contract.get("functions")),
                dramatic_question=str(contract.get("dramatic_question", "")),
                protagonist_choice=ProtagonistChoice(
                    actor=str(choice.get("actor", "")),
                    action=str(choice.get("action", "")),
                    alternatives=_string_tuple(choice.get("alternatives")),
                    cost=str(choice.get("cost", "")),
                    consequence=str(choice.get("consequence", "")),
                ),
                reader_change=ReaderChange(before=str(reader.get("before", "")), after=str(reader.get("after", ""))),
                information=InformationPlan(
                    reveal=_string_tuple(information.get("reveal")),
                    withhold=_string_tuple(information.get("withhold")),
                    misdirect=_string_tuple(information.get("misdirect")),
                ),
                pressure_curve=PressureCurve(
                    start=str(pressure.get("start", "")),
                    turn=str(pressure.get("turn", "")),
                    end=str(pressure.get("end", "")),
                ),
                foreshadow_actions=_string_tuple(contract.get("foreshadow_actions")),
                ending_shift=str(contract.get("ending_shift", "")),
                target_chinese_chars=_integer(contract.get("target_chinese_chars"), "target_chinese_chars"),
                forbidden=_string_tuple(contract.get("forbidden")),
                scene_plan=ScenePlan(
                    scenes=tuple(SceneContract(
                        id=str(item.get("id", "")), order=_integer(item.get("order"), "scene order"),
                        place_id=str(item.get("place_id", "")), place_label=str(item.get("place_label", "")),
                        place_class=str(item.get("place_class", "")), interior_exterior=str(item.get("interior_exterior", "")),
                        time_window=str(item.get("time_window", "")), participants=_string_tuple(item.get("participants")),
                        viewpoint=str(item.get("viewpoint", "")), ordinary_people_present=bool(item.get("ordinary_people_present", False)),
                        goal=str(item.get("goal", "")), conflict=str(item.get("conflict", "")), action=str(item.get("action", "")),
                        information_change=str(item.get("information_change", "")), state_change=str(item.get("state_change", "")),
                        entry_reason=str(item.get("entry_reason", "")), exit_trigger=str(item.get("exit_trigger", "")),
                        inherited_from_previous=bool(item.get("inherited_from_previous", False)),
                    ) for item in _object_list(scene_plan.get("scenes", []), "scenes")),
                    chapter_spatial_intent=str(scene_plan.get("chapter_spatial_intent", "")),
                    required_world_slice=str(scene_plan.get("required_world_slice", "")),
                    allowed_same_place_run=_integer(scene_plan.get("allowed_same_place_run", 3), "allowed_same_place_run"),
                    exception_reason=str(scene_plan.get("exception_reason", "")),
                ),
                technology_plan=TechnologyPlan(technologies=tuple(TechnologyContract(
                    id=str(item.get("id", "")), name=str(item.get("name", "")), role=str(item.get("role", "")),
                    birth_reason=str(item.get("birth_reason", "")), source=str(item.get("source", "")),
                    prerequisites=_string_tuple(item.get("prerequisites")), validation_stage=str(item.get("validation_stage", "")),
                    first_application=str(item.get("first_application", "")), social_diffusion=_string_tuple(item.get("social_diffusion")),
                    cost=str(item.get("cost", "")), changed_domains=_string_tuple(item.get("changed_domains")),
                ) for item in _object_list(technology_plan.get("technologies", []), "technologies"))),
                pov_plan=PointOfViewPlan(
                    primary_owner=str(pov_plan.get("primary_owner", "")),
                    mode=str(pov_plan.get("mode", "")),
                    protagonist_present=bool(pov_plan.get("protagonist_present", True)),
                    supporting_agency=tuple(SupportingAgencyContract(
                        actor=str(item.get("actor", "")),
                        independent_goal=str(item.get("independent_goal", "")),
                        resistance=str(item.get("resistance", "")),
                        choice=str(item.get("choice", "")),
                        cost=str(item.get("cost", "")),
                        result=str(item.get("result", "")),
                        mainline_change=str(item.get("mainline_change", "")),
                    ) for item in _object_list(pov_plan.get("supporting_agency", []), "supporting_agency")),
                    rationale=str(pov_plan.get("rationale", "")),
                ),
            ),
            schema_version=_integer(payload.get("schema_version", 1), "schema_version"),
            kind=str(payload.get("kind", "")),
        )
        decision.validate()
        return decision


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


def _require_text(value: str, name: str) -> None:
    if not value.strip():
        raise NarrativeValidationError(f"{name} is required")


def _require_items(values: tuple[object, ...], name: str) -> None:
    if not values or any(not str(value).strip() for value in values):
        raise NarrativeValidationError(f"{name} requires non-empty items")
