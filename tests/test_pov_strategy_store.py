import json

import pytest

from creative_os.runtime.pov_strategy_store import POVStrategyAuditStore, POVStrategyStoreError
from tests.pov_strategy_helpers import candidate_set


def test_store_survives_restart_and_detects_tampering(tmp_path):
    store = POVStrategyAuditStore(tmp_path)
    record = store.append_candidate(candidate_set())
    assert record.status == "proposed"
    assert POVStrategyAuditStore(tmp_path).read(candidate_set().id).candidate == candidate_set()
    path = tmp_path / ".creative_os/runtime/pov_strategy/pov-strategy-027.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["input_fingerprint"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(POVStrategyStoreError, match="tampered"):
        POVStrategyAuditStore(tmp_path).read(candidate_set().id)


def test_store_detects_audit_metadata_tampering(tmp_path):
    store = POVStrategyAuditStore(tmp_path)
    store.append_candidate(candidate_set())
    store.set_status(candidate_set().id, "selected", actor="tingyu")
    path = tmp_path / ".creative_os/runtime/pov_strategy/pov-strategy-027.events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[-1])
    event["actor"] = "attacker"
    lines[-1] = json.dumps(event)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(POVStrategyStoreError, match="metadata was tampered"):
        store.read(candidate_set().id)


def test_store_detects_candidate_rewrite_even_with_recomputed_codec_hash(tmp_path):
    from creative_os.domains.pov_strategy_codec import encode_candidate_set
    from dataclasses import replace
    store = POVStrategyAuditStore(tmp_path)
    value = candidate_set()
    store.append_candidate(value)
    path = tmp_path / ".creative_os/runtime/pov_strategy/pov-strategy-027.json"
    path.write_text(encode_candidate_set(replace(value, recommended=replace(value.recommended, rationale="rewritten"))), encoding="utf-8")
    with pytest.raises(POVStrategyStoreError, match="anchor mismatch"):
        store.read(value.id)
