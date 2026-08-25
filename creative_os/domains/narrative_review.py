from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from creative_os.domains.narrative_decision import NarrativeDecision, NarrativeValidationError
from creative_os.domains.narrative_progression import evaluate_progression
from creative_os.domains.narrative_replay_model import (
    EvidenceRef,
    ReplayNarrativeIssue,
    ReplayedChapterContract,
    UNKNOWN,
)


TIME_OPENERS = ("凌晨", "清晨", "早晨", "上午", "中午", "午后", "傍晚", "夜晚", "深夜")


@dataclass(frozen=True, slots=True)
class NarrativeIssue:
    code: str
    severity: str
    evidence: str


def review_replayed_contract(
    contract: ReplayedChapterContract,
    recent: tuple[ReplayedChapterContract, ...] = (),
) -> tuple[ReplayNarrativeIssue, ...]:
    contract.validate()
    issues: list[ReplayNarrativeIssue] = []

    if contract.protagonist_choice is None:
        issues.append(_replay_issue(
            "missing_protagonist_choice",
            "没有结构化证据证明主角在本章作出主动选择。",
            contract,
            "人工核对任务与正文；确认后补录人物选择证据。",
        ))
    elif not contract.protagonist_choice.cost.strip() or contract.protagonist_choice.cost == UNKNOWN:
        issues.append(_replay_issue(
            "missing_choice_cost",
            "人物选择缺少可确认的代价。",
            contract,
            "人工确认选择造成的即时或延迟代价并补录证据。",
        ))

    if contract.reader_before == UNKNOWN or contract.reader_after == UNKNOWN:
        issues.append(_replay_issue(
            "unknown_reader_change",
            "读者认知前后变化缺少明确证据。",
            contract,
            "人工标注本章揭示、隐藏或误导的信息变化。",
        ))

    current_functions = {item for item in contract.functions if item != UNKNOWN}
    for previous in reversed(recent):
        overlap = current_functions & {item for item in previous.functions if item != UNKNOWN}
        if overlap:
            issues.append(ReplayNarrativeIssue(
                code="repeated_chapter_function",
                severity="warning",
                message=f"与近期章节重复功能：{'、'.join(sorted(overlap))}",
                evidence=_unique_replay_evidence((*contract.evidence, *previous.evidence)),
                repair_hint="人工判断该重复是否承担升级、转折或兑现功能；否则调整章节职责。",
            ))
            break

    if contract.ending_shift == UNKNOWN:
        issues.append(_replay_issue(
            "unknown_ending_shift",
            "章节结尾的新失衡缺少明确证据。",
            contract,
            "人工确认结尾改变了哪项风险、关系、信息或行动条件。",
        ))
    return tuple(issues)


