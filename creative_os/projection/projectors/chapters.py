from __future__ import annotations

from collections import defaultdict

from creative_os.projection.chapters import (
    ChapterSnapshot,
    ChapterStage,
    ChapterStageSnapshot,
    ChapterStatus,
    StageStatus,
)
from creative_os.projection.provenance import Derivation, SourceRef
from creative_os.projection.source import ProjectFacts, ProjectionChangeSet


_STATUS_MAP = {
    "pass": ChapterStatus.PASSED,
    "passed": ChapterStatus.PASSED,
    "running": ChapterStatus.RUNNING,
    "failed": ChapterStatus.FAILED,
    "fail": ChapterStatus.FAILED,
    "blocked": ChapterStatus.BLOCKED,
    "not_started": ChapterStatus.NOT_STARTED,
}


def project_chapters(
    facts: ProjectFacts,
    previous: tuple[ChapterSnapshot, ...] | None = None,
    changes: ProjectionChangeSet | None = None,
) -> tuple[ChapterSnapshot, ...]:
    del previous, changes
    numbers = {item.chapter_number for item in facts.chapter_statuses}
    numbers.update(item.chapter_number for item in facts.gate_results if item.chapter_number is not None)
    numbers.update(number for item in facts.runtime_reports if (number := _chapter_number(item.chapter_id)) is not None)
    numbers.update(number for item in facts.execution_events if (number := _chapter_number(item.task_id)) is not None)

    status_by_chapter = {item.chapter_number: item for item in facts.chapter_statuses}
    gates_by_chapter: dict[int, list] = defaultdict(list)
    for gate in facts.gate_results:
        if gate.chapter_number is not None:
            gates_by_chapter[gate.chapter_number].append(gate)
    reports_by_chapter: dict[int, list] = defaultdict(list)
    for report in facts.runtime_reports:
        number = _chapter_number(report.chapter_id)
        if number is not None:
            reports_by_chapter[number].append(report)

    chapters: list[ChapterSnapshot] = []
    for number in sorted(numbers):
        status_fact = status_by_chapter.get(number)
        gates = gates_by_chapter[number]
        reports = reports_by_chapter[number]
        references = _unique_refs([
            *(item.source_ref for item in ([status_fact] if status_fact else [])),
            *(item.source_ref for item in gates),
            *(item.source_ref for item in reports),
        ])
        derivations: list[Derivation] = []
        blocked_by: list[Derivation] = []
        status = ChapterStatus.UNKNOWN
        if status_fact is not None:
            status = _STATUS_MAP.get(status_fact.status.lower(), ChapterStatus.UNKNOWN)
            if status is ChapterStatus.FAILED and status_fact.issues:
                status = ChapterStatus.BLOCKED
            derivations.append(Derivation("chapter.status_from_task", (status_fact.source_ref,)))
        failed_gates = [gate for gate in gates if gate.status.lower() in {"failed", "blocked", "fail"}]
        if failed_gates:
            status = ChapterStatus.BLOCKED
            blocked_by.extend(
                Derivation("chapter.blocked_by_gate", (gate.source_ref,), gate.gate_id)
                for gate in failed_gates
            )
        elif reports and any(report.stage == "compile_candidate_ready" for report in reports):
            status = ChapterStatus.PASSED
            derivations.append(Derivation(
                "chapter.completed_from_runtime_report",
                tuple(item.source_ref for item in reports if item.stage == "compile_candidate_ready"),
            ))

        chapters.append(ChapterSnapshot(
            chapter_id=f"chapter-{number:03d}",
            chapter_number=number,
            title="unknown",
            status=status,
            attempts=status_fact.attempts if status_fact else 0,
            elapsed_seconds=status_fact.elapsed_seconds if status_fact else sum(item.elapsed_seconds for item in reports),
            source_refs=references,
            stages=_project_stages(gates, reports),
            derivations=tuple(derivations),
            blocked_by=tuple(blocked_by),
        ))
    return tuple(chapters)


def _project_stages(gates: list, reports: list) -> tuple[ChapterStageSnapshot, ...]:
    states = {stage: StageStatus.UNKNOWN for stage in ChapterStage}
    refs: dict[ChapterStage, list[SourceRef]] = defaultdict(list)
    for report in reports:
        if report.stage == "compile_candidate_ready":
            for stage in ChapterStage:
                states[stage] = StageStatus.PASSED
                refs[stage].append(report.source_ref)
        elif report.stage == "review_failed":
            for stage in (ChapterStage.PLANNING, ChapterStage.ADMISSION, ChapterStage.WRITING):
                states[stage] = StageStatus.PASSED
                refs[stage].append(report.source_ref)
            states[ChapterStage.REVIEW] = StageStatus.FAILED
            states[ChapterStage.COMPILATION] = StageStatus.NOT_STARTED
            refs[ChapterStage.REVIEW].append(report.source_ref)
            refs[ChapterStage.COMPILATION].append(report.source_ref)
    for gate in gates:
        states[ChapterStage.REVIEW] = (
            StageStatus.PASSED if gate.status.lower() == "passed" else StageStatus.BLOCKED
        )
        refs[ChapterStage.REVIEW].append(gate.source_ref)
    return tuple(
        ChapterStageSnapshot(stage, states[stage], _unique_refs(refs[stage]))
        for stage in ChapterStage
    )


def _chapter_number(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.replace("-", "_")
    try:
        number = int(normalized.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        return None
    return number if number > 0 else None


def _unique_refs(values: list[SourceRef]) -> tuple[SourceRef, ...]:
    return tuple(dict.fromkeys(values))
