from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from creative_os.domains.novel_continuation import build_next_chapter
from creative_os.domains.contract_lifecycle import ContractLifecycleCoordinator
from creative_os.novel_continuation_runner import ContinuationRun, PreparedWriterRun, continue_one_chapter
from creative_os.runtime import AppendOnlyEventLog


class ProductionValidationClient(Protocol):
    def complete(self, messages: list[object], *, temperature: float, max_tokens: int) -> str | object:
        ...


@dataclass(frozen=True, slots=True)
class ChapterValidationResult:
    chapter_number: int
    status: str
    context_path: str
    final_chapter_path: str | None
    issue_count: int
    entity_warning_count: int = 0


@dataclass(frozen=True, slots=True)
class ContinuousValidationReport:
    project_root: str
    requested_chapters: int
    completed_chapters: int
    status: str
    chapters: tuple[ChapterValidationResult, ...]
    event_count: int
    recovery_ok: bool
    max_context_size_chars: int
    entity_warning_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "project_root": self.project_root,
            "requested_chapters": self.requested_chapters,
            "completed_chapters": self.completed_chapters,
            "status": self.status,
            "chapters": [
                {
                    "chapter_number": item.chapter_number,
                    "status": item.status,
                    "context_path": item.context_path,
                    "final_chapter_path": item.final_chapter_path,
                    "issue_count": item.issue_count,
                    "entity_warning_count": item.entity_warning_count,
                }
                for item in self.chapters
            ],
            "event_count": self.event_count,
            "recovery_ok": self.recovery_ok,
            "max_context_size_chars": self.max_context_size_chars,
            "entity_warning_count": self.entity_warning_count,
        }


