from __future__ import annotations

import hashlib
from pathlib import Path

from creative_os.domains.narrative_memory import load_active_narrative_decision, load_active_narrative_profile
from creative_os.domains.novel_state_store import compact_active_snapshots
from creative_os.domains.pov_strategy_model import (
    ArcState, ChapterNeeds, CharacterPressure, ConsequenceRef, EvidenceRef,
    MainlineCapability, POVStrategyInput, ProtagonistLoad, RecentPOVEntry,
    StateRef, StorylineState,
)
from creative_os.domains.narrative_evidence import EvidenceLocator
from creative_os.domains.pov_strategy_policy import POVStrategyPolicy


class POVStrategyInputError(ValueError):
    def __init__(self, code: str, missing_fields: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.missing_fields = missing_fields


def assemble_pov_strategy_input(
    project_root: str | Path,
    target_chapter: int,
    chapter_needs: ChapterNeeds,
    policy: POVStrategyPolicy,
) -> POVStrategyInput:
    root = Path(project_root)
    policy.validate()
    if target_chapter < 1 or not chapter_needs.functions or not chapter_needs.dramatic_question.strip():
        raise POVStrategyInputError("missing_pov_strategy_input", ("chapter_needs",))
    start = max(1, target_chapter - policy.history_window)
    history = tuple(_history_entry(root, chapter, policy.protagonist_id) for chapter in range(start, target_chapter))
    history = tuple(item for item in history if item is not None)
    if history and [item.chapter for item in history] != list(range(history[0].chapter, target_chapter)):
        raise POVStrategyInputError("invalid_pov_history_window")
    profile = load_active_narrative_profile(root)
    if profile is None:
        raise POVStrategyInputError("missing_pov_strategy_input", ("profile",))
    last_decision = load_active_narrative_decision(root, target_chapter - 1)
    arc = next((item for item in profile.arcs if last_decision and item.id == last_decision.arc_id), profile.arcs[0])
    snapshots = compact_active_snapshots(root, max_chars=6000)
    consequences = _explicit_consequences(root, snapshots)
    pressures = _character_pressures(root, snapshots)
    evidence = _dedupe((*[ref for item in history for ref in item.evidence_refs], *arc_evidence(root, arc.id), *[ref for item in _storylines(root, snapshots) for ref in item.evidence_refs]))
    value = POVStrategyInput(
        project_id=root.name,
        target_chapter=target_chapter,
        assembled_at=_assembled_at(root, history),
        policy_version=policy.version,
        recent_pov_history=history,
        protagonist_load=_protagonist_load(history, consequences, policy.protagonist_id, policy.cold_start_minimum),
        character_pressures=pressures,
        arc_state=ArcState(arc.id, getattr(arc.phase, "value", str(arc.phase)), arc.goal, arc.goal, arc_evidence(root, arc.id)),
        storyline_states=_storylines(root, snapshots),
        unclaimed_consequences=consequences,
        chapter_needs=chapter_needs,
        evidence=evidence,
    )
    return value.with_fingerprint()


def _history_entry(root: Path, chapter: int, protagonist_id: str) -> RecentPOVEntry | None:
    final = root / "production" / "final_chapters" / f"chapter_{chapter:03d}.md"
    decision = load_active_narrative_decision(root, chapter)
    if not final.exists() or decision is None or not decision.chapter_contract.pov_plan.primary_owner:
        return None
    text = final.read_text(encoding="utf-8")
    ref = _evidence(final.relative_to(root).as_posix(), text, f"chapter:{chapter}", "正式章节与活动合同")
    plan = decision.chapter_contract.pov_plan
    # 正式正文决定实际出场；合同保留计划 POV，二者共同绑定同一历史条目。
    protagonist_present = protagonist_id in text
    owner = plan.primary_owner if plan.primary_owner in text else ""
    if not owner:
        return None
    outcomes = tuple(
        StateRef(f"chapter-{chapter}-agency-{index}", agency.mainline_change, (ref,))
        for index, agency in enumerate(plan.supporting_agency)
    )
    return RecentPOVEntry(chapter, owner, protagonist_present, decision.chapter_contract.functions, outcomes, (ref,))


def _explicit_consequences(root: Path, snapshots) -> tuple[ConsequenceRef, ...]:
    result = []
    for snapshot in snapshots:
        fields = snapshot.get("fields", {})
        consequence = fields.get("pov_consequence") if isinstance(fields, dict) else None
        if not isinstance(consequence, dict) or consequence.get("status") != "unclaimed":
            continue
        ref = _snapshot_evidence(root, snapshot)
        result.append(ConsequenceRef(
            str(consequence["id"]), str(consequence["value"]), bool(consequence.get("affects_protagonist", False)),
            tuple(str(value) for value in consequence.get("owner_ids", ())), "unclaimed",
            int(consequence["materialized_after_chapter"]), (ref,),
        ))
    return tuple(result)


def _character_pressures(root, snapshots):
    by_actor: dict[str, CharacterPressure] = {}
    for snapshot in snapshots:
        if snapshot.get("kind") != "character":
            continue
        fields = snapshot.get("fields", {})
        pressure = fields.get("pov_pressure") if isinstance(fields, dict) else None
        if not isinstance(pressure, dict):
            continue
        ref = _snapshot_evidence(root, snapshot)
        actor = str(snapshot["subject"])
        goals = tuple(StateRef(str(v["id"]), str(v["value"]), (ref,)) for v in pressure.get("unfinished_goals", ()))
        choices = tuple(StateRef(str(v["id"]), str(v["value"]), (ref,)) for v in pressure.get("pending_choices", ()))
        costs = tuple(StateRef(str(v["id"]), str(v["value"]), (ref,)) for v in pressure.get("unpaid_costs", ()))
        capabilities = tuple(MainlineCapability(str(v["id"]), tuple(v["serves_functions"]), str(v["target_state_ref"]), (ref,)) for v in pressure.get("agency_capabilities", ()))
        if goals or choices or costs or capabilities:
            by_actor[actor] = CharacterPressure(actor, goals, choices, costs, capabilities)
    return tuple(by_actor[key] for key in sorted(by_actor))


def _protagonist_load(history, consequences, protagonist_id, cold_start_minimum):
    absence = 0
    monopoly = 0
    for item in reversed(history):
        if item.protagonist_present:
            break
        absence += 1
    for item in reversed(history):
        if item.primary_owner != protagonist_id:
            break
        monopoly += 1
    return ProtagonistLoad(absence, monopoly, len(history) < max(6, cold_start_minimum), consequences)


def _storylines(root, snapshots):
    grouped: dict[str, list[StateRef]] = {}
    for snapshot in snapshots:
        kind = str(snapshot.get("kind", "event"))
        value = str(snapshot.get("subject", "state"))
        ref = _snapshot_evidence(root, snapshot)
        grouped.setdefault(kind, []).append(StateRef(value, str(snapshot.get("fields", {})), (ref,)))
    return tuple(StorylineState(key, "active", tuple(values), tuple(ref for value in values for ref in value.evidence_refs)) for key, values in sorted(grouped.items()))


def _snapshot_evidence(root: Path, snapshot) -> EvidenceRef:
    kind, subject = str(snapshot["kind"]), str(snapshot["subject"])
    safe = "".join(char if char.isalnum() or char in "_-" else "_" for char in subject)
    path = root / ".creative_os" / "state" / "snapshots" / kind / f"{safe}.json"
    text = path.read_text(encoding="utf-8")
    return _evidence(path.relative_to(root).as_posix(), text, f"snapshot:{kind}:{subject}", "活动状态快照")


def arc_evidence(root: Path, arc_id: str) -> tuple[EvidenceRef, ...]:
    source = root / ".creative_os" / "memory" / "items" / "narrative-project-profile.json"
    text = source.read_text(encoding="utf-8") if source.exists() else arc_id
    return (_evidence("narrative-project-profile", text, f"arc:{arc_id}", "活动Arc"),)


def _evidence(source_id: str, text: str, locator: str, assertion: str) -> EvidenceRef:
    return EvidenceRef(
        source_id=source_id,
        source_version="1",
        source_content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        locator=EvidenceLocator("text_anchor", locator),
        assertion=assertion,
    )


def _dedupe(values):
    result = {}
    for value in values:
        result[(value.source_id, value.locator, value.assertion)] = value
    return tuple(result.values())


def _assembled_at(root: Path, history: tuple[RecentPOVEntry, ...]) -> str:
    latest = max((item.chapter for item in history), default=0)
    return f"chapter-{latest:03d}-materialized"
