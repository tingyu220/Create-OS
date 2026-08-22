from __future__ import annotations

from typing import Any

from creative_os.domains.narrative_decision import ChoiceStatus
from creative_os.domains.narrative_evidence import EvidenceRef
from creative_os.domains.narrative_replay_model import (
    UNKNOWN, ReplayedChapterContract, ReplayedProtagonistChoice,
)


class ReplayContractCodec:
    """Strict, audit-only version dispatcher for replay projections."""

    @classmethod
    def decode(cls, payload: object) -> ReplayedChapterContract:
        data = cls._object(payload, "replay contract")
        version = data.get("schema_version")
        if type(version) is not int:
            raise ValueError("replay schema_version must be an integer")
        if version == 1:
            return cls.decode_v1(data)
        if version == 2:
            return cls.decode_v2(data)
        raise ValueError("unsupported replay schema_version")

    @classmethod
    def decode_v1(cls, payload: object) -> ReplayedChapterContract:
        data = cls._object(payload, "v1 replay contract")
        allowed = {
            "schema_version", "chapter_id", "functions", "dramatic_question",
            "protagonist_choice", "evidence", "reader_before", "reader_after",
            "pressure_start", "pressure_end", "ending_shift",
        }
        cls._fields(data, allowed, allowed, "v1 replay contract")
        if data["schema_version"] != 1 or type(data["schema_version"]) is not int:
            raise ValueError("invalid v1 replay schema")
        return cls._build(
            data, data["reader_before"], data["reader_after"],
            data["pressure_start"], data["pressure_end"],
        )

    @classmethod
    def decode_v2(cls, payload: object) -> ReplayedChapterContract:
        data = cls._object(payload, "v2 replay contract")
        fields = {
            "schema_version", "chapter_id", "functions", "dramatic_question",
            "protagonist_choice", "evidence", "reader_change", "pressure_curve",
            "ending_shift",
        }
        cls._fields(data, fields, fields, "v2 replay contract")
        if data["schema_version"] != 2 or type(data["schema_version"]) is not int:
            raise ValueError("invalid v2 replay schema")
        reader = cls._object(data["reader_change"], "reader_change")
        pressure = cls._object(data["pressure_curve"], "pressure_curve")
        cls._fields(reader, {"before", "after"}, {"before", "after"}, "reader_change")
        cls._fields(pressure, {"start", "end"}, {"start", "end"}, "pressure_curve")
        return cls._build(data, reader["before"], reader["after"], pressure["start"], pressure["end"])

    @classmethod
    def encode_v2(cls, contract: ReplayedChapterContract) -> dict[str, object]:
        if type(contract) is not ReplayedChapterContract:
            raise TypeError("ReplayContractCodec only encodes replay contracts")
        contract.validate()
        choice = contract.protagonist_choice
        encoded_choice = {
            "status": choice.status.value, "actor": choice.actor, "action": choice.action,
            "alternatives": list(choice.alternatives), "cost": choice.cost,
            "consequence": choice.consequence,
            "missing_fields": list(choice.missing_fields),
        }
        return {
            "schema_version": 2, "chapter_id": contract.chapter_id,
            "functions": list(contract.functions), "dramatic_question": contract.dramatic_question,
            "protagonist_choice": encoded_choice,
            "reader_change": {"before": contract.reader_before, "after": contract.reader_after},
            "pressure_curve": {"start": contract.pressure_start, "end": contract.pressure_end},
            "ending_shift": contract.ending_shift,
            "evidence": [cls._encode_evidence(item) for item in contract.evidence],
        }

    @classmethod
    def _build(cls, data: dict[str, Any], before: object, after: object,
               start: object, end: object) -> ReplayedChapterContract:
        functions = cls._strings(data["functions"], "functions", allow_empty=False)
        evidence_raw = data["evidence"]
        if not isinstance(evidence_raw, list) or not evidence_raw:
            raise ValueError("replay contract requires evidence")
        contract = ReplayedChapterContract(
            chapter_id=cls._text(data["chapter_id"], "chapter_id"),
            functions=functions,
            dramatic_question=cls._text(data["dramatic_question"], "dramatic_question"),
            protagonist_choice=cls._choice(data["protagonist_choice"]),
            evidence=tuple(cls._evidence(item) for item in evidence_raw),
            reader_before=cls._text(before, "reader before"),
            reader_after=cls._text(after, "reader after"),
            pressure_start=cls._text(start, "pressure start"),
            pressure_end=cls._text(end, "pressure end"),
            ending_shift=cls._text(data["ending_shift"], "ending_shift"),
        )
        contract.validate()
        return contract

    @classmethod
    def _choice(cls, raw: object) -> ReplayedProtagonistChoice:
        if raw is None:
            return ReplayedProtagonistChoice(ChoiceStatus.UNKNOWN)
        data = cls._object(raw, "protagonist_choice")
        allowed = {"status", "actor", "action", "alternatives", "cost", "consequence", "missing_fields"}
        required = {"actor", "action"}
        cls._fields(data, allowed, required, "protagonist_choice")
        actor = cls._optional_text(data.get("actor")); action = cls._optional_text(data.get("action"))
        alternatives = cls._strings(data.get("alternatives", []), "alternatives", allow_empty=True)
        cost = cls._optional_text(data.get("cost")); consequence = cls._optional_text(data.get("consequence"))
        missing = tuple(name for name, value in (
            ("actor", actor), ("action", action), ("alternatives", alternatives),
            ("cost", cost), ("consequence", consequence),
        ) if not value or value == UNKNOWN)
        status = ChoiceStatus.UNKNOWN if len(missing) == 5 else ChoiceStatus.PARTIAL if missing else ChoiceStatus.COMPLETE
        if "status" in data and data["status"] != status.value:
            raise ValueError("replay choice status is not exact")
        if "missing_fields" in data:
            raw_missing = data["missing_fields"]
            if (not isinstance(raw_missing, list)
                    or any(not isinstance(item, str) for item in raw_missing)
                    or tuple(raw_missing) != missing):
                raise ValueError("replay choice missing_fields are not exact")
        return ReplayedProtagonistChoice(status, actor, action, alternatives, cost, consequence, missing)

    @classmethod
    def _evidence(cls, raw: object) -> EvidenceRef:
        data = cls._object(raw, "replay evidence")
        fields = {"source_type", "source_ref", "excerpt"}
        cls._fields(data, fields, fields, "replay evidence")
        return EvidenceRef(cls._text(data["source_type"], "source_type"),
                           cls._text(data["source_ref"], "source_ref"),
                           cls._text(data["excerpt"], "excerpt"))

    @staticmethod
    def _encode_evidence(value: EvidenceRef) -> dict[str, object]:
        if not value.is_legacy_replay_ref:
            raise ValueError("contract evidence cannot be downgraded into replay evidence")
        return {"source_type": value.source_type, "source_ref": value.source_ref, "excerpt": value.excerpt}

    @staticmethod
    def _object(value: object, name: str) -> dict[str, Any]:
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise ValueError(f"{name} must be an object")
        return value

    @staticmethod
    def _fields(value: dict[str, Any], allowed: set[str], required: set[str], name: str) -> None:
        if set(value) - allowed or required - set(value):
            raise ValueError(f"invalid {name} fields")

    @staticmethod
    def _text(value: object, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")
        return value.strip()

    @staticmethod
    def _optional_text(value: object) -> str:
        return value.strip() if isinstance(value, str) and value.strip() else UNKNOWN

    @classmethod
    def _strings(cls, value: object, name: str, *, allow_empty: bool) -> tuple[str, ...]:
        if not isinstance(value, list) or (not allow_empty and not value):
            raise ValueError(f"{name} must be a list")
        result = tuple(cls._text(item, name) for item in value)
        if len(set(result)) != len(result):
            raise ValueError(f"{name} must be unique")
        return result
