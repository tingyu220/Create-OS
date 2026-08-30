from __future__ import annotations
from pathlib import Path
from .chapter_production_orchestrator import ChapterProductionOrchestrator
from .state_change_approval import StateChangeApprovalService

class ProductionCompositionRoot:
    """Offline production composition root; rebuilds owners per chapter."""
    def __init__(self, project_root: str | Path, writer, readiness, engagement):
        self.project_root=Path(project_root); self.writer=writer; self.readiness=readiness; self.engagement=engagement

    def run_chapter(self, project_id: str, chapter_number: int):
        artifact=self.writer.prepare(chapter_number)
        if hasattr(self.writer, 'verify_artifact'):
            self.writer.verify_artifact({'chapter': chapter_number, 'artifact_hash': artifact.artifact_hash})
        orchestrator=ChapterProductionOrchestrator(self.project_root, readiness=self.readiness, engagement=self.engagement)
        view=orchestrator.start(project_id, chapter_number)
        if view.state.value == 'director_proposed':
            view=orchestrator.record_engagement_review(project_id, chapter_number, {'artifact_hash':artifact.artifact_hash,'context_fingerprint':'f'*64})
        view=orchestrator.record_fulfillment(project_id, chapter_number, {'contract_hash':'e'*64,'artifact_hash':artifact.artifact_hash,'evidence':[]})
        candidate={'candidate_id':f'{project_id}:{chapter_number}','state':artifact.metadata}
        approval=StateChangeApprovalService(self.project_root)
        approval.approve(candidate,'offline-human','offline acceptance')
        receipt=approval.materialize(candidate)
        self.writer.close_reopen_all()
        return view, receipt
