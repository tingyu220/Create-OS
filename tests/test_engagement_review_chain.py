from pathlib import Path
import pytest

from creative_os.domains.reader_engagement_store import ReaderEngagementStore


def _hash(char: str) -> str:
    return char * 64


def test_opening_checkpoint_is_human_authority_and_restarts_exactly(tmp_path: Path):
    store = ReaderEngagementStore(tmp_path)
    payload = {"record_id": "open-1", "project_id": "p", "chapter_number": 1,
               "plan_hash": _hash("a"), "projection_hash": _hash("b"), "ledger_head_hash": _hash("c"),
               "curve_hash": _hash("d"), "contract_hash": _hash("e"), "context_fingerprint": _hash("f"),
               "artifact_hash": _hash("0"), "ruleset_hash": _hash("1"), "actor": "editor", "reason": "追读", "disposition": "approved"}
    record = store.append_opening_checkpoint_review(payload)
    assert ReaderEngagementStore(tmp_path).load_exact("opening_checkpoint", "open-1", record.content_hash) == record
    with pytest.raises(ValueError, match="opening_checkpoint_schema"):
        store.append_opening_checkpoint_review({**payload, "actor": ""})


def test_compiler_only_appends_candidate_not_human_transition(tmp_path: Path):
    store = ReaderEngagementStore(tmp_path)
    record = store.compile_transition_candidate("e1", "absent", "open", _hash("a"), ("exact-evidence",), plan_hash=_hash("b"), projection_hash=_hash("c"))
    assert record.record_type == "expectation_candidate"
    assert not [x for x in store.recover() if x.record_type == "expectation_transition"]
