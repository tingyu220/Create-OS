from __future__ import annotations

import json
import hashlib
from typing import Any

from creative_os.projection.chapters import (
    ChapterSnapshot,
    ChapterStage,
    ChapterStageSnapshot,
    ChapterStatus,
    StageStatus,
)
from creative_os.projection.model import (
    PROJECT_SNAPSHOT_SCHEMA_VERSION,
    DiagnosticSeverity,
    ProjectSnapshot,
    ProjectionDiagnostic,
    _canonical,
)
from creative_os.projection.overview import OverviewBlocker, OverviewSnapshot, ProjectRunStatus
from creative_os.projection.provenance import Derivation, SourceHead, SourceRef
from creative_os.projection.quality import GateResultSnapshot, QualityIssueSnapshot, QualitySnapshot
from creative_os.projection.trace import TraceEntrySnapshot, TraceSnapshot
from creative_os.projection.narrative import CharacterSnapshot, StoryThreadSnapshot, TimelineEntrySnapshot


class ProjectionCodecError(ValueError):
    pass


_V1_FIELDS = {
    "schema_version", "snapshot_id", "project_id", "built_at", "source_heads",
    "overview", "chapters", "quality", "trace", "diagnostics",
}
_V2_FIELDS = _V1_FIELDS | {"characters", "story_threads", "timeline"}