def review_narrative(
    contract: NarrativeDecision,
    recent_contracts: list[NarrativeDecision],
    text: str,
) -> list[NarrativeIssue]:
    issues: list[NarrativeIssue] = []
    try:
        contract.validate()
    except NarrativeValidationError as error:
        issues.append(NarrativeIssue("incomplete_chapter_contract", "high", str(error)))

    chapter = contract.chapter_contract
    if not chapter.protagonist_choice.actor or not chapter.protagonist_choice.action:
        issues.append(NarrativeIssue("missing_protagonist_agency", "high", "chapter_contract.protagonist_choice"))
    if not chapter.protagonist_choice.cost or not chapter.protagonist_choice.consequence:
        issues.append(NarrativeIssue("missing_agency_cost_or_consequence", "high", "chapter_contract.protagonist_choice"))
    if not chapter.reader_change.before or not chapter.reader_change.after:
        issues.append(NarrativeIssue("missing_reader_change", "high", "chapter_contract.reader_change"))
    if not chapter.foreshadow_actions:
        issues.append(NarrativeIssue("missing_foreshadow_action", "medium", "chapter_contract.foreshadow_actions"))
    if not chapter.ending_shift:
        issues.append(NarrativeIssue("missing_ending_shift", "medium", "chapter_contract.ending_shift"))

    current_functions = set(chapter.functions)
    for recent in recent_contracts[-2:]:
        overlap = current_functions & set(recent.chapter_contract.functions)
        if overlap:
            issues.append(
                NarrativeIssue("duplicate_recent_function", "medium", f"functions: {', '.join(sorted(overlap))}")
            )
            break

    opener = _opening(text)
    if recent_contracts and opener and any(opener.startswith(word) for word in TIME_OPENERS):
        issues.append(NarrativeIssue("repeated_time_opening", "low", opener))

    for forbidden in chapter.forbidden:
        if forbidden and forbidden in text:
            issues.append(NarrativeIssue("forbidden_information_revealed", "high", forbidden))

    scene_plan = chapter.scene_plan
    dramatized_scene_ids: set[str] = set()
    for scene in scene_plan.scenes:
        place_present = _evidence_match(scene.place_label, text) or scene.place_id in text
        dramatic_markers = (
            scene.goal, scene.conflict, scene.action, scene.information_change,
            scene.state_change, scene.entry_reason, scene.exit_trigger,
        )
        marker_hits = sum(bool(marker and _evidence_match(marker, text)) for marker in dramatic_markers)
        if place_present and marker_hits >= 2:
            dramatized_scene_ids.add(scene.id)
        else:
            issues.append(NarrativeIssue(
                "declared_location_not_dramatized", "high", f"{scene.id}: {scene.place_label}",
            ))
    ordinary_slice_dramatized = any(
        scene.id in dramatized_scene_ids
        and scene.ordinary_people_present
        and any(participant != scene.viewpoint and _evidence_match(participant, text) for participant in scene.participants)
        for scene in scene_plan.scenes
    )
    if scene_plan.required_world_slice and not ordinary_slice_dramatized:
        issues.append(NarrativeIssue(
            "external_world_slice_missing", "high", scene_plan.required_world_slice,
        ))

    for technology in chapter.technology_plan.technologies:
        engineering_markers = (
            technology.validation_stage,
            technology.first_application,
            *technology.social_diffusion,
        )
        engineering_hits = sum(bool(marker and _evidence_match(marker, text)) for marker in engineering_markers)
        if not _evidence_match(technology.name, text) or engineering_hits < 2:
            issues.append(NarrativeIssue(
                "technology_application_missing", "high", f"{technology.id}: {technology.first_application}",
            ))
    for agency in chapter.pov_plan.supporting_agency:
        agency_markers = (
            agency.independent_goal, agency.resistance, agency.choice,
            agency.cost, agency.result, agency.mainline_change,
        )
        if agency.actor not in text or sum(_evidence_match(marker, text) for marker in agency_markers) < 3:
            issues.append(NarrativeIssue(
                "supporting_agency_not_dramatized", "high", f"{agency.actor}: {agency.mainline_change}",
            ))
    for progression_issue in evaluate_progression(contract, recent_contracts).issues:
        issues.append(NarrativeIssue(
            progression_issue.code, progression_issue.severity, progression_issue.evidence,
        ))
    return issues


def _opening(text: str) -> str:
    for line in text.splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            return value[:120]
    return ""


def _evidence_match(marker: str, text: str) -> bool:
    """Match concise contract evidence without requiring prose to copy whole clauses verbatim."""
    value = marker.strip()
    if not value:
        return False
    if value in text:
        return True
    compact = "".join(character for character in value if character.isalnum())
    chunks = {compact[index:index + 2] for index in range(max(0, len(compact) - 1))}
    return len(chunks) >= 2 and sum(chunk in text for chunk in chunks) >= min(3, len(chunks))


def _replay_issue(
    code: str,
    message: str,
    contract: ReplayedChapterContract,
    repair_hint: str,
) -> ReplayNarrativeIssue:
    return ReplayNarrativeIssue(
        code=code,
        severity="warning",
        message=message,
        evidence=contract.evidence,
        repair_hint=repair_hint,
    )


def _unique_replay_evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    result: list[EvidenceRef] = []
    seen: set[tuple[str, str, str]] = set()
    for value in values:
        marker = (value.source_type, value.source_ref, value.excerpt)
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return tuple(result)
