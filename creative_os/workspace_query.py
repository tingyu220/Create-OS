from __future__ import annotations
from typing import Protocol
from creative_os.projection.model import ProjectSnapshot
from creative_os.projection.provenance import SourceHead
from creative_os.workspace_dto import Freshness, OperationsSnapshot, ProjectionBundle, ProjectionEnvelope, ProjectionSection, SectionEnvelope
from creative_os.projection.model import DiagnosticSeverity, ProjectionDiagnostic

class ProjectionRepository(Protocol):
    def read_bundle(self, project_id: str) -> ProjectionBundle | None: ...
    def current_heads(self, project_id: str) -> tuple[SourceHead, ...]: ...

class WorkspaceQueryAdapter:
    """只将投影仓库映射为 Web DTO，不读取任何权威层。"""
    def __init__(self, repository: ProjectionRepository) -> None:
        self._repository = repository

    def get_workspace(self, project_id: str) -> ProjectionEnvelope:
        diagnostics = ()
        try:
            bundle = self._repository.read_bundle(project_id)
            heads = tuple(self._repository.current_heads(project_id))
        except Exception as error:
            diagnostics = (ProjectionDiagnostic("workspace_projection_unavailable", DiagnosticSeverity.ERROR, str(error)),)
            return ProjectionEnvelope(project_id, None, None, Freshness.UNAVAILABLE, {ProjectionSection.PROJECT: SectionEnvelope(Freshness.UNAVAILABLE, diagnostics), ProjectionSection.OPERATIONS: SectionEnvelope(Freshness.UNAVAILABLE, diagnostics)}, (), None)
        if bundle is None:
            snapshot, operations = None, None
        else:
            snapshot, operations = bundle.project, bundle.operations
        source_drift = bundle is not None and tuple(bundle.source_heads) != heads
        project_status = bundle.freshness.get(ProjectionSection.PROJECT, Freshness.FRESH) if bundle else Freshness.UNAVAILABLE
        if snapshot is not None and source_drift: project_status = Freshness.STALE
        if snapshot is None:
            project_status = Freshness.UNAVAILABLE
        operation_status = bundle.freshness.get(ProjectionSection.OPERATIONS, Freshness.UNAVAILABLE) if bundle else Freshness.UNAVAILABLE
        if operations is None:
            operation_status = Freshness.UNAVAILABLE
        elif source_drift:
            operation_status = Freshness.STALE
        statuses = {ProjectionSection.PROJECT: SectionEnvelope(project_status, () if not bundle else bundle.diagnostics), ProjectionSection.OPERATIONS: SectionEnvelope(operation_status, () if not bundle else bundle.diagnostics)}
        overall = aggregate_freshness((project_status, operation_status))
        return ProjectionEnvelope(project_id, snapshot, operations, overall, statuses, heads, None if not bundle else bundle.refresh_id)

def aggregate_freshness(statuses: tuple[Freshness, ...]) -> Freshness:
    values = set(statuses)
    if values == {Freshness.FRESH}: return Freshness.FRESH
    if Freshness.STALE in values: return Freshness.STALE
    if values == {Freshness.UNAVAILABLE}: return Freshness.UNAVAILABLE
    return Freshness.PARTIAL
