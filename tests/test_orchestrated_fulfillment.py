from pathlib import Path
from creative_os.domains.contract_fulfillment_reviewer import ContractFulfillmentReviewer

def test_reviewer_appends_exact_fake_artifact_evidence_and_reopens(tmp_path: Path):
    reviewer=ContractFulfillmentReviewer(tmp_path)
    first=reviewer.append_verified_records({"contract_hash":"a"*64,"artifact_hash":"b"*64,"evidence":[{"field_path":"chapter","source_id":"fake:1","source_version":"v1","source_hash":"c"*64}]})
    assert first[0]["artifact_hash"] == "b"*64
    assert ContractFulfillmentReviewer(tmp_path).active("a"*64) == first

def test_reviewer_rejects_wrong_artifact_hash(tmp_path: Path):
    reviewer=ContractFulfillmentReviewer(tmp_path)
    try: reviewer.append_verified_records({"contract_hash":"a"*64,"artifact_hash":"bad","evidence":[]})
    except ValueError as error: assert "artifact_hash" in str(error)
    else: assert False
