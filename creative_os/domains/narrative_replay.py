from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from creative_os.domains.narrative_decision import NarrativeDecision
from creative_os.domains.narrative_decision import ChoiceStatus
from creative_os.domains.narrative_evidence import ChapterEvidence, EvidenceRef, JsonArtifact, load_chapter_evidence
from creative_os.domains.narrative_replay_model import (
    ReplayedChapterContract, ReplayedProtagonistChoice, UNKNOWN,
)
from creative_os.domains.narrative_replay_store import NarrativeReplayEvent, NarrativeReplayStore
from creative_os.domains.narrative_review import TIME_OPENERS, review_narrative


@dataclass(frozen=True, slots=True)
class ReplayFinding:
    chapter_number: int
    source: str
    opening: str
    automatic_codes: tuple[str, ...]
    evidence: tuple[str, ...]
    manual_pending: tuple[str, ...]


def replay_chapter(evidence: ChapterEvidence) -> ReplayedChapterContract:
    """Build a deterministic audit projection without inferring from prose."""
    if not evidence.source_refs:
        raise ValueError("chapter evidence requires source_refs")

    references = [_prose_reference(evidence)]
    contract_data, contract_artifact = _find_structured_contract(evidence)

    functions: tuple[str, ...] = ()
    dramatic_question = UNKNOWN
    protagonist_choice = ReplayedProtagonistChoice(ChoiceStatus.UNKNOWN)
    reader_before = UNKNOWN
    reader_after = UNKNOWN
    pressure_start = UNKNOWN
    pressure_end = UNKNOWN
    ending_shift = UNKNOWN

    if contract_data is not None and contract_artifact is not None:
        functions = _strings(contract_data.get("functions"))
        dramatic_question = _text(contract_data.get("dramatic_question"))
        protagonist_choice = _choice(contract_data.get("protagonist_choice"))
        reader_change = _object(contract_data.get("reader_change"))
        pressure_curve = _object(contract_data.get("pressure_curve"))
        if reader_change is not None:
            reader_before = _text(reader_change.get("before"))
            reader_after = _text(reader_change.get("after"))
        if pressure_curve is not None:
            pressure_start = _text(pressure_curve.get("start"))
            pressure_end = _text(pressure_curve.get("end"))
        ending_shift = _text(contract_data.get("ending_shift"))
        references.append(_json_reference("context", contract_artifact, contract_data))

    task_functions, task_references = _task_functions(evidence.tasks)
    if not functions:
        functions = task_functions
        references.extend(task_references)
    if ending_shift == UNKNOWN:
        task_ending, ending_reference = _task_ending(evidence.tasks)
        ending_shift = task_ending
        if ending_reference is not None:
            references.append(ending_reference)

    contract = ReplayedChapterContract(
        chapter_id=evidence.chapter_id,
        functions=functions or (UNKNOWN,),
        dramatic_question=dramatic_question,
        protagonist_choice=protagonist_choice,
        evidence=tuple(_unique_references(references)),
        reader_before=reader_before,
        reader_after=reader_after,
        pressure_start=pressure_start,
        pressure_end=pressure_end,
        ending_shift=ending_shift,
    )
    contract.validate()
    return contract


def replay_range(
    project_root: str | Path,
    start: int = 1,
    end: int = 6,
) -> tuple[ReplayedChapterContract, ...]:
    if start < 1 or end < start:
        raise ValueError("invalid replay range")
    root = Path(project_root)
    store = NarrativeReplayStore(project_id=root.name)
    for version, chapter_number in enumerate(range(start, end + 1), start=1):
        contract = replay_chapter(load_chapter_evidence(root, chapter_number))
        store.append(NarrativeReplayEvent(version, "chapter_replayed", contract.chapter_id, contract))
    return store.snapshot().chapter_contracts


def analyze_chapter(
    project_root: str | Path,
    chapter_number: int,
    decision: NarrativeDecision | None,
) -> ReplayFinding:
    if chapter_number < 1:
        raise ValueError("chapter_number must be positive")
    root = Path(project_root)
    path = root / "production" / "final_chapters" / f"chapter_{chapter_number:03d}.md"
    text = path.read_text(encoding="utf-8")
    opening = _opening(text)
    codes: list[str] = []
    evidence: list[str] = []
    pending: list[str] = []
    if any(opening.startswith(word) for word in TIME_OPENERS):
        codes.append("time_word_opening")
        evidence.append(f"opening: {opening}")
    scene_headings = [line.strip() for line in text.splitlines() if line.strip().startswith("##")]
    if scene_headings:
        codes.append("markdown_scene_headings_present")
        evidence.append("scene_headings: " + " | ".join(scene_headings[:3]))
    if decision is None:
        pending.append("missing_narrative_contract")
    else:
        issues = review_narrative(decision, recent_contracts=[], text=text)
        codes.extend(issue.code for issue in issues)
        evidence.extend(f"{issue.code}: {issue.evidence}" for issue in issues)
    return ReplayFinding(
        chapter_number=chapter_number,
        source=path.relative_to(root).as_posix(),
        opening=opening,
        automatic_codes=tuple(dict.fromkeys(codes)),
        evidence=tuple(evidence),
        manual_pending=tuple(pending),
    )