def encode_project_snapshot(snapshot: ProjectSnapshot) -> str:
    payload = {
        "schema_version": snapshot.schema_version,
        "snapshot_id": snapshot.snapshot_id,
        "project_id": snapshot.project_id,
        "built_at": snapshot.built_at,
        "source_heads": [_encode_head(item) for item in snapshot.source_heads],
        "overview": _encode_overview(snapshot.overview),
        "chapters": [_encode_chapter(item) for item in snapshot.chapters],
        "quality": _encode_quality(snapshot.quality),
        "trace": _encode_trace(snapshot.trace),
        "characters": [_encode_character(item) for item in snapshot.characters],
        "story_threads": [_encode_story_thread(item) for item in snapshot.story_threads],
        "timeline": [_encode_timeline(item) for item in snapshot.timeline],
        "diagnostics": [_encode_diagnostic(item) for item in snapshot.diagnostics],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def decode_project_snapshot(payload: str) -> ProjectSnapshot:
    try:
        raw = json.loads(payload)
        raw = _object(raw)
        if type(raw.get("schema_version")) is not int:
            raise ProjectionCodecError("project_snapshot_schema_unsupported")
        schema_version = raw["schema_version"]
        if schema_version == 1:
            _keys(raw, _V1_FIELDS, "project_snapshot_fields_invalid")
        elif schema_version == PROJECT_SNAPSHOT_SCHEMA_VERSION:
            _keys(raw, _V2_FIELDS, "project_snapshot_fields_invalid")
        else:
            raise ProjectionCodecError("project_snapshot_schema_unsupported")
        snapshot = ProjectSnapshot.create(
            project_id=_text(raw["project_id"]),
            built_at=_text(raw["built_at"]),
            source_heads=tuple(_decode_head(item) for item in _list(raw["source_heads"])),
            overview=_decode_overview(raw["overview"]),
            chapters=tuple(_decode_chapter(item) for item in _list(raw["chapters"])),
            quality=_decode_quality(raw["quality"]),
            trace=_decode_trace(raw["trace"]),
            characters=tuple(_decode_character(item) for item in _list(raw.get("characters", []))),
            story_threads=tuple(_decode_story_thread(item) for item in _list(raw.get("story_threads", []))),
            timeline=tuple(_decode_timeline(item) for item in _list(raw.get("timeline", []))),
            diagnostics=tuple(_decode_diagnostic(item) for item in _list(raw["diagnostics"])),
        )
        expected_id = snapshot.snapshot_id if schema_version == PROJECT_SNAPSHOT_SCHEMA_VERSION else _legacy_snapshot_id(snapshot)
        actual_id = _text(raw["snapshot_id"])
        if expected_id != actual_id and (
            schema_version != PROJECT_SNAPSHOT_SCHEMA_VERSION
            or _legacy_quality_snapshot_id(raw) != actual_id
        ):
            raise ProjectionCodecError("project_snapshot_id_mismatch")
        return snapshot
    except ProjectionCodecError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ProjectionCodecError("project_snapshot_invalid") from error


def _legacy_snapshot_id(snapshot: ProjectSnapshot) -> str:
    identity = {
        "schema_version": 1,
        "project_id": snapshot.project_id,
        "source_heads": snapshot.source_heads,
        "overview": snapshot.overview,
        "chapters": snapshot.chapters,
        "quality": snapshot.quality,
        "trace": snapshot.trace,
        "diagnostics": snapshot.diagnostics,
    }
    return hashlib.sha256(
        json.dumps(_canonical(identity), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _legacy_quality_snapshot_id(raw: dict[str, Any]) -> str:
    """计算加入 disposition_status 前的 v2 快照摘要，用于兼容旧缓存。"""
    identity = {key: raw[key] for key in (
        "schema_version", "project_id", "source_heads", "overview", "chapters", "quality", "trace",
        "characters", "story_threads", "timeline", "diagnostics",
    )}
    quality = identity["quality"]
    if isinstance(quality, dict) and isinstance(quality.get("issues"), list):
        quality = dict(quality)
        quality["issues"] = [
            {key: item[key] for key in ("issue_id", "code", "severity", "blocking", "scope", "source_refs")}
            for item in quality["issues"] if isinstance(item, dict)
        ]
        identity["quality"] = quality
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _encode_ref(value: SourceRef) -> dict[str, object]:
    return {
        "source_kind": value.source_kind,
        "source_id": value.source_id,
        "locator": value.locator,
        "content_hash": value.content_hash,
    }


def _decode_ref(value: object) -> SourceRef:
    raw = _object(value)
    _keys(raw, {"source_kind", "source_id", "locator", "content_hash"}, "source_ref_fields_invalid")
    return SourceRef(*(_text(raw[key]) for key in ("source_kind", "source_id", "locator", "content_hash")))


def _encode_head(value: SourceHead) -> dict[str, object]:
    return {
        "source_kind": value.source_kind,
        "source_id": value.source_id,
        "cursor": value.cursor,
        "content_hash": value.content_hash,
    }


def _decode_head(value: object) -> SourceHead:
    raw = _object(value)
    _keys(raw, {"source_kind", "source_id", "cursor", "content_hash"}, "source_head_fields_invalid")
    return SourceHead(
        _text(raw["source_kind"]),
        _text(raw["source_id"]),
        _optional_text(raw["cursor"]),
        _optional_text(raw["content_hash"]),
    )


def _encode_derivation(value: Derivation) -> dict[str, object]:
    return {
        "rule_id": value.rule_id,
        "inputs": [_encode_ref(item) for item in value.inputs],
        "explanation": value.explanation,
    }


def _decode_derivation(value: object) -> Derivation:
    raw = _object(value)
    _keys(raw, {"rule_id", "inputs", "explanation"}, "derivation_fields_invalid")
    return Derivation(
        _text(raw["rule_id"]),
        tuple(_decode_ref(item) for item in _list(raw["inputs"])),
        _text(raw["explanation"], allow_empty=True),
    )


def _encode_overview(value: OverviewSnapshot) -> dict[str, object]:
    return {
        "current_stage": value.current_stage,
        "run_status": value.run_status.value,
        "chapter_count": value.chapter_count,
        "blocked_chapter_count": value.blocked_chapter_count,
        "source_refs": [_encode_ref(item) for item in value.source_refs],
        "blockers": [{
            "code": item.code,
            "message": item.message,
            "derivation": _encode_derivation(item.derivation),
        } for item in value.blockers],
    }


def _decode_overview(value: object) -> OverviewSnapshot:
    raw = _object(value)
    _keys(raw, {"current_stage", "run_status", "chapter_count", "blocked_chapter_count", "source_refs", "blockers"}, "overview_fields_invalid")
    blockers = []
    for item in _list(raw["blockers"]):
        blocker = _object(item)
        _keys(blocker, {"code", "message", "derivation"}, "overview_blocker_fields_invalid")
        blockers.append(OverviewBlocker(
            _text(blocker["code"]),
            _text(blocker["message"]),
            _decode_derivation(blocker["derivation"]),
        ))
    return OverviewSnapshot(
        _text(raw["current_stage"]),
        ProjectRunStatus(_text(raw["run_status"])),
        _integer(raw["chapter_count"]),
        _integer(raw["blocked_chapter_count"]),
        tuple(_decode_ref(item) for item in _list(raw["source_refs"])),
        tuple(blockers),
    )


def _encode_chapter(value: ChapterSnapshot) -> dict[str, object]:
    return {
        "chapter_id": value.chapter_id,
        "chapter_number": value.chapter_number,
        "title": value.title,
        "status": value.status.value,
        "attempts": value.attempts,
        "elapsed_seconds": value.elapsed_seconds,
        "source_refs": [_encode_ref(item) for item in value.source_refs],
        "stages": [{
            "stage": item.stage.value,
            "status": item.status.value,
            "source_refs": [_encode_ref(ref) for ref in item.source_refs],
            "derivations": [_encode_derivation(entry) for entry in item.derivations],
        } for item in value.stages],
        "derivations": [_encode_derivation(item) for item in value.derivations],
        "blocked_by": [_encode_derivation(item) for item in value.blocked_by],
        "checkpoint_state": value.checkpoint_state,
    }


def _decode_chapter(value: object) -> ChapterSnapshot:
    raw = _object(value)
    expected = {"chapter_id", "chapter_number", "title", "status", "attempts", "elapsed_seconds", "source_refs", "stages", "derivations", "blocked_by"}
    if set(raw) not in (expected, expected | {"checkpoint_state"}):
        raise ProjectionCodecError("chapter_fields_invalid")
    stages = []
    for item in _list(raw["stages"]):
        stage = _object(item)
        _keys(stage, {"stage", "status", "source_refs", "derivations"}, "chapter_stage_fields_invalid")
        stages.append(ChapterStageSnapshot(
            ChapterStage(_text(stage["stage"])),
            StageStatus(_text(stage["status"])),
            tuple(_decode_ref(ref) for ref in _list(stage["source_refs"])),
            tuple(_decode_derivation(entry) for entry in _list(stage["derivations"])),
        ))
    return ChapterSnapshot(
        chapter_id=_text(raw["chapter_id"]),
        chapter_number=_integer(raw["chapter_number"]),
        title=_text(raw["title"]),
        status=ChapterStatus(_text(raw["status"])),
        attempts=_integer(raw["attempts"]),
        elapsed_seconds=_number(raw["elapsed_seconds"]),
        source_refs=tuple(_decode_ref(item) for item in _list(raw["source_refs"])),
        stages=tuple(stages),
        derivations=tuple(_decode_derivation(item) for item in _list(raw["derivations"])),
        blocked_by=tuple(_decode_derivation(item) for item in _list(raw["blocked_by"])),
        checkpoint_state=_optional_text(raw.get("checkpoint_state")),
    )


def _encode_quality(value: QualitySnapshot) -> dict[str, object]:
    return {
        "issues": [{
            "issue_id": item.issue_id,
            "code": item.code,
            "severity": item.severity,
            "blocking": item.blocking,
            "scope": item.scope,
            "source_refs": [_encode_ref(ref) for ref in item.source_refs],
            "disposition_status": item.disposition_status,
        } for item in value.issues],
        "gate_results": [{
            "gate_id": item.gate_id,
            "status": item.status,
            "source_refs": [_encode_ref(ref) for ref in item.source_refs],
            "derivations": [_encode_derivation(entry) for entry in item.derivations],
        } for item in value.gate_results],
        "source_refs": [_encode_ref(item) for item in value.source_refs],
    }


def _decode_quality(value: object) -> QualitySnapshot:
    raw = _object(value)
    _keys(raw, {"issues", "gate_results", "source_refs"}, "quality_fields_invalid")
    issues = []
    for item in _list(raw["issues"]):
        issue = _object(item)
        keys = set(issue)
        if keys not in (
            {"issue_id", "code", "severity", "blocking", "scope", "source_refs"},
            {"issue_id", "code", "severity", "blocking", "scope", "source_refs", "disposition_status"},
        ):
            raise ProjectionCodecError("quality_issue_fields_invalid")
        issues.append(QualityIssueSnapshot(
            _text(issue["issue_id"]), _text(issue["code"]), _text(issue["severity"]),
            _boolean(issue["blocking"]), _text(issue["scope"]),
            tuple(_decode_ref(ref) for ref in _list(issue["source_refs"])),
            None if issue.get("disposition_status") is None else _text(issue["disposition_status"]),
        ))
    gates = []
    for item in _list(raw["gate_results"]):
        gate = _object(item)
        _keys(gate, {"gate_id", "status", "source_refs", "derivations"}, "gate_result_fields_invalid")
        gates.append(GateResultSnapshot(
            _text(gate["gate_id"]), _text(gate["status"]),
            tuple(_decode_ref(ref) for ref in _list(gate["source_refs"])),
            tuple(_decode_derivation(entry) for entry in _list(gate["derivations"])),
        ))
    return QualitySnapshot(tuple(issues), tuple(gates), tuple(_decode_ref(item) for item in _list(raw["source_refs"])))


def _encode_trace(value: TraceSnapshot) -> dict[str, object]:
    return {
        "entries": [{
            "trace_kind": item.trace_kind,
            "sequence": item.sequence,
            "event_id": item.event_id,
            "event_type": item.event_type,
            "occurred_at": item.occurred_at,
            "task_id": item.task_id,
            "execution_id": item.execution_id,
            "summary": item.summary,
            "source_refs": [_encode_ref(ref) for ref in item.source_refs],
        } for item in value.entries],
        "source_refs": [_encode_ref(item) for item in value.source_refs],
    }


def _decode_trace(value: object) -> TraceSnapshot:
    raw = _object(value)
    _keys(raw, {"entries", "source_refs"}, "trace_fields_invalid")
    entries = []
    for item in _list(raw["entries"]):
        entry = _object(item)
        _keys(entry, {"trace_kind", "sequence", "event_id", "event_type", "occurred_at", "task_id", "execution_id", "summary", "source_refs"}, "trace_entry_fields_invalid")
        entries.append(TraceEntrySnapshot(
            trace_kind=_text(entry["trace_kind"]),
            sequence=None if entry["sequence"] is None else _integer(entry["sequence"]),
            event_id=_optional_text(entry["event_id"]),
            event_type=_text(entry["event_type"]),
            occurred_at=_text(entry["occurred_at"]),
            task_id=_optional_text(entry["task_id"]),
            execution_id=_optional_text(entry["execution_id"]),
            summary=_text(entry["summary"]),
            source_refs=tuple(_decode_ref(ref) for ref in _list(entry["source_refs"])),
        ))
    return TraceSnapshot(tuple(entries), tuple(_decode_ref(item) for item in _list(raw["source_refs"])))


def _encode_character(value: CharacterSnapshot) -> dict[str, object]:
    return {"subject": value.subject, "fields_json": value.fields_json,
            "source_refs": [_encode_ref(item) for item in value.source_refs],
            "derivation": _encode_derivation(value.derivation)}


def _decode_character(value: object) -> CharacterSnapshot:
    raw = _object(value)
    _keys(raw, {"subject", "fields_json", "source_refs", "derivation"}, "character_fields_invalid")
    return CharacterSnapshot(_text(raw["subject"]), _text(raw["fields_json"], allow_empty=True),
                             tuple(_decode_ref(item) for item in _list(raw["source_refs"])),
                             _decode_derivation(raw["derivation"]))


def _encode_story_thread(value: StoryThreadSnapshot) -> dict[str, object]:
    return {"subject": value.subject, "thread_type": value.thread_type, "status": value.status,
            "fields_json": value.fields_json, "source_refs": [_encode_ref(item) for item in value.source_refs],
            "derivation": _encode_derivation(value.derivation), "open_loop": value.open_loop}


def _decode_story_thread(value: object) -> StoryThreadSnapshot:
    raw = _object(value)
    _keys(raw, {"subject", "thread_type", "status", "fields_json", "source_refs", "derivation", "open_loop"}, "story_thread_fields_invalid")
    return StoryThreadSnapshot(_text(raw["subject"]), _text(raw["thread_type"]), _text(raw["status"]),
                               _text(raw["fields_json"], allow_empty=True),
                               tuple(_decode_ref(item) for item in _list(raw["source_refs"])),
                               _decode_derivation(raw["derivation"]),
                               _optional_text(raw["open_loop"]))


def _encode_timeline(value: TimelineEntrySnapshot) -> dict[str, object]:
    return {"subject": value.subject, "precision": value.precision, "relative_order": value.relative_order,
            "conflict_status": value.conflict_status, "fields_json": value.fields_json,
            "source_refs": [_encode_ref(item) for item in value.source_refs],
            "derivation": _encode_derivation(value.derivation)}


def _decode_timeline(value: object) -> TimelineEntrySnapshot:
    raw = _object(value)
    _keys(raw, {"subject", "precision", "relative_order", "conflict_status", "fields_json", "source_refs", "derivation"}, "timeline_fields_invalid")
    return TimelineEntrySnapshot(_text(raw["subject"]), _text(raw["precision"]), _text(raw["relative_order"]),
                                 _text(raw["conflict_status"]),
                                 _text(raw["fields_json"], allow_empty=True),
                                 tuple(_decode_ref(item) for item in _list(raw["source_refs"])),
                                 _decode_derivation(raw["derivation"]))


def _encode_diagnostic(value: ProjectionDiagnostic) -> dict[str, object]:
    return {
        "code": value.code,
        "severity": value.severity.value,
        "message": value.message,
        "source_refs": [_encode_ref(item) for item in value.source_refs],
    }


def _decode_diagnostic(value: object) -> ProjectionDiagnostic:
    raw = _object(value)
    _keys(raw, {"code", "severity", "message", "source_refs"}, "diagnostic_fields_invalid")
    return ProjectionDiagnostic(
        _text(raw["code"]), DiagnosticSeverity(_text(raw["severity"])), _text(raw["message"]),
        tuple(_decode_ref(item) for item in _list(raw["source_refs"])),
    )


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProjectionCodecError("object_required")
    return {str(key): item for key, item in value.items()}


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ProjectionCodecError("list_required")
    return value


def _keys(value: object, expected: set[str], code: str) -> None:
    raw = _object(value)
    if set(raw) != expected:
        raise ProjectionCodecError(code)


def _text(value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ProjectionCodecError("text_required")
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value)


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ProjectionCodecError("integer_required")
    return value


def _number(value: object) -> float:
    if type(value) not in {int, float}:
        raise ProjectionCodecError("number_required")
    # 保留权威投影的 int/float 语义，避免重建 snapshot_id 时发生隐式类型漂移。
    return value  # type: ignore[return-value]


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise ProjectionCodecError("boolean_required")
    return value