def run_continuous_validation(
    prepared_runs: tuple[PreparedWriterRun, ...],
    *,
    client: ProductionValidationClient,
    max_attempts: int = 2,
) -> ContinuousValidationReport:
    if not prepared_runs or any(not isinstance(item, PreparedWriterRun) for item in prepared_runs):
        raise TypeError("continuous validation requires PreparedWriterRun values")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    root = prepared_runs[0].project_root
    if any(item.project_root != root for item in prepared_runs):
        raise ValueError("prepared runs must belong to one project")
    results: list[ChapterValidationResult] = []
    for prepared in prepared_runs:
        run = continue_one_chapter(
            prepared,
            client=client,
            max_attempts=max_attempts,
        )
        results.append(_result(run))
        if run.status != "pass":
            break
    event_log = AppendOnlyEventLog(root / ".creative_os" / "runtime" / "events.jsonl")
    recovery_ok = all(item.admission_service.validate_token(
        item.token, item.run_id, item.context.fingerprint
    ) == item.token for item in prepared_runs)
    context_sizes = [_context_size(Path(item.context_path)) for item in results]
    chapter_count = len(prepared_runs)
    status = "pass" if len(results) == chapter_count and all(item.status == "pass" for item in results) and recovery_ok else "fail"
    report = ContinuousValidationReport(
        project_root=str(root),
        requested_chapters=chapter_count,
        completed_chapters=sum(item.status == "pass" for item in results),
        status=status,
        chapters=tuple(results),
        event_count=len(event_log.events()),
        recovery_ok=recovery_ok,
        max_context_size_chars=max(context_sizes, default=0),
        entity_warning_count=sum(item.entity_warning_count for item in results),
    )
    report_path = root / "production" / "reports" / "continuous_validation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def audit_narrative_production(
    project_root: str | Path,
    *,
    first_chapter: int,
    last_chapter: int,
) -> dict[str, object]:
    if first_chapter < 1 or last_chapter < first_chapter:
        raise ValueError("invalid chapter range")
    root = Path(project_root)
    events = AppendOnlyEventLog(root / ".creative_os" / "runtime" / "events.jsonl").events()
    results: list[dict[str, object]] = []
    for chapter in range(first_chapter, last_chapter + 1):
        task_id = f"chapter-{chapter:03d}"
        context_path = root / ".creative_os" / "contexts" / "compiled" / f"chapter_{chapter:03d}.json"
        review_path = root / ".creative_os" / "reviews" / f"chapter_{chapter:03d}_continuation.json"
        final_path = root / "production" / "final_chapters" / f"chapter_{chapter:03d}.md"
        context = json.loads(context_path.read_text(encoding="utf-8")) if context_path.exists() else {}
        review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {"issues": ["missing_review"]}
        chapter_events = [event for event in events if event.task_id == task_id]
        event_types = [event.event_type.value for event in chapter_events]
        required_events = {"TaskCreated", "TaskStarted", "ContextBuilt", "CapabilityCalled", "ResultGenerated", "ReviewPassed", "KnowledgeUpdated", "StateChanged", "TaskCompleted"}
        authority_ok = _audit_contract_binding(root, chapter, context, review, chapter_events)
        complete = (
            final_path.exists()
            and not review.get("issues")
            and authority_ok
            and required_events <= set(event_types)
        )
        results.append({
            "chapter": chapter,
            "passed": complete,
            "context_size_chars": context.get("size_chars", 0),
            "entity_warning_count": len(review.get("entity_warnings", [])),
            "events": event_types,
        })
    passed = all(item["passed"] for item in results)
    report = {"range": [first_chapter, last_chapter], "passed": passed, "chapters": results, "event_count": len(events)}
    report_path = root / "production" / "reports" / f"narrative_production_audit_{first_chapter:03d}_{last_chapter:03d}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _audit_contract_binding(root: Path, chapter: int, context: object,
                            review: object, events: list[object]) -> bool:
    if not isinstance(context, dict) or set(context.get("contract_binding", {})) != {
        "contract_id", "contract_version", "contract_content_hash", "context_fingerprint",
    }:
        return False
    binding = context["contract_binding"]
    fingerprint = context.get("fingerprint")
    if (not isinstance(binding["contract_id"], str)
            or type(binding["contract_version"]) is not int
            or not isinstance(binding["contract_content_hash"], str)
            or len(binding["contract_content_hash"]) != 64
            or not isinstance(fingerprint, str) or len(fingerprint) != 64
            or binding["context_fingerprint"] != fingerprint):
        return False
    if not isinstance(review, dict) or review.get("context") != fingerprint:
        return False
    context_event_types = {"ContextBuilt", "CapabilityCalled", "ResultGenerated"}
    context_events = [event for event in events
                      if event.event_type.value in context_event_types]
    if ({event.event_type.value for event in context_events} != context_event_types
            or any(not isinstance(event.payload, dict)
                   or event.payload.get("context_id") != fingerprint
                   for event in context_events)):
        return False
    try:
        lifecycle = ContractLifecycleCoordinator(root)
        pointer = lifecycle.read_pointer(binding["contract_id"])
        decision = lifecycle.load_current(binding["contract_id"])
    except (OSError, ValueError, KeyError):
        return False
    return bool(
        pointer is not None and decision is not None
        and decision.chapter == chapter
        and decision.chapter_contract.chapter_id == f"chapter_{chapter:03d}"
        and pointer.contract_version == binding["contract_version"]
        and pointer.content_hash == binding["contract_content_hash"]
    )


def _result(run: ContinuationRun) -> ChapterValidationResult:
    return ChapterValidationResult(
        chapter_number=run.chapter_number,
        status=run.status,
        context_path=str(run.context_path),
        final_chapter_path=str(run.final_chapter_path) if run.final_chapter_path else None,
        issue_count=len(run.issues),
        entity_warning_count=len(run.entity_warnings or []),
    )


def _recovery_check(root: Path, results: list[ChapterValidationResult], *, require_narrative_contract: bool) -> bool:
    if not results:
        return False
    last = results[-1]
    if last.status != "pass" or not last.final_chapter_path:
        return False
    final_path = Path(last.final_chapter_path)
    if not final_path.exists() or not Path(last.context_path).exists():
        return False
    try:
        # Recovery validates persisted canon and state. A missing contract for the
        # next planning boundary is a readiness concern, not state corruption.
        build_next_chapter(root, require_narrative_contract=False)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False
    return True


def _context_size(path: Path) -> int:
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["size_chars"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return 0
