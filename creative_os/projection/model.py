from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum, StrEnum
import hashlib
import json
from typing import Any

from creative_os.projection.chapters import ChapterSnapshot
from creative_os.projection.overview import OverviewSnapshot
from creative_os.projection.provenance import SourceHead, SourceRef
from creative_os.projection.quality import QualitySnapshot
from creative_os.projection.trace import TraceSnapshot
from creative_os.projection.narrative import CharacterSnapshot, StoryThreadSnapshot, TimelineEntrySnapshot


PROJECT_SNAPSHOT_SCHEMA_VERSION = 2


class DiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ProjectionDiagnostic:
    code: str
    severity: DiagnosticSeverity
    message: str
    source_refs: tuple[SourceRef, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    schema_version: int
    snapshot_id: str
    project_id: str
    built_at: str
    source_heads: tuple[SourceHead, ...]
    overview: OverviewSnapshot
    chapters: tuple[ChapterSnapshot, ...]
    quality: QualitySnapshot
    trace: TraceSnapshot
    characters: tuple[CharacterSnapshot, ...] = ()
    story_threads: tuple[StoryThreadSnapshot, ...] = ()
    timeline: tuple[TimelineEntrySnapshot, ...] = ()
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        built_at: str,
        source_heads: tuple[SourceHead, ...],
        overview: OverviewSnapshot,
        chapters: tuple[ChapterSnapshot, ...],
        quality: QualitySnapshot,
        trace: TraceSnapshot,
        characters: tuple[CharacterSnapshot, ...] = (),
        story_threads: tuple[StoryThreadSnapshot, ...] = (),
        timeline: tuple[TimelineEntrySnapshot, ...] = (),
        diagnostics: tuple[ProjectionDiagnostic, ...] = (),
    ) -> "ProjectSnapshot":
        normalized_project_id = project_id.strip()
        if not normalized_project_id:
            raise ValueError("project_id_required")
        if not built_at.strip():
            raise ValueError("snapshot_built_at_required")
        if not source_heads:
            raise ValueError("snapshot_source_heads_required")
        identity = {
            "schema_version": PROJECT_SNAPSHOT_SCHEMA_VERSION,
            "project_id": normalized_project_id,
            "source_heads": source_heads,
            "overview": overview,
            "chapters": chapters,
            "quality": quality,
            "trace": trace,
            "characters": characters,
            "story_threads": story_threads,
            "timeline": timeline,
            "diagnostics": diagnostics,
        }
        digest = hashlib.sha256(
            json.dumps(_canonical(identity), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(
            schema_version=PROJECT_SNAPSHOT_SCHEMA_VERSION,
            snapshot_id=digest,
            project_id=normalized_project_id,
            built_at=built_at.strip(),
            source_heads=source_heads,
            overview=overview,
            chapters=chapters,
            quality=quality,
            trace=trace,
            characters=characters,
            story_threads=story_threads,
            timeline=timeline,
            diagnostics=diagnostics,
        )


def _canonical(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    return value
