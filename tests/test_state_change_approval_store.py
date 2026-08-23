import json
import pytest
from creative_os.domains.state_change_approval import StateChangeApprovalService, StateChangeApprovalStore

def test_approval_materialization_survives_restart_and_binds_baseline(tmp_path):
    c={'candidate_id':'c1','state':{'hero':'changed'}}
    StateChangeApprovalService(tmp_path).approve(c,'tingyu','确认状态变化')
    receipt=StateChangeApprovalService(tmp_path).materialize(c)
    assert receipt['materialized'] is True and receipt['next_baseline_hash']
    assert StateChangeApprovalStore(tmp_path).recover()[-1]['record_id']=='materialization:c1'

def test_materialize_rejects_unapproved_or_drifted_candidate(tmp_path):
    c={'candidate_id':'c1','state':'a'}
    service=StateChangeApprovalService(tmp_path)
    with pytest.raises(ValueError,match='approval_required'): service.materialize(c)
    service.approve(c,'a','r')
    with pytest.raises(ValueError,match='approval_required'): service.materialize({'candidate_id':'c1','state':'b'})

def test_store_rejects_tampered_head_and_is_idempotent(tmp_path):
    c={'candidate_id':'c1'}; s=StateChangeApprovalService(tmp_path); first=s.approve(c,'a','r'); assert s.approve(c,'a','r')==first
    head=tmp_path/'.creative_os'/'state-change'/'head.json'; data=json.loads(head.read_text()); data['count']=99; head.write_text(json.dumps(data)+'\n')
    with pytest.raises(ValueError,match='tampered'): StateChangeApprovalStore(tmp_path).recover()
