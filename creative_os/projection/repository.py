from __future__ import annotations
import json
import os
from pathlib import Path
from creative_os.projection.builder import ProjectProjectionBuilder, ProjectProjectionRequest
from creative_os.projection.codec import decode_project_snapshot, encode_project_snapshot
from creative_os.projection.filesystem_source import FilesystemProjectSource
from creative_os.projection.model import ProjectSnapshot
from creative_os.workspace_dto import OperationsSnapshot, TaskDTO, ExecutionDTO, ErrorDTO, RecoveryDTO, RetryDTO, SourceRef, ProjectionBundle, ProjectionSection, Freshness, UsageDTO
from creative_os.projection.model import ProjectionDiagnostic, DiagnosticSeverity
from creative_os.projection.provenance import SourceHead

BUNDLE_SCHEMA_VERSION = 1
class ProjectionRepositoryError(ValueError): pass

def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)

def _encode_source_ref(value):
    return {
        "source_kind": value.source_kind,
        "source_id": value.source_id,
        "locator": value.locator,
        "content_hash": value.content_hash,
    }


def _encode_diagnostic(value):
    return {
        "code": value.code,
        "severity": value.severity.value,
        "message": value.message,
        "source_refs": [_encode_source_ref(item) for item in value.source_refs],
    }


def _encode_operations(value):
    usage = None if value.usage is None else {
        "prompt_tokens": value.usage.prompt_tokens,
        "completion_tokens": value.usage.completion_tokens,
        "total_tokens": value.usage.total_tokens,
    }
    return {
        "project_id": value.project_id,
        "task_count": value.task_count,
        "execution_count": value.execution_count,
        "failed_count": value.failed_count,
        "attempts": value.attempts,
        "usage": usage,
        "source_refs": [_encode_source_ref(item) for item in value.source_refs],
        "diagnostics": [_encode_diagnostic(item) for item in value.diagnostics],
        "tasks": [
            {
                "task_id": item.task_id,
                "status": item.status,
                "attempts": item.attempts,
                "elapsed_seconds": item.elapsed_seconds,
                "source_refs": [_encode_source_ref(ref) for ref in item.source_refs],
            }
            for item in value.tasks
        ],
        "executions": [
            {
                "execution_id": item.execution_id,
                "identity_kind": item.identity_kind,
                "event_type": item.event_type,
                "occurred_at": item.occurred_at,
                "source_refs": [_encode_source_ref(ref) for ref in item.source_refs],
            }
            for item in value.executions
        ],
        "errors": [
            {
                "code": item.code,
                "message": item.message,
                "retryable": item.retryable,
                "source_refs": [_encode_source_ref(ref) for ref in item.source_refs],
            }
            for item in value.errors
        ],
        "recovery": None if value.recovery is None else {
            "state": value.recovery.state,
            "source_refs": [_encode_source_ref(ref) for ref in value.recovery.source_refs],
        },
        "retries": [
            {
                "attempts": item.attempts,
                "source_refs": [_encode_source_ref(ref) for ref in item.source_refs],
            }
            for item in value.retries
        ],
    }


def encode_projection_bundle(bundle: ProjectionBundle) -> str:
    payload = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "project": None if bundle.project is None else encode_project_snapshot(bundle.project),
        "operations": None if bundle.operations is None else _encode_operations(bundle.operations),
        "source_heads": [
            {
                "source_kind": item.source_kind,
                "source_id": item.source_id,
                "cursor": item.cursor,
                "content_hash": item.content_hash,
            }
            for item in bundle.source_heads
        ],
        "freshness": {key.value: value.value for key, value in bundle.freshness.items()},
        "diagnostics": [_encode_diagnostic(item) for item in bundle.diagnostics],
        "refresh_id": bundle.refresh_id,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)

