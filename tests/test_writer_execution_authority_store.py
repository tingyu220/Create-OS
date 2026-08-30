from pathlib import Path
import pytest
from creative_os.domains.writer_execution_authority_store import WriterExecutionAuthorityStore

def test_writer_intent_and_local_receipt_are_exact_and_idempotent(tmp_path: Path):
    store=WriterExecutionAuthorityStore(tmp_path)
    intent=store.append_intent({"run_id":"r1","project_id":"p","chapter":1,"request_hash":"a"*64,"context_fingerprint":"b"*64,"idempotency_key":"k1"})
    receipt=store.append_local_receipt("r1", {"artifact_hash":"c"*64,"request_hash":"a"*64})
    assert store.load_exact("intent", "r1", intent["content_hash"])["run_id"] == "r1"
    assert store.append_local_receipt("r1", {"artifact_hash":"c"*64,"request_hash":"a"*64}) == receipt

def test_receipt_requires_local_mac_and_binding(tmp_path: Path):
    store=WriterExecutionAuthorityStore(tmp_path)
    intent=store.append_intent({"run_id":"r1","project_id":"p","chapter":1,"request_hash":"a"*64,"context_fingerprint":"b"*64,"idempotency_key":"k1"})
    receipt=store.append_local_receipt("r1", {"artifact_hash":"c"*64,"request_hash":"a"*64,"provider_metadata":{"request_id":"q1"}})
    assert receipt["type"] == "receipt"
    assert len(receipt["payload"]["local_mac"]) == 64
    with pytest.raises(ValueError, match="receipt_binding"):
        store.append_local_receipt("r2", {"artifact_hash":"c"*64,"request_hash":"a"*64})

def test_reconciliation_requires_actor_reason_and_is_restart_exact(tmp_path: Path):
    store=WriterExecutionAuthorityStore(tmp_path)
    store.append_intent({"run_id":"r1","project_id":"p","chapter":1,"request_hash":"a"*64,"context_fingerprint":"b"*64,"idempotency_key":"k1"})
    store.append_local_receipt("r1", {"artifact_hash":"c"*64,"request_hash":"a"*64})
    decision=store.append_reconciliation_decision("r1", {"decision_id":"d1","actor":"tingyu","reason":"核对外部结果","provider_request_id":"q1","provider_result_hash":"d"*64})
    assert WriterExecutionAuthorityStore(tmp_path).load_exact("reconciliation", "d1", decision["content_hash"])["actor"] == "tingyu"
