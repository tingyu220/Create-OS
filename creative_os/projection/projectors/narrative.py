from __future__ import annotations

import json
from collections import defaultdict

from creative_os.projection.narrative import CharacterSnapshot, StoryThreadSnapshot, TimelineEntrySnapshot
from creative_os.projection.provenance import Derivation
from creative_os.projection.source import ProjectFacts


def project_characters(facts: ProjectFacts) -> tuple[CharacterSnapshot, ...]:
    return tuple(CharacterSnapshot(x.subject, x.fields_json, (x.source_ref,), Derivation("active-character-state", (x.source_ref,))) for x in facts.active_states if x.kind == "character")


def project_story_threads(facts: ProjectFacts) -> tuple[StoryThreadSnapshot, ...]:
    result: list[StoryThreadSnapshot] = []
    for x in facts.active_states:
        if x.kind not in {"hook", "foreshadow"}:
            continue
        try:
            payload = json.loads(x.fields_json)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        open_loop = payload.get("open_loop")
        result.append(StoryThreadSnapshot(
            subject=x.subject,
            thread_type="foreshadow",
            status=payload.get("status", "unknown") if isinstance(payload.get("status", "unknown"), str) else "unknown",
            fields_json=x.fields_json,
            source_refs=(x.source_ref,),
            derivation=Derivation("active-hook-state", (x.source_ref,)),
            open_loop=open_loop.strip() if isinstance(open_loop, str) and open_loop.strip() else None,
        ))
    for expectation in facts.engagement_expectations:
        fields_json = json.dumps({
            "expectation_id": expectation.expectation_id,
            "from_state": expectation.from_state,
            "to_state": expectation.to_state,
            "content_hash": expectation.content_hash,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        refs = (expectation.source_ref, expectation.decision_source_ref)
        result.append(StoryThreadSnapshot(
            subject=expectation.expectation_id,
            thread_type="expectation",
            status=expectation.to_state,
            fields_json=fields_json,
            source_refs=refs,
            derivation=Derivation("approved-engagement-expectation", refs),
        ))
    result.sort(key=lambda item: (item.thread_type, item.subject))
    return tuple(result)


def project_timeline(facts: ProjectFacts) -> tuple[TimelineEntrySnapshot, ...]:
    grouped: dict[str, list[tuple[object, dict[str, object]]]] = defaultdict(list)
    for state in facts.active_states:
        if state.kind != "timeline":
            continue
        try:
            payload = json.loads(state.fields_json)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        grouped[state.subject].append((state, payload if isinstance(payload, dict) else {}))

    result: list[TimelineEntrySnapshot] = []
    for subject in sorted(grouped):
        states = grouped[subject]
        refs = tuple(dict.fromkeys(state.source_ref for state, _ in states))
        derivation = Derivation("active-timeline-state", refs)
        values = {
            field: {value for _, payload in states if isinstance((value := payload.get(field)), str) and value.strip()}
            for field in ("precision", "relative_order")
        }
        declared_statuses = {
            value.strip()
            for _, payload in states
            if isinstance((value := payload.get("conflict_status")), str) and value.strip()
        }
        conflicted = len(values["precision"]) > 1 or len(values["relative_order"]) > 1 or "conflicted" in declared_statuses
        conflict_status = "conflicted" if conflicted else (next(iter(declared_statuses)) if len(declared_statuses) == 1 else "unknown")
        precision = "unknown" if conflicted or len(values["precision"]) != 1 else next(iter(values["precision"]))
        relative_order = "unknown" if conflicted or len(values["relative_order"]) != 1 else next(iter(values["relative_order"]))
        fields_json = states[0][0].fields_json
        if conflicted:
            fields_json = json.dumps({
                "conflict_status": conflict_status,
                "precision": precision,
                "relative_order": relative_order,
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        result.append(TimelineEntrySnapshot(
            subject=subject,
            precision=precision,
            relative_order=relative_order,
            conflict_status=conflict_status,
            fields_json=fields_json,
            source_refs=refs,
            derivation=derivation,
        ))
    return tuple(result)
