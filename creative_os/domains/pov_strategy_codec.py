from __future__ import annotations

import json
import hashlib
from dataclasses import asdict

from creative_os.domains.pov_strategy_model import (
    EvidenceRef, MainlineChangeProposal, POVOption, POVRisk,
    POVStrategyCandidateSet, RhythmOutlook, StateRef,
    SupportingAgencyBoundary, TransitionReason,
)
from creative_os.domains.narrative_evidence import EvidenceLocator


class POVStrategyCodecError(ValueError):
    pass


def encode_candidate_set(value: POVStrategyCandidateSet) -> str:
    value.validate()
    payload = {"schema_version": 1, **asdict(value)}
    payload["content_hash"] = _content_hash(payload)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def decode_candidate_set(content: str) -> POVStrategyCandidateSet:
    try:
        data = json.loads(content)
        content_hash = data.pop("content_hash")
        if content_hash != _content_hash(data):
            raise POVStrategyCodecError("candidate fingerprint or content was modified")
        if data.pop("schema_version") != 1:
            raise POVStrategyCodecError("unsupported schema")
        value = _candidate(data)
        value.validate()
        return value
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, POVStrategyCodecError):
            raise
        raise POVStrategyCodecError(str(exc)) from exc


def _content_hash(data: dict) -> str:
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _evidence(data: dict) -> EvidenceRef:
    locator = data["locator"]
    value = EvidenceRef(
        source_id=data["source_id"],
        source_version=data["source_version"],
        source_content_hash=data["source_content_hash"],
        locator=EvidenceLocator(locator["kind"], locator["value"]),
        assertion=data["assertion"],
        excerpt=data.get("excerpt"),
    )
    value.validate()
    return value


def _state(data: dict) -> StateRef:
    return StateRef(data["id"], data["value"], tuple(_evidence(x) for x in data["evidence_refs"]))


def _option(data: dict) -> POVOption:
    change = data["mainline_change"]
    agency = data["agency"]
    transition = data["transition"]
    return POVOption(
        data["id"], data["primary_owner"], data["protagonist_present"], data["rationale"],
        tuple(data["function_fits"]), tuple(data["benefits"]), tuple(data["tradeoffs"]), tuple(data["cannot_serve"]),
        MainlineChangeProposal(change["target_state_ref"], change["change_type"], change["capability"], tuple(_evidence(x) for x in change["evidence_refs"])),
        SupportingAgencyBoundary(agency["actor"], _state(agency["goal_ref"]), _state(agency["resistance_ref"]), agency["choice_boundary"], _state(agency["plausible_cost_ref"]) if agency["plausible_cost_ref"] else None),
        TransitionReason(transition["from_recent_pov"], transition["arc_reason"], tuple(_evidence(x) for x in transition["evidence_refs"])),
        tuple(_evidence(x) for x in data["evidence_refs"]),
    )


def _candidate(data: dict) -> POVStrategyCandidateSet:
    outlook = data["rhythm_outlook"]
    return POVStrategyCandidateSet(
        data["id"], data["target_chapter"], data["input_fingerprint"], data["policy_version"], data["generated_at"],
        tuple(data["expires_when"]), _option(data["recommended"]), tuple(_option(x) for x in data["alternatives"]),
        RhythmOutlook(outlook["horizon_chapters"], tuple(outlook["pressures_to_revisit"]), tuple(outlook["suggested_pov_functions"]), tuple(outlook["flexibility_notes"])),
        tuple(POVRisk(x["code"], x["severity"], tuple(_evidence(e) for e in x["evidence_refs"]), x["explanation"]) for x in data["risks"]),
    )
