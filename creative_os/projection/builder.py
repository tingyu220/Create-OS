from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from creative_os.projection.model import ProjectSnapshot
from creative_os.projection.projectors.chapters import project_chapters
from creative_os.projection.projectors.overview import project_overview
from creative_os.projection.projectors.quality import project_quality
from creative_os.projection.projectors.trace import project_trace
from creative_os.projection.projectors.narrative import project_characters, project_story_threads, project_timeline
from creative_os.projection.source import ProjectSource, ProjectionCursor


class ProjectionBuildError(RuntimeError):
    pass


class ProjectionConsistencyError(ProjectionBuildError):
    pass


class ProjectionProjectMismatchError(ProjectionBuildError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectProjectionRequest:
    project_id: str
    previous_cursor: ProjectionCursor | None = None
    requested_sections: tuple[str, ...] = ("overview", "chapters", "quality", "trace", "characters", "story_threads", "timeline")

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("projection_project_id_required")


@dataclass(frozen=True, slots=True)
class ProjectionBuildResult:
    snapshot: ProjectSnapshot
    cursor: ProjectionCursor
    refresh_mode: str
    attempts: int


class ProjectProjectionBuilder:
    def __init__(
        self,
        source: ProjectSource,
        *,
        max_attempts: int = 3,
        clock: Callable[[], str] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("projection_max_attempts_invalid")
        self.source = source
        self.max_attempts = max_attempts
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())

    def build(self, request: ProjectProjectionRequest) -> ProjectionBuildResult:
        required = {"overview", "chapters", "quality", "trace", "characters", "story_threads", "timeline"}
        if set(request.requested_sections) != required:
            raise ProjectionBuildError("projection_partial_sections_not_supported")
        for attempt in range(1, self.max_attempts + 1):
            before = self.source.read_head()
            facts = self.source.read_facts(request.previous_cursor)
            if facts.project_id != request.project_id:
                raise ProjectionProjectMismatchError("projection_project_mismatch")
            chapters = project_chapters(facts)
            quality = project_quality(facts)
            trace = project_trace(facts)
            overview = project_overview(chapters=chapters, quality=quality, trace=trace)
            characters = project_characters(facts)
            story_threads = project_story_threads(facts)
            timeline = project_timeline(facts)
            after = self.source.read_head()
            if before != after:
                continue
            snapshot = ProjectSnapshot.create(
                project_id=request.project_id,
                built_at=self.clock(),
                source_heads=after,
                overview=overview,
                chapters=chapters,
                quality=quality,
                trace=trace,
                characters=characters,
                story_threads=story_threads,
                timeline=timeline,
                diagnostics=facts.diagnostics,
            )
            return ProjectionBuildResult(
                snapshot=snapshot,
                cursor=ProjectionCursor(after),
                refresh_mode="full",
                attempts=attempt,
            )
        raise ProjectionConsistencyError("projection_source_drift")