def render_replay_report(findings: list[ReplayFinding]) -> str:
    lines = ["# 《文明升阶》叙事回放报告", "", "本报告只读取正式正文；没有合同的章节不会被系统臆测。", ""]
    for finding in sorted(findings, key=lambda item: item.chapter_number):
        lines.extend([f"## 第 {finding.chapter_number} 章", "", f"- 来源：`{finding.source}`", f"- 开头：{finding.opening}"])
        lines.append(f"- 自动检测：{'、'.join(finding.automatic_codes) if finding.automatic_codes else '未发现'}")
        lines.append(f"- 人工待定：{'、'.join(finding.manual_pending) if finding.manual_pending else '无'}")
        if finding.evidence:
            lines.append("- 证据：")
            lines.extend(f"  - {evidence}" for evidence in finding.evidence)
        lines.append("")
    return "\n".join(lines)


def _opening(text: str) -> str:
    for line in text.splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            return value[:160]
    return ""


def _find_structured_contract(
    evidence: ChapterEvidence,
) -> tuple[dict[str, object] | None, JsonArtifact | None]:
    for artifact in (*evidence.contexts, *evidence.knowledge, *evidence.tasks):
        direct = _object(artifact.data.get("chapter_contract"))
        if direct is not None:
            return direct, artifact
        decision = _object(artifact.data.get("narrative_decision"))
        nested = _object(decision.get("chapter_contract")) if decision is not None else None
        if nested is not None:
            return nested, artifact
        narrative = _object(artifact.data.get("narrative_contract"))
        if narrative is not None:
            nested = _object(narrative.get("chapter_contract")) or narrative
            return nested, artifact
    return None, None


def _task_functions(tasks: tuple[JsonArtifact, ...]) -> tuple[tuple[str, ...], tuple[EvidenceRef, ...]]:
    values: list[str] = []
    references: list[EvidenceRef] = []
    for task in tasks:
        scene_spec = _object(task.data.get("scene_spec"))
        goal = _text(scene_spec.get("goal")) if scene_spec is not None else _text(task.data.get("goal"))
        if goal != UNKNOWN and goal not in values:
            values.append(goal)
            references.append(EvidenceRef("task", task.source_ref, f"goal: {goal}"))
    return tuple(values), tuple(references)


def _task_ending(tasks: tuple[JsonArtifact, ...]) -> tuple[str, EvidenceRef | None]:
    for task in reversed(tasks):
        scene_spec = _object(task.data.get("scene_spec"))
        outcome = _text(scene_spec.get("outcome")) if scene_spec is not None else UNKNOWN
        if outcome != UNKNOWN:
            return outcome, EvidenceRef("task", task.source_ref, f"outcome: {outcome}")
    return UNKNOWN, None


def _choice(value: object) -> ReplayedProtagonistChoice:
    payload = _object(value)
    if payload is None:
        return ReplayedProtagonistChoice(ChoiceStatus.UNKNOWN)
    actor = _text(payload.get("actor"))
    action = _text(payload.get("action"))
    alternatives = _strings(payload.get("alternatives"))
    cost = _text(payload.get("cost"))
    consequence = _text(payload.get("consequence"))
    missing = tuple(name for name, item in (
        ("actor", actor), ("action", action), ("alternatives", alternatives),
        ("cost", cost), ("consequence", consequence),
    ) if item == UNKNOWN or not item)
    status = ChoiceStatus.UNKNOWN if len(missing) == 5 else ChoiceStatus.PARTIAL if missing else ChoiceStatus.COMPLETE
    return ReplayedProtagonistChoice(
        status=status,
        actor=actor,
        action=action,
        alternatives=alternatives,
        cost=cost,
        consequence=consequence,
        missing_fields=missing,
    )


def _object(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else UNKNOWN


def _prose_reference(evidence: ChapterEvidence) -> EvidenceRef:
    return EvidenceRef(
        source_type="chapter",
        source_ref=evidence.source_refs[0],
        excerpt=_opening(evidence.prose) or "canonical chapter exists",
    )


def _json_reference(source_type: str, artifact: JsonArtifact, payload: dict[str, object]) -> EvidenceRef:
    excerpt = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return EvidenceRef(source_type=source_type, source_ref=artifact.source_ref, excerpt=excerpt[:500])


def _unique_references(references: list[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    result: list[EvidenceRef] = []
    seen: set[tuple[str, str, str]] = set()
    for reference in references:
        marker = (reference.source_type, reference.source_ref, reference.excerpt)
        if marker not in seen:
            seen.add(marker)
            result.append(reference)
    return tuple(result)
