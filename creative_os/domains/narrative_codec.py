from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from collections.abc import Mapping
from typing import Any

from creative_os.domains.narrative_decision import (
    ArcPhase,
    CandidateDecisionBy,
    CandidateImpact,
    CandidateKind,
    CandidateValueState,
    ChapterContract,
    EngagementObligation,
    ChoiceStatus,
    FieldEvidenceBinding,
    InformationPlan,
    LegacyUnclassifiedEvidence,
    NarrativeDecision,
    NarrativeValidationError,
    NullablePlan,
    OptionalCandidateResolution,
    PressureCurve,
    ProtagonistChoice,
    PointOfViewPlan,
    ReaderChange,
    SceneClosure,
    SceneContract,
    ScenePlan,
    SupportingAgencyContract,
    TechnologyContract,
    TechnologyPlan,
)
from creative_os.domains.narrative_evidence import EvidenceLocator, EvidenceRef, EvidenceRole


class NarrativeDecisionCodec:
    """The only schema-version dispatch and canonical serialization boundary."""

    @classmethod
    def decode(cls, content: str | bytes | Mapping[str, Any]) -> NarrativeDecision:
        payload = cls._payload(content)
        if "schema_version" not in payload:
            if not cls._is_exact_v1_shape(payload):
                raise NarrativeValidationError("schema_version is required for non-legacy narrative decision")
            return cls.decode_v1(payload)
        version = cls._integer(payload["schema_version"], "schema_version")
        if version == 1:
            if not cls._is_exact_v1_shape(payload):
                raise NarrativeValidationError("schema_version=2 is required for v2 narrative fields")
            return cls.decode_v1(payload)
        if version == 2:
            if "contract_id" not in payload:
                payload = cls._adapt_legacy_scene_v2_payload(payload)
            return cls.decode_v2(payload)
        if version == 3:
            if not isinstance(payload.get("chapter_contract"), Mapping) or "engagement_obligations" not in payload["chapter_contract"]:
                raise NarrativeValidationError("unsupported narrative decision schema: 3")
            return cls.decode_v3(payload)
        raise NarrativeValidationError(f"unsupported narrative decision schema: {version}")

    @classmethod
    def _adapt_legacy_scene_v2_payload(cls, payload: Mapping[str, Any]) -> dict[str, Any]:
        """将 Scene/Technology Gate 上线期的无信封 v2 合同投影为统一 v2 读取形态。"""
        required_root = {
            "schema_version", "kind", "chapter", "profile_id", "volume_id", "arc_id",
            "arc_phase", "arc_goal", "inherited_pressure", "future_pressures", "chapter_contract",
        }
        if set(payload) != required_root:
            raise NarrativeValidationError("legacy scene v2 root shape is invalid")
        chapter = cls._integer(payload["chapter"], "chapter")
        contract = dict(cls._object(payload["chapter_contract"], "chapter_contract"))
        required_contract = {
            "functions", "dramatic_question", "protagonist_choice", "reader_change", "information",
            "pressure_curve", "foreshadow_actions", "ending_shift", "target_chinese_chars", "forbidden",
            "scene_plan", "technology_plan",
        }
        if not required_contract <= set(contract) <= required_contract | {"pov_plan"}:
            raise NarrativeValidationError("legacy scene v2 chapter contract shape is invalid")
        choice = dict(cls._object(contract["protagonist_choice"], "protagonist_choice"))
        cls._require_fields(choice, {"actor", "action", "alternatives", "cost", "consequence"}, "legacy protagonist_choice")
        missing = cls._choice_missing(
            cls._optional_text(choice["actor"]),
            cls._optional_text(choice["action"]),
            cls._strings(choice["alternatives"], "alternatives", allow_empty=True),
            cls._optional_text(choice["cost"]),
            cls._optional_text(choice["consequence"]),
        )
        choice["missing_fields"] = list(missing)
        choice["status"] = (ChoiceStatus.UNKNOWN if len(missing) == 5 else ChoiceStatus.PARTIAL if missing else ChoiceStatus.COMPLETE).value
        information = dict(cls._object(contract["information"], "information"))
        information["misdirect"] = cls._legacy_nullable_payload(information.get("misdirect"), "information.misdirect")
        contract["information"] = information
        contract["protagonist_choice"] = choice
        contract["foreshadow_actions"] = cls._legacy_nullable_payload(contract["foreshadow_actions"], "foreshadow_actions")
        contract["forbidden"] = cls._legacy_nullable_payload(contract["forbidden"], "forbidden")
        contract["chapter_id"] = f"chapter_{chapter:03d}"
        contract["optional_candidates"] = []
        contract["intent_evidence_bindings"] = {}
        return {
            **payload,
            "contract_id": f"narrative-chapter-{chapter:03d}",
            "contract_version": 1,
            "chapter_contract": contract,
            "legacy_unclassified_evidence": [],
        }

    @classmethod
    def _legacy_nullable_payload(cls, value: object, name: str) -> dict[str, Any]:
        values = cls._strings(value, name, allow_empty=True)
        return {
            "values": list(values),
            "not_applicable_reason": None if values else "历史合同明确无适用项",
        }

    @classmethod
    def decode_v1(cls, content: str | bytes | Mapping[str, Any]) -> NarrativeDecision:
        payload = cls._payload(content)
        version = cls._integer(payload.get("schema_version", 1), "schema_version")
        if version != 1:
            raise NarrativeValidationError(f"decode_v1 requires schema 1, got {version}")
        if payload.get("kind", "narrative_decision") != "narrative_decision":
            raise NarrativeValidationError("unsupported narrative decision kind")

        chapter = cls._integer(payload.get("chapter"), "chapter")
        contract = cls._object(payload.get("chapter_contract"), "chapter_contract")
        choice_payload = cls._object(contract.get("protagonist_choice"), "protagonist_choice")
        choice = cls._decode_v1_choice(choice_payload)
        reader = cls._object(contract.get("reader_change"), "reader_change")
        information = cls._object(contract.get("information"), "information")
        pressure = cls._object(contract.get("pressure_curve"), "pressure_curve")
        legacy_evidence = cls._decode_legacy_evidence(
            payload.get("evidence", contract.get("evidence", []))
        )
        decision = NarrativeDecision(
            contract_id=f"narrative-chapter-{chapter:03d}",
            contract_version=1,
            chapter=chapter,
            profile_id=cls._text(payload.get("profile_id"), "profile_id"),
            volume_id=cls._text(payload.get("volume_id"), "volume_id"),
            arc_id=cls._text(payload.get("arc_id"), "arc_id"),
            arc_phase=cls._enum(ArcPhase, payload.get("arc_phase"), "arc_phase"),
            arc_goal=cls._text(payload.get("arc_goal"), "arc_goal"),
            inherited_pressure=cls._text(payload.get("inherited_pressure"), "inherited_pressure"),
            future_pressures=cls._strings(payload.get("future_pressures"), "future_pressures"),
            chapter_contract=ChapterContract(
                chapter_id=f"chapter_{chapter:03d}",
                functions=cls._strings(contract.get("functions"), "functions"),
                dramatic_question=cls._text(contract.get("dramatic_question"), "dramatic_question"),
                protagonist_choice=choice,
                reader_change=ReaderChange(
                    before=cls._text(reader.get("before"), "reader_change.before"),
                    after=cls._text(reader.get("after"), "reader_change.after"),
                ),
                information=InformationPlan(
                    reveal=cls._strings(information.get("reveal"), "information.reveal"),
                    withhold=cls._strings(information.get("withhold"), "information.withhold"),
                    misdirect=NullablePlan(
                        values=cls._strings(
                            information.get("misdirect"), "information.misdirect", allow_empty=True
                        )
                    ),
                ),
                pressure_curve=PressureCurve(
                    start=cls._text(pressure.get("start"), "pressure_curve.start"),
                    turn=cls._text(pressure.get("turn"), "pressure_curve.turn"),
                    end=cls._text(pressure.get("end"), "pressure_curve.end"),
                ),
                foreshadow_actions=NullablePlan(
                    values=cls._strings(
                        contract.get("foreshadow_actions"), "foreshadow_actions", allow_empty=True
                    )
                ),
                ending_shift=cls._text(contract.get("ending_shift"), "ending_shift"),
                target_chinese_chars=cls._integer(
                    contract.get("target_chinese_chars"), "target_chinese_chars"
                ),
                forbidden=NullablePlan(
                    values=cls._strings(contract.get("forbidden"), "forbidden", allow_empty=True)
                ),
            ),
            legacy_unclassified_evidence=legacy_evidence,
        )
        decision.validate()
        return decision

    @classmethod
    def decode_v2(cls, content: str | bytes | Mapping[str, Any]) -> NarrativeDecision:
        payload = cls._payload(content)
        cls._require_fields(
            payload,
            {
                "schema_version",
                "kind",
                "contract_id",
                "contract_version",
                "chapter",
                "profile_id",
                "volume_id",
                "arc_id",
                "arc_phase",
                "arc_goal",
                "inherited_pressure",
                "future_pressures",
                "chapter_contract",
                "legacy_unclassified_evidence",
            },
            "root",
        )
        if cls._integer(payload["schema_version"], "schema_version") != 2:
            raise NarrativeValidationError("decode_v2 requires schema 2")
        if payload["kind"] != "narrative_decision":
            raise NarrativeValidationError("unsupported narrative decision kind")

        contract_id = cls._text(payload["contract_id"], "contract_id")
        contract_version = cls._integer(payload["contract_version"], "contract_version")
        contract = cls._object(payload["chapter_contract"], "chapter_contract")
        cls._require_fields_with_optional(
            contract,
            {
                "chapter_id",
                "functions",
                "dramatic_question",
                "protagonist_choice",
                "reader_change",
                "information",
                "pressure_curve",
                "foreshadow_actions",
                "ending_shift",
                "target_chinese_chars",
                "forbidden",
                "optional_candidates",
                "intent_evidence_bindings",
            },
            {"scene_plan", "technology_plan", "pov_plan"},
            "chapter_contract",
        )
        choice = cls._decode_v2_choice(cls._object(contract["protagonist_choice"], "protagonist_choice"))
        reader = cls._object(contract["reader_change"], "reader_change")
        cls._require_fields(reader, {"before", "after"}, "reader_change")
        information = cls._object(contract["information"], "information")
        cls._require_fields(information, {"reveal", "withhold", "misdirect"}, "information")
        pressure = cls._object(contract["pressure_curve"], "pressure_curve")
        cls._require_fields(pressure, {"start", "turn", "end"}, "pressure_curve")

        decision = NarrativeDecision(
            contract_id=contract_id,
            contract_version=contract_version,
            chapter=cls._integer(payload["chapter"], "chapter"),
            profile_id=cls._text(payload["profile_id"], "profile_id"),
            volume_id=cls._text(payload["volume_id"], "volume_id"),
            arc_id=cls._text(payload["arc_id"], "arc_id"),
            arc_phase=cls._enum(ArcPhase, payload["arc_phase"], "arc_phase"),
            arc_goal=cls._text(payload["arc_goal"], "arc_goal"),
            inherited_pressure=cls._text(payload["inherited_pressure"], "inherited_pressure"),
            future_pressures=cls._strings(payload["future_pressures"], "future_pressures"),
            chapter_contract=ChapterContract(
                chapter_id=cls._text(contract["chapter_id"], "chapter_id"),
                functions=cls._strings(contract["functions"], "functions"),
                dramatic_question=cls._text(contract["dramatic_question"], "dramatic_question"),
                protagonist_choice=choice,
                reader_change=ReaderChange(
                    before=cls._text(reader["before"], "reader_change.before"),
                    after=cls._text(reader["after"], "reader_change.after"),
                ),
                information=InformationPlan(
                    reveal=cls._strings(information["reveal"], "information.reveal"),
                    withhold=cls._strings(information["withhold"], "information.withhold"),
                    misdirect=cls._decode_nullable(information["misdirect"], "information.misdirect"),
                ),
                pressure_curve=PressureCurve(
                    start=cls._text(pressure["start"], "pressure_curve.start"),
                    turn=cls._text(pressure["turn"], "pressure_curve.turn"),
                    end=cls._text(pressure["end"], "pressure_curve.end"),
                ),
                foreshadow_actions=cls._decode_nullable(contract["foreshadow_actions"], "foreshadow_actions"),
                ending_shift=cls._text(contract["ending_shift"], "ending_shift"),
                target_chinese_chars=cls._integer(contract["target_chinese_chars"], "target_chinese_chars"),
                forbidden=cls._decode_nullable(contract["forbidden"], "forbidden"),
                optional_candidates=tuple(
                    cls._decode_candidate(item)
                    for item in cls._objects(contract["optional_candidates"], "optional_candidates")
                ),
                intent_evidence_bindings=cls._decode_bindings(
                    contract["intent_evidence_bindings"], contract_id, contract_version
                ),
                scene_plan=cls._decode_scene_plan(contract.get("scene_plan")),
                technology_plan=cls._decode_technology_plan(contract.get("technology_plan")),
                pov_plan=cls._decode_pov_plan(contract.get("pov_plan")),
            ),
            legacy_unclassified_evidence=cls._decode_v2_legacy_evidence(
                payload["legacy_unclassified_evidence"]
            ),
        )
        decision.validate()
        return decision

    @classmethod
    def encode_v2(cls, decision: NarrativeDecision) -> str:
        if not isinstance(decision, NarrativeDecision):
            raise NarrativeValidationError("encode_v2 requires NarrativeDecision")
        decision.validate()
        return cls.canonical_json(cls._encode_decision(decision))

    @classmethod
    def encode_v3(cls, decision: NarrativeDecision) -> str:
        if not isinstance(decision, NarrativeDecision):
            raise NarrativeValidationError("encode_v3 requires NarrativeDecision")
        if not decision.chapter_contract.engagement_obligations:
            raise NarrativeValidationError("engagement obligations are required for v3")
        decision.validate()
        payload = cls._encode_decision(decision)
        payload["schema_version"] = 3
        payload["chapter_contract"]["engagement_obligations"] = [
            {
                "action": item.action,
                "expectation_id": item.expectation_id,
                "projection_hash": item.projection_hash,
                "deadline_chapter": item.deadline_chapter,
                "intent_evidence": [cls._encode_evidence(ref) for ref in item.intent_evidence],
            }
            for item in decision.chapter_contract.engagement_obligations
        ]
        return cls.canonical_json(payload)

    @classmethod
    def encode(cls, decision: NarrativeDecision) -> str:
        if not isinstance(decision, NarrativeDecision):
            raise NarrativeValidationError("encode requires NarrativeDecision")
        if decision.schema_version == 2:
            return cls.encode_v2(decision)
        if decision.schema_version == 3:
            return cls.encode_v3(decision)
        raise NarrativeValidationError(f"unsupported schema version: {decision.schema_version}")

    @classmethod
    def decode_v3(cls, content: str | bytes | Mapping[str, Any]) -> NarrativeDecision:
        payload = cls._payload(content)
        if cls._integer(payload.get("schema_version"), "schema_version") != 3:
            raise NarrativeValidationError("decode_v3 requires schema 3")
        contract = cls._object(payload.get("chapter_contract"), "chapter_contract")
        obligations = []
        for item in cls._objects(contract.get("engagement_obligations"), "engagement_obligations"):
            refs = tuple(cls._decode_evidence(ref) for ref in cls._objects(item.get("intent_evidence"), "intent_evidence"))
            obligations.append(EngagementObligation(
                action=cls._text(item.get("action"), "engagement action"),
                expectation_id=cls._text(item.get("expectation_id"), "expectation_id"),
                intent_evidence=refs,
                projection_hash=cls._text(item.get("projection_hash"), "projection_hash"),
                deadline_chapter=item.get("deadline_chapter"),
            ))
        base = dict(payload)
        base["schema_version"] = 2
        base_contract = dict(contract)
        base_contract.pop("engagement_obligations", None)
        base["chapter_contract"] = base_contract
        decoded = cls.decode_v2(base)
        updated = replace(decoded.chapter_contract, engagement_obligations=tuple(obligations))
        return replace(decoded, chapter_contract=updated, schema_version=3)

    @classmethod
    def adapt_v2_to_v3(cls, content: str | bytes | Mapping[str, Any]) -> NarrativeDecision:
        decoded = cls.decode_v2(content)
        return replace(decoded, schema_version=3)

    @staticmethod
    def schema_version(content: str | bytes | Mapping[str, Any]) -> int:
        payload = NarrativeDecisionCodec._payload(content)
        return NarrativeDecisionCodec._integer(payload.get("schema_version"), "schema_version")

    @classmethod
    def content_hash(cls, value: NarrativeDecision | Mapping[str, Any] | str | bytes) -> str:
        canonical = cls.encode(value) if isinstance(value, NarrativeDecision) else cls.canonical_json(value)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def canonical_json(cls, value: Mapping[str, Any] | str | bytes) -> str:
        payload = cls._payload(value) if isinstance(value, (str, bytes)) else value
        if not isinstance(payload, Mapping):
            raise NarrativeValidationError("canonical JSON root must be an object")
        try:
            return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise NarrativeValidationError("content must be JSON serializable") from error

    @staticmethod
    def _encode_decision(decision: NarrativeDecision) -> dict[str, Any]:
        contract = decision.chapter_contract
        choice = contract.protagonist_choice
        return {
            "schema_version": 2,
            "kind": decision.kind,
            "contract_id": decision.contract_id,
            "contract_version": decision.contract_version,
            "chapter": decision.chapter,
            "profile_id": decision.profile_id,
            "volume_id": decision.volume_id,
            "arc_id": decision.arc_id,
            "arc_phase": decision.arc_phase.value,
            "arc_goal": decision.arc_goal,
            "inherited_pressure": decision.inherited_pressure,
            "future_pressures": list(decision.future_pressures),
            "chapter_contract": {
                "chapter_id": contract.chapter_id,
                "functions": list(contract.functions),
                "dramatic_question": contract.dramatic_question,
                "protagonist_choice": {
                    "status": choice.status.value,
                    "actor": choice.actor,
                    "action": choice.action,
                    "alternatives": list(choice.alternatives),
                    "cost": choice.cost,
                    "consequence": choice.consequence,
                    "missing_fields": list(choice.missing_fields),
                },
                "reader_change": {"before": contract.reader_change.before, "after": contract.reader_change.after},
                "information": {
                    "reveal": list(contract.information.reveal),
                    "withhold": list(contract.information.withhold),
                    "misdirect": NarrativeDecisionCodec._encode_nullable(contract.information.misdirect),
                },
                "pressure_curve": {
                    "start": contract.pressure_curve.start,
                    "turn": contract.pressure_curve.turn,
                    "end": contract.pressure_curve.end,
                },
                "foreshadow_actions": NarrativeDecisionCodec._encode_nullable(contract.foreshadow_actions),
                "ending_shift": contract.ending_shift,
                "target_chinese_chars": contract.target_chinese_chars,
                "forbidden": NarrativeDecisionCodec._encode_nullable(contract.forbidden),
                "optional_candidates": [
                    {
                        "candidate_id": item.candidate_id,
                        "kind": NarrativeDecisionCodec._enum_value(item.kind),
                        "value_state": NarrativeDecisionCodec._enum_value(item.value_state),
                        "proposed_value": item.proposed_value,
                        "dependency_inputs": list(item.dependency_inputs),
                        "affects_current_chapter": NarrativeDecisionCodec._enum_value(item.affects_current_chapter),
                        "rationale": item.rationale,
                        "decided_by": NarrativeDecisionCodec._enum_value(item.decided_by),
                        "decision_ref": item.decision_ref,
                    }
                    for item in contract.optional_candidates
                ],
                "intent_evidence_bindings": {
                    binding.field_path: [NarrativeDecisionCodec._encode_evidence(ref) for ref in binding.evidence]
                    for binding in contract.intent_evidence_bindings
                },
                "scene_plan": {
                    "scenes": [
                        {
                            "id": item.id,
                            "order": item.order,
                            "place_id": item.place_id,
                            "place_label": item.place_label,
                            "place_class": item.place_class,
                            "interior_exterior": item.interior_exterior,
                            "time_window": item.time_window,
                            "participants": list(item.participants),
                            "viewpoint": item.viewpoint,
                            "ordinary_people_present": item.ordinary_people_present,
                            "goal": item.goal,
                            "conflict": item.conflict,
                            "action": item.action,
                            "information_change": item.information_change,
                            "state_change": item.state_change,
                            "entry_reason": item.entry_reason,
                            "exit_trigger": item.exit_trigger,
                            "inherited_from_previous": item.inherited_from_previous,
                            **({
                                "narrative_purpose": item.narrative_purpose,
                                "essential_information": list(item.essential_information),
                                "emotional_change": item.emotional_change,
                                "closure": {
                                    "goal_addressed": item.closure.goal_addressed,
                                    "conflict_advanced": item.closure.conflict_advanced,
                                    "choice_made": item.closure.choice_made,
                                    "outcome_recorded": item.closure.outcome_recorded,
                                },
                            } if (
                                item.narrative_purpose
                                or item.essential_information
                                or item.emotional_change
                                or item.closure != SceneClosure()
                            ) else {}),
                        }
                        for item in contract.scene_plan.scenes
                    ],
                    "chapter_spatial_intent": contract.scene_plan.chapter_spatial_intent,
                    "required_world_slice": contract.scene_plan.required_world_slice,
                    "allowed_same_place_run": contract.scene_plan.allowed_same_place_run,
                    "exception_reason": contract.scene_plan.exception_reason,
                },
                "technology_plan": {
                    "technologies": [
                        {
                            "id": item.id,
                            "name": item.name,
                            "role": item.role,
                            "birth_reason": item.birth_reason,
                            "source": item.source,
                            "prerequisites": list(item.prerequisites),
                            "validation_stage": item.validation_stage,
                            "first_application": item.first_application,
                            "social_diffusion": list(item.social_diffusion),
                            "cost": item.cost,
                            "changed_domains": list(item.changed_domains),
                        }
                        for item in contract.technology_plan.technologies
                    ]
                },
                "pov_plan": {
                    "primary_owner": contract.pov_plan.primary_owner,
                    "mode": contract.pov_plan.mode,
                    "protagonist_present": contract.pov_plan.protagonist_present,
                    "supporting_agency": [
                        {
                            "actor": item.actor,
                            "independent_goal": item.independent_goal,
                            "resistance": item.resistance,
                            "choice": item.choice,
                            "cost": item.cost,
                            "result": item.result,
                            "mainline_change": item.mainline_change,
                        }
                        for item in contract.pov_plan.supporting_agency
                    ],
                    "rationale": contract.pov_plan.rationale,
                },
            },
            "legacy_unclassified_evidence": [
                {
                    "source_type": item.source_type,
                    "source_ref": item.source_ref,
                    "excerpt": item.excerpt,
                    "classification": item.classification,
                }
                for item in decision.legacy_unclassified_evidence
            ],
        }

    @staticmethod
    def _encode_nullable(plan: NullablePlan) -> dict[str, Any]:
        return {"values": list(plan.values), "not_applicable_reason": plan.not_applicable_reason}

    @staticmethod
    def _encode_evidence(ref: EvidenceRef) -> dict[str, Any]:
        assert ref.role is not None and ref.locator is not None
        payload = {
            "evidence_id": ref.evidence_id,
            "contract_id": ref.contract_id,
            "contract_version": ref.contract_version,
            "field_path": ref.field_path,
            "role": ref.role.value,
            "source_id": ref.source_id,
            "source_version": ref.source_version,
            "source_content_hash": ref.source_content_hash,
            "locator": {"kind": ref.locator.kind, "value": ref.locator.value},
            "excerpt": ref.excerpt,
            "assertion": ref.assertion,
        }
        if ref.asserted_value is not None:
            payload["asserted_value"] = ref.asserted_value
        return payload

    @classmethod
    def _decode_v1_choice(cls, payload: Mapping[str, Any]) -> ProtagonistChoice:
        actor = cls._optional_text(payload.get("actor"))
        action = cls._optional_text(payload.get("action"))
        alternatives = cls._strings(payload.get("alternatives", []), "alternatives", allow_empty=True)
        cost = cls._optional_text(payload.get("cost"))
        consequence = cls._optional_text(payload.get("consequence"))
        missing = cls._choice_missing(actor, action, alternatives, cost, consequence)
        status = ChoiceStatus.UNKNOWN if len(missing) == 5 else ChoiceStatus.PARTIAL if missing else ChoiceStatus.COMPLETE
        return ProtagonistChoice(actor, action, alternatives, cost, consequence, status, missing)

    @classmethod
    def _decode_v2_choice(cls, payload: Mapping[str, Any]) -> ProtagonistChoice:
        cls._require_fields(
            payload,
            {"status", "actor", "action", "alternatives", "cost", "consequence", "missing_fields"},
            "protagonist_choice",
        )
        choice = ProtagonistChoice(
            actor=cls._optional_text(payload["actor"]),
            action=cls._optional_text(payload["action"]),
            alternatives=cls._strings(payload["alternatives"], "alternatives", allow_empty=True),
            cost=cls._optional_text(payload["cost"]),
            consequence=cls._optional_text(payload["consequence"]),
            status=cls._enum(ChoiceStatus, payload["status"], "choice status"),
            missing_fields=cls._strings(payload["missing_fields"], "missing_fields", allow_empty=True),
        )
        choice.validate()
        return choice

    @classmethod
    def _decode_scene_plan(cls, value: object) -> ScenePlan:
        if value is None:
            return ScenePlan()
        payload = cls._object(value, "scene_plan")
        cls._require_fields(
            payload,
            {"scenes", "chapter_spatial_intent", "required_world_slice", "allowed_same_place_run", "exception_reason"},
            "scene_plan",
        )
        scenes = []
        for raw in cls._objects(payload["scenes"], "scene_plan.scenes"):
            cls._require_fields_with_optional(
                raw,
                {
                    "id", "order", "place_id", "place_label", "place_class", "interior_exterior",
                    "time_window", "participants", "viewpoint", "ordinary_people_present", "goal",
                    "conflict", "action", "information_change", "state_change", "entry_reason", "exit_trigger",
                    "inherited_from_previous",
                },
                {"narrative_purpose", "essential_information", "emotional_change", "closure"},
                "scene_contract",
            )
            closure_raw = raw.get("closure")
            if closure_raw is None:
                closure = SceneClosure()
            else:
                closure_payload = cls._object(closure_raw, "scene closure")
                cls._require_fields(
                    closure_payload,
                    {"goal_addressed", "conflict_advanced", "choice_made", "outcome_recorded"},
                    "scene closure",
                )
                closure = SceneClosure(
                    goal_addressed=bool(closure_payload["goal_addressed"]),
                    conflict_advanced=bool(closure_payload["conflict_advanced"]),
                    choice_made=bool(closure_payload["choice_made"]),
                    outcome_recorded=bool(closure_payload["outcome_recorded"]),
                )
            scenes.append(SceneContract(
                id=cls._text(raw["id"], "scene id"),
                order=cls._integer(raw["order"], "scene order"),
                place_id=cls._text(raw["place_id"], "scene place_id"),
                place_label=cls._text(raw["place_label"], "scene place_label"),
                place_class=cls._text(raw["place_class"], "scene place_class"),
                interior_exterior=cls._text(raw["interior_exterior"], "scene interior_exterior"),
                time_window=cls._text(raw["time_window"], "scene time_window"),
                participants=cls._strings(raw["participants"], "scene participants"),
                viewpoint=cls._text(raw["viewpoint"], "scene viewpoint"),
                ordinary_people_present=bool(raw["ordinary_people_present"]),
                goal=cls._text(raw["goal"], "scene goal"),
                conflict=cls._text(raw["conflict"], "scene conflict"),
                action=cls._text(raw["action"], "scene action"),
                information_change=cls._text(raw["information_change"], "scene information_change"),
                state_change=cls._text(raw["state_change"], "scene state_change"),
                entry_reason=cls._text(raw["entry_reason"], "scene entry_reason"),
                exit_trigger=cls._text(raw["exit_trigger"], "scene exit_trigger"),
                inherited_from_previous=bool(raw["inherited_from_previous"]),
                narrative_purpose=cls._optional_text(raw.get("narrative_purpose")) or "",
                essential_information=cls._strings(
                    raw.get("essential_information", []), "scene essential_information", allow_empty=True,
                ),
                emotional_change=cls._optional_text(raw.get("emotional_change")) or "",
                closure=closure,
            ))
        return ScenePlan(
            scenes=tuple(scenes),
            chapter_spatial_intent=cls._optional_text(payload["chapter_spatial_intent"]) or "",
            required_world_slice=cls._optional_text(payload["required_world_slice"]) or "",
            allowed_same_place_run=cls._integer(payload["allowed_same_place_run"], "allowed_same_place_run"),
            exception_reason=cls._optional_text(payload["exception_reason"]) or "",
        )

    @classmethod
    def _decode_technology_plan(cls, value: object) -> TechnologyPlan:
        if value is None:
            return TechnologyPlan()
        payload = cls._object(value, "technology_plan")
        cls._require_fields(payload, {"technologies"}, "technology_plan")
        technologies = []
        for raw in cls._objects(payload["technologies"], "technology_plan.technologies"):
            cls._require_fields(
                raw,
                {"id", "name", "role", "birth_reason", "source", "prerequisites", "validation_stage", "first_application", "social_diffusion", "cost", "changed_domains"},
                "technology_contract",
            )
            technologies.append(TechnologyContract(
                id=cls._text(raw["id"], "technology id"),
                name=cls._text(raw["name"], "technology name"),
                role=cls._text(raw["role"], "technology role"),
                birth_reason=cls._text(raw["birth_reason"], "technology birth_reason"),
                source=cls._text(raw["source"], "technology source"),
                prerequisites=cls._strings(raw["prerequisites"], "technology prerequisites", allow_empty=True),
                validation_stage=cls._text(raw["validation_stage"], "technology validation_stage"),
                first_application=cls._text(raw["first_application"], "technology first_application"),
                social_diffusion=cls._strings(raw["social_diffusion"], "technology social_diffusion", allow_empty=True),
                cost=cls._text(raw["cost"], "technology cost"),
                changed_domains=cls._strings(raw["changed_domains"], "technology changed_domains", allow_empty=True),
            ))
        return TechnologyPlan(tuple(technologies))

    @classmethod
    def _decode_pov_plan(cls, value: object) -> PointOfViewPlan:
        if value is None:
            return PointOfViewPlan()
        payload = cls._object(value, "pov_plan")
        cls._require_fields(payload, {"primary_owner", "mode", "protagonist_present", "supporting_agency", "rationale"}, "pov_plan")
        agencies = []
        for raw in cls._objects(payload["supporting_agency"], "pov_plan.supporting_agency"):
            cls._require_fields(raw, {"actor", "independent_goal", "resistance", "choice", "cost", "result", "mainline_change"}, "supporting_agency")
            agencies.append(SupportingAgencyContract(
                actor=cls._text(raw["actor"], "agency actor"),
                independent_goal=cls._text(raw["independent_goal"], "agency independent_goal"),
                resistance=cls._text(raw["resistance"], "agency resistance"),
                choice=cls._text(raw["choice"], "agency choice"),
                cost=cls._text(raw["cost"], "agency cost"),
                result=cls._text(raw["result"], "agency result"),
                mainline_change=cls._text(raw["mainline_change"], "agency mainline_change"),
            ))
        return PointOfViewPlan(
            primary_owner=cls._optional_text(payload["primary_owner"]) or "",
            mode=cls._optional_text(payload["mode"]) or "",
            protagonist_present=bool(payload["protagonist_present"]),
            supporting_agency=tuple(agencies),
            rationale=cls._optional_text(payload["rationale"]) or "",
        )

    @classmethod
    def _decode_nullable(cls, value: object, name: str) -> NullablePlan:
        payload = cls._object(value, name)
        cls._require_fields(payload, {"values", "not_applicable_reason"}, name)
        reason = payload["not_applicable_reason"]
        if reason is not None and not isinstance(reason, str):
            raise NarrativeValidationError(f"{name}.not_applicable_reason must be text or null")
        plan = NullablePlan(values=cls._strings(payload["values"], f"{name}.values", allow_empty=True), not_applicable_reason=reason)
        plan.validate()
        return plan

    @classmethod
    def _decode_candidate(cls, payload: Mapping[str, Any]) -> OptionalCandidateResolution:
        cls._require_fields(
            payload,
            {
                "candidate_id",
                "kind",
                "value_state",
                "proposed_value",
                "dependency_inputs",
                "affects_current_chapter",
                "rationale",
                "decided_by",
                "decision_ref",
            },
            "optional_candidate",
        )
        proposed = payload["proposed_value"]
        if proposed is not None and not isinstance(proposed, str):
            raise NarrativeValidationError("candidate proposed_value must be text or null")
        candidate = OptionalCandidateResolution(
            candidate_id=cls._text(payload["candidate_id"], "candidate_id"),
            kind=cls._enum(CandidateKind, payload["kind"], "candidate kind"),
            value_state=cls._enum(CandidateValueState, payload["value_state"], "candidate value_state"),
            proposed_value=proposed,
            dependency_inputs=cls._strings(payload["dependency_inputs"], "dependency_inputs"),
            affects_current_chapter=cls._enum(
                CandidateImpact, payload["affects_current_chapter"], "candidate affects_current_chapter"
            ),
            rationale=cls._text(payload["rationale"], "candidate rationale"),
            decided_by=cls._enum(CandidateDecisionBy, payload["decided_by"], "candidate decided_by"),
            decision_ref=cls._text(payload["decision_ref"], "candidate decision_ref"),
        )
        candidate.validate()
        return candidate

    @classmethod
    def _decode_bindings(
        cls, value: object, contract_id: str, contract_version: int
    ) -> tuple[FieldEvidenceBinding, ...]:
        payload = cls._object(value, "intent_evidence_bindings")
        bindings: list[FieldEvidenceBinding] = []
        for field_path in sorted(payload):
            refs = tuple(
                cls._decode_evidence(item)
                for item in cls._objects(payload[field_path], f"intent_evidence_bindings.{field_path}")
            )
            binding = FieldEvidenceBinding(field_path=field_path, evidence=refs)
            binding.validate(contract_id, contract_version)
            bindings.append(binding)
        return tuple(bindings)

    @classmethod
    def _decode_evidence(cls, payload: Mapping[str, Any]) -> EvidenceRef:
        required_fields = {
            "evidence_id",
            "contract_id",
            "contract_version",
            "field_path",
            "role",
            "source_id",
            "source_version",
            "source_content_hash",
            "locator",
            "excerpt",
            "assertion",
        }
        actual_fields = set(payload)
        missing = required_fields - actual_fields
        unexpected = actual_fields - required_fields - {"asserted_value"}
        if missing:
            raise NarrativeValidationError(f"evidence missing field: {sorted(missing)[0]}")
        if unexpected:
            raise NarrativeValidationError(f"evidence unexpected field: {sorted(unexpected)[0]}")
        if "asserted_value" in payload and payload["asserted_value"] is None:
            raise NarrativeValidationError("evidence asserted_value must be a scalar when present")
        locator = cls._object(payload["locator"], "evidence.locator")
        cls._require_fields(locator, {"kind", "value"}, "evidence.locator")
        try:
            return EvidenceRef(
                evidence_id=cls._text(payload["evidence_id"], "evidence_id"),
                contract_id=cls._text(payload["contract_id"], "evidence contract_id"),
                contract_version=cls._integer(payload["contract_version"], "evidence contract_version"),
                field_path=cls._text(payload["field_path"], "evidence field_path"),
                role=cls._enum(EvidenceRole, payload["role"], "evidence role"),
                source_id=cls._text(payload["source_id"], "evidence source_id"),
                source_version=cls._text(payload["source_version"], "evidence source_version"),
                source_content_hash=cls._text(payload["source_content_hash"], "evidence source_content_hash"),
                locator=EvidenceLocator(
                    kind=cls._text(locator["kind"], "locator kind"),
                    value=cls._text(locator["value"], "locator value"),
                ),
                excerpt=cls._text(payload["excerpt"], "evidence excerpt"),
                assertion=cls._text(payload["assertion"], "evidence assertion"),
                asserted_value=payload.get("asserted_value"),
            )
        except ValueError as error:
            raise NarrativeValidationError(f"invalid evidence: {error}") from error

    @classmethod
    def _decode_legacy_evidence(cls, value: object) -> tuple[LegacyUnclassifiedEvidence, ...]:
        return tuple(
            LegacyUnclassifiedEvidence(
                source_type=cls._text(item.get("source_type"), "legacy evidence source_type"),
                source_ref=cls._text(item.get("source_ref"), "legacy evidence source_ref"),
                excerpt=cls._text(item.get("excerpt"), "legacy evidence excerpt"),
            )
            for item in cls._objects(value, "legacy evidence")
        )

    @classmethod
    def _decode_v2_legacy_evidence(cls, value: object) -> tuple[LegacyUnclassifiedEvidence, ...]:
        evidence: list[LegacyUnclassifiedEvidence] = []
        for payload in cls._objects(value, "legacy_unclassified_evidence"):
            cls._require_fields(
                payload, {"source_type", "source_ref", "excerpt", "classification"}, "legacy evidence"
            )
            item = LegacyUnclassifiedEvidence(
                source_type=cls._text(payload["source_type"], "legacy evidence source_type"),
                source_ref=cls._text(payload["source_ref"], "legacy evidence source_ref"),
                excerpt=cls._text(payload["excerpt"], "legacy evidence excerpt"),
                classification=cls._text(payload["classification"], "legacy evidence classification"),
            )
            item.validate()
            evidence.append(item)
        return tuple(evidence)

    @staticmethod
    def _choice_missing(
        actor: str | None,
        action: str | None,
        alternatives: tuple[str, ...],
        cost: str | None,
        consequence: str | None,
    ) -> tuple[str, ...]:
        return tuple(
            name
            for name, value in (
                ("actor", actor),
                ("action", action),
                ("alternatives", alternatives),
                ("cost", cost),
                ("consequence", consequence),
            )
            if not value
        )

    @staticmethod
    def _is_exact_v1_shape(payload: Mapping[str, Any]) -> bool:
        root_required = {
            "kind",
            "chapter",
            "profile_id",
            "volume_id",
            "arc_id",
            "arc_phase",
            "arc_goal",
            "inherited_pressure",
            "future_pressures",
            "chapter_contract",
        }
        root_allowed = root_required | {"schema_version", "evidence"}
        if not root_required <= set(payload) <= root_allowed:
            return False
        contract = payload.get("chapter_contract")
        if not isinstance(contract, dict):
            return False
        contract_required = {
            "functions",
            "dramatic_question",
            "protagonist_choice",
            "reader_change",
            "information",
            "pressure_curve",
            "foreshadow_actions",
            "ending_shift",
            "target_chinese_chars",
            "forbidden",
        }
        if not contract_required <= set(contract) <= contract_required | {"evidence"}:
            return False
        exact_nested_fields = {
            "protagonist_choice": {"actor", "action", "alternatives", "cost", "consequence"},
            "reader_change": {"before", "after"},
            "information": {"reveal", "withhold", "misdirect"},
            "pressure_curve": {"start", "turn", "end"},
        }
        for field_name, expected in exact_nested_fields.items():
            nested = contract.get(field_name)
            if not isinstance(nested, dict) or set(nested) != expected:
                return False
        evidence_values = [
            value
            for value in (payload.get("evidence"), contract.get("evidence"))
            if value is not None
        ]
        if len(evidence_values) > 1:
            return False
        legacy_evidence_fields = {"source_type", "source_ref", "excerpt"}
        if any(
            not isinstance(evidence, list)
            or any(not isinstance(item, dict) or set(item) != legacy_evidence_fields for item in evidence)
            for evidence in evidence_values
        ):
            return False
        return all(
            isinstance(contract.get(field_name), list)
            for field_name in ("foreshadow_actions", "forbidden")
        ) and isinstance(contract["information"].get("misdirect"), list)

    @staticmethod
    def _payload(content: str | bytes | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(content, Mapping):
            return dict(content)
        try:
            value = json.loads(content)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as error:
            raise NarrativeValidationError("narrative content must be valid JSON") from error
        if not isinstance(value, dict):
            raise NarrativeValidationError("narrative content root must be an object")
        return value

    @staticmethod
    def _object(value: object, name: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise NarrativeValidationError(f"{name} must be an object")
        return value

    @classmethod
    def _objects(cls, value: object, name: str) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise NarrativeValidationError(f"{name} must be a list")
        return [cls._object(item, name) for item in value]

    @staticmethod
    def _strings(value: object, name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise NarrativeValidationError(f"{name} must be a list")
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise NarrativeValidationError(f"{name} must contain non-empty strings")
        if not allow_empty and not value:
            raise NarrativeValidationError(f"{name} requires non-empty items")
        return tuple(value)

    @staticmethod
    def _text(value: object, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise NarrativeValidationError(f"{name} is required")
        return value

    @staticmethod
    def _optional_text(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise NarrativeValidationError("optional text must be text or null")
        return value

    @staticmethod
    def _integer(value: object, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise NarrativeValidationError(f"{name} must be an integer")
        return value

    @staticmethod
    def _enum(enum_type: type[Any], value: object, name: str) -> Any:
        try:
            return enum_type(value)
        except (TypeError, ValueError) as error:
            raise NarrativeValidationError(f"invalid {name}: {value}") from error

    @staticmethod
    def _enum_value(value: object) -> str:
        return value.value if hasattr(value, "value") else str(value)

    @staticmethod
    def _require_fields(payload: Mapping[str, Any], expected: set[str], name: str) -> None:
        actual = set(payload)
        missing = expected - actual
        unexpected = actual - expected
        if missing:
            raise NarrativeValidationError(f"{name} missing field: {sorted(missing)[0]}")
        if unexpected:
            raise NarrativeValidationError(f"{name} unexpected field: {sorted(unexpected)[0]}")

    @staticmethod
    def _require_fields_with_optional(
        payload: Mapping[str, Any], required: set[str], optional: set[str], name: str
    ) -> None:
        actual = set(payload)
        missing = required - actual
        unexpected = actual - required - optional
        if missing:
            raise NarrativeValidationError(f"{name} missing field: {sorted(missing)[0]}")
        if unexpected:
            raise NarrativeValidationError(f"{name} unexpected field: {sorted(unexpected)[0]}")
