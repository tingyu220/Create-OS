from pathlib import Path
import pytest
from creative_os.domains.state_change_approval import StateChangeApprovalService

def test_state_materialization_requires_human_approved_decision(tmp_path: Path):
    service=StateChangeApprovalService(tmp_path)
    candidate={"candidate_id":"c1","final_hash":"a"*64,"fulfillment_hash":"b"*64}
    with pytest.raises(ValueError, match="approval_required"):
        service.materialize(candidate)
