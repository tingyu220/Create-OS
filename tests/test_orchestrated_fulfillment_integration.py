from pathlib import Path
import pytest
from creative_os.domains.chapter_production_orchestrator import ChapterProductionOrchestrator
from creative_os.domains.chapter_run_checkpoint import ChapterRunState

def test_orchestrator_fulfillment_reopens_and_advances_checkpoint(tmp_path: Path):
    class Ready:
        def audit(self): return type('R',(),{'status':'ready'})()
    class Engagement:
        def project_chapter_locked(self,p,c): return type('P',(),{'content_hash':'a'*64})()
        def append_engagement_review(self,p): return {'record_id':p['review_id'],'content_hash':'b'*64}
        def load_exact(self,*args): return {'status':'passed'}
    o=ChapterProductionOrchestrator(tmp_path,readiness=Ready(),engagement=Engagement())
    o.start('p',1); o.record_engagement_review('p',1,{'artifact_hash':'c'*64,'context_fingerprint':'d'*64})
    view=o.record_fulfillment('p',1,{'contract_hash':'e'*64,'artifact_hash':'c'*64,'evidence':[]})
    assert view.state == ChapterRunState.FULFILLMENT_RECORDED

def test_fulfillment_rejects_wrong_artifact_hash_and_is_idempotent(tmp_path: Path):
    o=ChapterProductionOrchestrator(tmp_path)
    with pytest.raises(ValueError,match='artifact_hash'):
        o.record_fulfillment('p',1,{'contract_hash':'e'*64,'artifact_hash':'bad','evidence':[]})
