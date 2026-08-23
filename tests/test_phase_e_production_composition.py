from tests.fakes.fake_chapter_writer import FakeChapterWriter
from creative_os.domains.chapter_production_composition import ProductionCompositionRoot
from creative_os.domains.chapter_production_orchestrator import ChapterProductionOrchestrator
from creative_os.domains.state_change_approval import StateChangeApprovalStore
import json, pytest

class Ready:
    def audit(self): return type('R',(),{'status':'ready'})()
class Engagement:
    def project_chapter_locked(self,p,c): return type('P',(),{'content_hash':'a'*64})()
    def append_engagement_review(self,p): return {'record_id':p['review_id'],'content_hash':'b'*64}
    def load_exact(self,*args): return {'status':'passed'}

def test_production_composition_rebuilds_each_chapter_and_materializes(tmp_path):
    writer=FakeChapterWriter(tmp_path)
    root=ProductionCompositionRoot(tmp_path,writer,Ready(),Engagement())
    results=[root.run_chapter('p',chapter) for chapter in range(1,11)]
    assert len(results)==10 and writer.calls==10
    assert all(receipt['materialized'] for _,receipt in results)
    assert all(v.state.value=='fulfillment_recorded' for v,_ in results)

def test_production_composition_resume_is_idempotent(tmp_path):
    writer=FakeChapterWriter(tmp_path); root=ProductionCompositionRoot(tmp_path,writer,Ready(),Engagement())
    first=root.run_chapter('p',1); second=root.run_chapter('p',1)
    assert writer.calls==1 and first[0]==second[0] and first[1]==second[1]

def test_real_composition_recovers_after_interruption_and_reopen(tmp_path, monkeypatch):
    writer=FakeChapterWriter(tmp_path); root=ProductionCompositionRoot(tmp_path,writer,Ready(),Engagement())
    original=ChapterProductionOrchestrator.record_fulfillment; interrupted={'done':False}
    def fail_once(self,*args,**kwargs):
        if not interrupted['done']:
            interrupted['done']=True; raise RuntimeError('simulated interruption')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(ChapterProductionOrchestrator,'record_fulfillment',fail_once)
    with pytest.raises(RuntimeError): root.run_chapter('p',3)
    result=root.run_chapter('p',3)
    assert result[0].state.value=='fulfillment_recorded'

def test_real_composition_tampered_state_store_has_zero_side_effect(tmp_path):
    writer=FakeChapterWriter(tmp_path); root=ProductionCompositionRoot(tmp_path,writer,Ready(),Engagement())
    root.run_chapter('p',4)
    head=tmp_path/'.creative_os'/'state-change'/'head.json'; data=json.loads(head.read_text()); data['count']=999; head.write_text(json.dumps(data)+'\n')
    with pytest.raises(ValueError,match='tampered'): StateChangeApprovalStore(tmp_path).recover()

def test_real_composition_rejects_bad_artifact_before_checkpoint(tmp_path):
    class BadWriter(FakeChapterWriter):
        def prepare(self, chapter):
            artifact=super().prepare(chapter)
            return type(artifact)(artifact.metadata,artifact.structured_evidence,'bad')
    writer=BadWriter(tmp_path); root=ProductionCompositionRoot(tmp_path,writer,Ready(),Engagement())
    with pytest.raises(ValueError,match='artifact_hash'): root.run_chapter('p',5)
