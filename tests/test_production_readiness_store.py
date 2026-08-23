from pathlib import Path
import pytest
from creative_os.domains.production_readiness_store import ProductionReadinessStore

def test_readiness_store_append_exact_restart_and_idempotency(tmp_path: Path):
    store=ProductionReadinessStore(tmp_path)
    payload={"audit_hash":"a"*64,"status":"ready","ruleset_hash":"b"*64}
    first=store.append_audit(payload)
    assert ProductionReadinessStore(tmp_path).load_exact("audit", first["record_id"], first["content_hash"]) == payload
    assert store.append_audit(payload)==first

def test_readiness_approval_requires_exact_audit_and_human_binding(tmp_path: Path):
    store=ProductionReadinessStore(tmp_path)
    audit=store.append_audit({"audit_hash":"a"*64,"status":"ready","ruleset_hash":"b"*64})
    approval=store.append_approval({"audit_record_id":audit["record_id"],"audit_hash":audit["content_hash"],"actor":"tingyu","reason":"批准","decision":"approved"})
    assert store.load_exact("approval", approval["record_id"], approval["content_hash"])["actor"] == "tingyu"
    with pytest.raises(ValueError, match="stale"):
        store.append_approval({"audit_record_id":audit["record_id"],"audit_hash":"c"*64,"actor":"tingyu","reason":"批准","decision":"approved"})

def test_readiness_store_rejects_tamper(tmp_path: Path):
    store=ProductionReadinessStore(tmp_path)
    store.append_audit({"audit_hash":"a"*64,"status":"ready","ruleset_hash":"b"*64})
    store.records_path.write_text(store.records_path.read_text(encoding='utf-8').replace('"sequence":1','"sequence":2'),encoding='utf-8')
    with pytest.raises(ValueError, match="tampered"):
        store.recover()
