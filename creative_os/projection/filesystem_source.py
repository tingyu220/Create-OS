from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from creative_os.projection.model import DiagnosticSeverity, ProjectionDiagnostic
from creative_os.projection.provenance import SourceHead, SourceRef
from creative_os.projection.source import (
    ChapterStatusFact,
    ExecutionEventFact,
    GateResultFact,
    ProjectFacts,
    ProjectionCursor,
    QualityIssueFact,
    RuntimeReportFact,
    ActiveStateFact,
    EngagementExpectationFact,
)
from creative_os.domains.reader_engagement_store import ReaderEngagementStore
from creative_os.runtime.events import AppendOnlyEventLog, EventLogError


class ProjectionSourceError(ValueError):
    pass


class FilesystemProjectSource:
    """只读取单个项目根中的权威文件，不执行任何领域写操作。"""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).absolute()

    def read_head(self) -> tuple[SourceHead, ...]:
        metadata_path = self.project_root / "project.json"
        status_paths = self._status_paths()
        event_path = self._event_path()
        heads = [self._file_head("project_metadata", "project", metadata_path)]
        heads.append(self._collection_head("chapter_statuses", "chapter-statuses", status_paths))
        heads.append(self._collection_head("writer_validation_reports", "writer-validation", self._report_paths()))
        heads.append(self._collection_head("active_state_snapshots", "state-snapshots", self._state_paths()))
        heads.append(self._collection_head("memory_items", "memory-items", self._memory_item_paths()))
        engagement_path = self.project_root / ".creative_os" / "engagement" / "records.jsonl"
        heads.append(self._file_head("engagement_authority", "records", engagement_path))
        if event_path.is_file():
            try:
                events = AppendOnlyEventLog(event_path).events()
            except EventLogError as error:
                raise ProjectionSourceError("runtime_event_log_invalid") from error
            cursor = "0:empty" if not events else f"{events[-1].sequence}:{events[-1].event_id}"
            heads.append(SourceHead("runtime_event_log", "runtime", cursor, self._hash_file(event_path)))
        else:
            heads.append(SourceHead("runtime_event_log", "runtime", "missing", None))
        return tuple(sorted(heads, key=lambda item: (item.source_kind, item.source_id)))

    def read_facts(self, cursor: ProjectionCursor | None = None) -> ProjectFacts:
        del cursor  # 第一版全量读取，但接口保留增量游标语义。
        project_id, metadata_ref = self._read_project_identity()
        diagnostics: list[ProjectionDiagnostic] = []
        references: list[SourceRef] = [metadata_ref]

        statuses: list[ChapterStatusFact] = []
        status_paths = self._status_paths()
        if not status_paths:
            diagnostics.append(self._missing("chapter_status_source_missing"))
        for path in status_paths:
            payload = self._read_json_object(path, "chapter_status_invalid")
            reference = self._reference("chapter_status", f"chapter-{int(payload['chapter']):03d}", path)
            references.append(reference)
            try:
                issues = payload.get("issues", [])
                if not isinstance(issues, list):
                    raise TypeError
                statuses.append(ChapterStatusFact(
                    chapter_number=int(payload["chapter"]),
                    status=str(payload["status"]),
                    attempts=int(payload["attempts"]),
                    elapsed_seconds=float(payload["elapsed_seconds"]),
                    issues=tuple(str(item) for item in issues),
                    source_ref=reference,
                ))
            except (KeyError, TypeError, ValueError) as error:
                raise ProjectionSourceError("chapter_status_invalid") from error

        quality_issues: list[QualityIssueFact] = []
        gate_results: list[GateResultFact] = []
        runtime_reports: list[RuntimeReportFact] = []
        active_states: list[ActiveStateFact] = []
        engagement_expectations: list[EngagementExpectationFact] = []
        active_memory_ids = self._active_memory_ids()
        for path in self._state_paths():
            payload = self._read_json_object(path, "state_snapshot_invalid")
            if payload.get("latest_change") not in active_memory_ids:
                continue
            kind = str(payload.get("kind", "")); subject = str(payload.get("subject", ""))
            if kind not in {"character", "hook", "timeline"} or not subject:
                continue
            reference = self._reference("active_state", f"{kind}:{subject}", path)
            references.append(reference)
            state_fields = payload.get("fields", {})
            if not isinstance(state_fields, dict):
                diagnostics.append(self._diagnostic("active_state_fields_invalid", f"{kind}:{subject} 的 fields 不是结构化对象，相关字段保持缺失。"))
                state_fields = {}
            elif kind in {"hook", "foreshadow"} and not (
                isinstance(state_fields.get("open_loop"), str) and state_fields["open_loop"].strip()
            ):
                diagnostics.append(self._diagnostic("story_thread_open_loop_unproven", f"{subject} 没有权威 open_loop 字段，保持缺失。"))
            active_states.append(ActiveStateFact(kind, subject, json.dumps(state_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")), reference))

        self._read_engagement_expectations(engagement_expectations, references, diagnostics)
        report_paths = self._report_paths()
        if not report_paths:
            diagnostics.append(self._missing("writer_validation_report_source_missing"))
        for path in report_paths:
            payload = self._read_json_object(path, "writer_validation_report_invalid")
            reference = self._reference("writer_validation_report", path.stem, path)
            references.append(reference)
            try:
                chapter_id = str(payload["chapter_id"])
                mode = str(payload["mode"])
                model = str(payload["model"])
                stage = str(payload["stage"])
                review_passed = payload["review_passed"]
                blocking_codes = payload.get("blocking_codes", [])
                if type(review_passed) is not bool or not isinstance(blocking_codes, list):
                    raise TypeError
                chapter_number = self._chapter_number(chapter_id)
                gate_results.append(GateResultFact(
                    gate_id=f"novel-review:{chapter_id}",
                    status="passed" if review_passed else "failed",
                    chapter_number=chapter_number,
                    source_ref=reference,
                ))
                for index, code in enumerate(blocking_codes, start=1):
                    normalized_code = str(code).strip()
                    if not normalized_code:
                        raise ValueError
                    quality_issues.append(QualityIssueFact(
                        issue_id=f"{path.stem}:{index}:{normalized_code}",
                        code=normalized_code,
                        severity="error",
                        blocking=True,
                        scope=chapter_id,
                        source_ref=reference,
                    ))
                runtime_reports.append(RuntimeReportFact(
                    report_id=path.stem,
                    mode=mode,
                    model=model,
                    chapter_id=chapter_id,
                    stage=stage,
                    elapsed_seconds=float(payload.get("elapsed_seconds", 0.0)),
                    source_ref=reference,
                ))
            except (KeyError, TypeError, ValueError) as error:
                raise ProjectionSourceError("writer_validation_report_invalid") from error

        execution_events: list[ExecutionEventFact] = []
        event_path = self._event_path()
        if not event_path.is_file():
            diagnostics.append(self._missing("runtime_event_log_missing"))
        else:
            try:
                events = AppendOnlyEventLog(event_path).events()
            except EventLogError as error:
                raise ProjectionSourceError("runtime_event_log_invalid") from error
            event_hash = self._hash_file(event_path)
            for event in events:
                reference = SourceRef(
                    source_kind="runtime_event",
                    source_id=event.event_id,
                    locator=f"{self._relative(event_path)}:sequence={event.sequence}",
                    content_hash=event_hash,
                )
                references.append(reference)
                execution_events.append(ExecutionEventFact(
                    event_id=event.event_id,
                    event_type=event.event_type.value,
                    occurred_at=event.occurred_at,
                    sequence=event.sequence,
                    task_id=event.task_id,
                    execution_id=event.execution_id,
                    payload_json=json.dumps(event.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    source_ref=reference,
                ))

        return ProjectFacts(
            project_id=project_id,
            chapter_statuses=tuple(sorted(statuses, key=lambda item: item.chapter_number)),
            quality_issues=tuple(sorted(quality_issues, key=lambda item: item.issue_id)),
            gate_results=tuple(sorted(gate_results, key=lambda item: (item.gate_id, item.source_ref.source_id))),
            execution_events=tuple(sorted(execution_events, key=lambda item: item.sequence)),
            runtime_reports=tuple(sorted(runtime_reports, key=lambda item: item.report_id)),
            active_states=tuple(sorted(active_states, key=lambda item: (item.kind, item.subject))),
            diagnostics=tuple(diagnostics),
            source_refs=tuple(dict.fromkeys(references)),
            engagement_expectations=tuple(sorted(engagement_expectations, key=lambda item: item.expectation_id)),
        )

    def _read_engagement_expectations(
        self,
        facts: list[EngagementExpectationFact],
        references: list[SourceRef],
        diagnostics: list[ProjectionDiagnostic],
    ) -> None:
        path = self.project_root / ".creative_os" / "engagement" / "records.jsonl"
        if not path.is_file():
            diagnostics.append(self._missing("engagement_authority_source_missing"))
            return
        try:
            records = ReaderEngagementStore(self.project_root).recover_read_only()
        except ValueError:
            diagnostics.append(self._diagnostic("engagement_authority_chain_invalid", "engagement authority 链无法验证，投影保持为空。"))
            return
        by_key = {(record.record_type, record.record_id): record for record in records}
        incomplete = False
        for transition in records:
            if transition.record_type != "expectation_transition":
                continue
            decision = by_key.get(("expectation_decision", transition.record_id))
            candidate = by_key.get(("expectation_candidate", transition.record_id))
            decision_payload = decision.payload if decision is not None else None
            candidate_payload = candidate.payload if candidate is not None else None
            transition_payload = transition.payload
            decision_is_valid = (
                candidate is not None
                and decision is not None
                and isinstance(candidate_payload, dict)
                and isinstance(decision_payload, dict)
                and decision.record_id == candidate.record_id
            )
            if decision_is_valid:
                decision_is_valid = (
                    decision_payload.get("candidate_id") == candidate.record_id
                    and decision_payload.get("decision_hash") == decision.content_hash
                    and type(decision_payload.get("actor")) is str
                    and bool(decision_payload["actor"].strip())
                    and type(decision_payload.get("reason")) is str
                    and bool(decision_payload["reason"].strip())
                    and decision_payload.get("disposition") == "approved"
                )
            chain_is_valid = (
                candidate is not None
                and decision_is_valid
                and transition.record_id == candidate.record_id == decision.record_id
                and isinstance(transition_payload, dict)
                and transition_payload.get("candidate") == candidate_payload
                and type(transition.content_hash) is str
                and type(candidate.content_hash) is str
                and type(candidate_payload.get("content_hash")) is str
                and re.fullmatch(r"[0-9a-f]{64}", transition.content_hash) is not None
                and transition.content_hash == candidate.content_hash == candidate_payload["content_hash"]
            )
            if not chain_is_valid:
                incomplete = True
                continue
            if transition_payload.get("decision_hash") != decision.content_hash:
                incomplete = True
                continue
            transition_ref = self._engagement_reference(path, transition.record_id, transition.content_hash)
            decision_ref = self._engagement_reference(path, decision.record_id, decision.content_hash)
            references.extend((transition_ref, decision_ref))
            facts.append(EngagementExpectationFact(
                expectation_id=str(candidate.payload["expectation_id"]),
                from_state=str(candidate.payload["from_state"]),
                to_state=str(candidate.payload["to_state"]),
                content_hash=str(candidate.payload["content_hash"]),
                source_ref=transition_ref,
                decision_source_ref=decision_ref,
            ))
        if any(record.record_type in {"expectation_candidate", "expectation_decision"} for record in records):
            complete_ids = {item.expectation_id for item in facts}
            if any(record.record_id not in complete_ids for record in records if record.record_type in {"expectation_candidate", "expectation_decision"}):
                incomplete = True
        if incomplete:
            facts.clear()
            diagnostics.append(self._diagnostic("engagement_authority_incomplete", "engagement expectation 缺少批准 decision 或 transition 绑定不完整。"))

    def _read_project_identity(self) -> tuple[str, SourceRef]:
        path = self.project_root / "project.json"
        payload = self._read_json_object(path, "project_metadata_invalid")
        project_id = payload.get("id")
        if not isinstance(project_id, str) or not project_id.strip():
            raise ProjectionSourceError("project_id_missing")
        return project_id.strip(), self._reference("project_metadata", project_id.strip(), path)

    def _status_paths(self) -> tuple[Path, ...]:
        status_dir = self.project_root / "production" / "runs" / "status"
        return tuple(sorted(status_dir.glob("chapter_*_status.json"))) if status_dir.is_dir() else ()

    def _event_path(self) -> Path:
        return self.project_root / ".creative_os" / "runtime" / "events.jsonl"

    def _state_paths(self) -> tuple[Path, ...]:
        root = self.project_root / ".creative_os" / "state" / "snapshots"
        return tuple(sorted(root.glob("*/*.json"))) if root.is_dir() else ()

    def _memory_item_paths(self) -> tuple[Path, ...]:
        root = self.project_root / ".creative_os" / "memory" / "items"
        return tuple(sorted(root.glob("*.json"))) if root.is_dir() else ()

    def _active_memory_ids(self) -> frozenset[str]:
        paths = self._memory_item_paths()
        if not paths:
            return frozenset()
        active_ids: set[str] = set()
        for path in paths:
            payload = self._read_json_object(path, "memory_item_invalid")
            if payload.get("status") == "active" and isinstance(payload.get("id"), str):
                active_ids.add(payload["id"])
        return frozenset(active_ids)

    def _report_paths(self) -> tuple[Path, ...]:
        report_dir = self.project_root / "production" / "reports"
        return tuple(sorted(report_dir.glob("*_writer_validation.json"))) if report_dir.is_dir() else ()

    def _file_head(self, source_kind: str, source_id: str, path: Path) -> SourceHead:
        if not path.is_file():
            return SourceHead(source_kind, source_id, "missing", None)
        return SourceHead(source_kind, source_id, None, self._hash_file(path))

    def _collection_head(self, source_kind: str, source_id: str, paths: tuple[Path, ...]) -> SourceHead:
        if not paths:
            return SourceHead(source_kind, source_id, "missing", None)
        digest = hashlib.sha256()
        for path in paths:
            digest.update(self._relative(path).encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return SourceHead(source_kind, source_id, str(len(paths)), digest.hexdigest())

    def _reference(self, source_kind: str, source_id: str, path: Path) -> SourceRef:
        return SourceRef(source_kind, source_id, self._relative(path), self._hash_file(path))

    def _engagement_reference(self, path: Path, record_id: str, content_hash: str) -> SourceRef:
        return SourceRef("engagement_authority", record_id, f"{self._relative(path)}:record={record_id}", content_hash)

    def _relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.project_root).as_posix()
        except ValueError as error:
            raise ProjectionSourceError("source_outside_project_root") from error

    @staticmethod
    def _hash_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _read_json_object(path: Path, code: str) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProjectionSourceError(code) from error
        if not isinstance(payload, dict):
            raise ProjectionSourceError(code)
        return payload

    @staticmethod
    def _missing(code: str) -> ProjectionDiagnostic:
        return ProjectionDiagnostic(
            code=code,
            severity=DiagnosticSeverity.WARNING,
            message="权威来源不存在，相关投影必须保持 unknown。",
        )

    @staticmethod
    def _diagnostic(code: str, message: str) -> ProjectionDiagnostic:
        return ProjectionDiagnostic(code=code, severity=DiagnosticSeverity.WARNING, message=message)

    @staticmethod
    def _chapter_number(chapter_id: str) -> int | None:
        try:
            value = int(chapter_id.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            return None
        return value if value > 0 else None
