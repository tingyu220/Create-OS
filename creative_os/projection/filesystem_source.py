from __future__ import annotations

import hashlib
import json
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
)
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
            diagnostics=tuple(diagnostics),
            source_refs=tuple(dict.fromkeys(references)),
        )

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
    def _chapter_number(chapter_id: str) -> int | None:
        try:
            value = int(chapter_id.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            return None
        return value if value > 0 else None