def _decode_projection_bundle(payload: str) -> ProjectionBundle:
    raw = json.loads(payload)
    if set(raw) != {"schema_version", "project", "operations", "source_heads", "freshness", "diagnostics", "refresh_id"} or raw["schema_version"] != BUNDLE_SCHEMA_VERSION: raise ProjectionRepositoryError("projection_bundle_schema_invalid")
    project = None if raw["project"] is None else decode_project_snapshot(raw["project"])
    heads = tuple(SourceHead(**item) for item in raw["source_heads"])
    if set(raw["freshness"]) != {"project", "operations"}: raise ProjectionRepositoryError("projection_freshness_fields_invalid")
    freshness = {ProjectionSection(key): Freshness(value) for key, value in raw["freshness"].items()}
    operations = None
    if raw["operations"] is not None:
        item = raw["operations"]
        required = {"project_id","task_count","execution_count","failed_count","attempts","usage","source_refs","diagnostics","tasks","executions","errors","recovery","retries"}
        if set(item) != required: raise ProjectionRepositoryError("projection_operations_fields_invalid")
        def ref(x):
            if set(x) != {"source_kind","source_id","locator","content_hash"}: raise ProjectionRepositoryError("projection_source_ref_invalid")
            return SourceRef(x["source_kind"], x["source_id"], x["locator"], x["content_hash"])
        usage = item["usage"]
        if usage is not None:
            if set(usage) != {"prompt_tokens","completion_tokens","total_tokens"}: raise ProjectionRepositoryError("projection_usage_invalid")
            usage = UsageDTO(**usage)
        diagnostics = tuple(ProjectionDiagnostic(x["code"], DiagnosticSeverity(x["severity"]), x["message"], tuple(ref(r) for r in x["source_refs"])) for x in item["diagnostics"])
        tasks = tuple(TaskDTO(x["task_id"], x["status"], x["attempts"], x["elapsed_seconds"], tuple(ref(r) for r in x["source_refs"])) for x in item["tasks"])
        executions = tuple(ExecutionDTO(x["execution_id"], x["identity_kind"], x["event_type"], x["occurred_at"], tuple(ref(r) for r in x["source_refs"])) for x in item["executions"])
        if any(x.identity_kind not in {"execution_id", "event_id"} for x in executions): raise ProjectionRepositoryError("projection_operations_execution_identity_invalid")
        errors = tuple(ErrorDTO(x["code"], x["message"], x["retryable"], tuple(ref(r) for r in x["source_refs"])) for x in item["errors"])
        recovery = None if item["recovery"] is None else RecoveryDTO(item["recovery"]["state"], tuple(ref(r) for r in item["recovery"]["source_refs"]))
        retries = tuple(RetryDTO(x["attempts"], tuple(ref(r) for r in x["source_refs"])) for x in item["retries"])
        if project is not None and item["project_id"] != project.project_id: raise ProjectionRepositoryError("projection_project_id_mismatch")
        for name in ("task_count", "execution_count", "failed_count", "attempts"):
            if type(item[name]) is not int or item[name] < 0: raise ProjectionRepositoryError("projection_operations_count_invalid")
        operations = OperationsSnapshot(item["project_id"], item["task_count"], item["execution_count"], item["failed_count"], item["attempts"], usage, tuple(ref(x) for x in item["source_refs"]), diagnostics, tasks, executions, errors, recovery, retries)
    diagnostics = tuple(ProjectionDiagnostic(x["code"], DiagnosticSeverity(x["severity"]), x["message"], tuple(SourceRef(**r) for r in x["source_refs"])) for x in raw["diagnostics"])
    return ProjectionBundle(project, operations, heads, freshness, diagnostics, raw.get("refresh_id"))

def decode_projection_bundle(payload: str) -> ProjectionBundle:
    try:
        return _decode_projection_bundle(payload)
    except ProjectionRepositoryError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ProjectionRepositoryError("projection_bundle_nested_invalid") from error

class FileProjectionRepository:
    """项目内原子保存 projection bundle 与刷新日志。"""
    def __init__(self, project_root: str | Path, expected_project_id: str | None = None) -> None:
        self.root = Path(project_root).absolute() / ".creative_os" / "projection"
        self.expected_project_id = expected_project_id
        self.bundle_path, self.journal_path = self.root / "bundle.json", self.root / "refresh-journal.jsonl"

    def read_bundle(self, project_id: str):
        if self.expected_project_id is not None and project_id != self.expected_project_id: raise ProjectionRepositoryError("projection_project_id_mismatch")
        if not self.bundle_path.is_file():
            return None
        try:
            payload = json.loads(self.bundle_path.read_text(encoding="utf-8"))
            bundle = decode_projection_bundle(json.dumps(payload, ensure_ascii=False))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise ProjectionRepositoryError("projection_bundle_corrupt") from error
        if bundle.project is not None and bundle.project.project_id != project_id: raise ProjectionRepositoryError("projection_project_id_mismatch")
        return bundle

    def current_heads(self, project_id: str):
        if self.expected_project_id is not None and project_id != self.expected_project_id: raise ProjectionRepositoryError("projection_project_id_mismatch")
        return FilesystemProjectSource(self.root.parent.parent).read_head()

    def publish(self, snapshot: ProjectSnapshot, operations: OperationsSnapshot, refresh_id: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.expected_project_id is not None and snapshot.project_id != self.expected_project_id: raise ProjectionRepositoryError("projection_project_id_mismatch")
        operation_status = Freshness.PARTIAL if operations.diagnostics else Freshness.FRESH
        bundle = ProjectionBundle(
            snapshot,
            operations,
            snapshot.source_heads,
            {ProjectionSection.PROJECT: Freshness.FRESH, ProjectionSection.OPERATIONS: operation_status},
            snapshot.diagnostics,
            refresh_id,
        )
        payload = json.loads(encode_projection_bundle(bundle))
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        decode_projection_bundle(encoded)
        _atomic_write(self.bundle_path, encoded)
        decode_projection_bundle(self.bundle_path.read_text(encoding="utf-8"))

class RepositoryRefreshBuilder:
    def __init__(self, project_root: str | Path, repository: FileProjectionRepository) -> None:
        self.repository, self.builder = repository, ProjectProjectionBuilder(FilesystemProjectSource(project_root))
    def __call__(self, project_id: str, _sections, refresh_id: str) -> ProjectSnapshot:
        result = self.builder.build(ProjectProjectionRequest(project_id=project_id))
        operations = OperationsSnapshot.from_project(result.snapshot)
        snapshot = ProjectSnapshot.create(project_id=result.snapshot.project_id, built_at=result.snapshot.built_at, source_heads=result.snapshot.source_heads, overview=result.snapshot.overview, chapters=result.snapshot.chapters, quality=result.snapshot.quality, trace=result.snapshot.trace, characters=result.snapshot.characters, story_threads=result.snapshot.story_threads, timeline=result.snapshot.timeline, diagnostics=result.snapshot.diagnostics)
        if snapshot.snapshot_id != result.snapshot.snapshot_id:
            raise RuntimeError("projection_snapshot_mutated_after_operations_projection")
        self.repository.publish(result.snapshot, operations, refresh_id)
        return result.snapshot
