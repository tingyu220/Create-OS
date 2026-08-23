from pathlib import Path
from creative_os.domains.chapter_production_orchestrator import ChapterProductionOrchestrator
from creative_os.domains.chapter_run_checkpoint import ChapterRunState

def test_orchestrator_appends_authoritative_engagement_review_after_fake_artifact(tmp_path: Path):
    class Ready:
        def audit(self): return type('R',(),{'status':'ready'})()
    class Engagement:
        def project_chapter_locked(self,p,c): return type('P',(),{'content_hash':'a'*64})()
        def append_engagement_review(self,payload): return {'record_id':payload['review_id'],'content_hash':'b'*64}
        def load_exact(self,*args): return {'status':'passed'}
    orchestrator=ChapterProductionOrchestrator(tmp_path, readiness=Ready(), engagement=Engagement())
    view=orchestrator.start('p',1)
    reviewed=orchestrator.record_engagement_review('p',1, {'artifact_hash':'c'*64,'context_fingerprint':'d'*64})
    assert reviewed.state == ChapterRunState.ENGAGEMENT_REVIEWED

def test_review_never_accepts_caller_supplied_status(tmp_path: Path):
    class Ready:
        def audit(self): return type('R',(),{'status':'ready'})()
    class Engagement:
        def project_chapter_locked(self,p,c): return type('P',(),{'content_hash':'a'*64})()
    orchestrator=ChapterProductionOrchestrator(tmp_path, readiness=Ready(), engagement=Engagement())
    orchestrator.start('p',1)
    try:
        orchestrator.record_engagement_review('p',1, {'status':'passed'})
    except ValueError:
        return
    assert False
