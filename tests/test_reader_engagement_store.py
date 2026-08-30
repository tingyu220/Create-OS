import pytest

from creative_os.domains.reader_engagement_store import ReaderEngagementStore


def test_store_append_plan_candidate_and_exact_restart(tmp_path):
    store = ReaderEngagementStore(tmp_path)
    record = store.append_plan_candidate({"id": "plan-1", "content_hash": "a" * 64})
    reopened = ReaderEngagementStore(tmp_path)
    assert reopened.load_exact("plan", record.record_id, record.content_hash) == record


def test_store_rejects_unknown_record_schema(tmp_path):
    store = ReaderEngagementStore(tmp_path)
    with pytest.raises(ValueError, match="schema"):
        store.append_raw("future_record", {"schema_version": 99})


def test_store_detects_tampered_record_chain_after_restart(tmp_path):
    store = ReaderEngagementStore(tmp_path)
    store.append_plan_candidate({"id": "plan-1", "content_hash": "a" * 64})
    records = store.records_path.read_bytes().replace(b"plan-1", b"plan-x")
    store.records_path.write_bytes(records)
    with pytest.raises(ValueError, match="tampered"):
        ReaderEngagementStore(tmp_path).recover()


def test_store_second_append_preserves_previous_entry_hash(tmp_path):
    store = ReaderEngagementStore(tmp_path)
    first = store.append_plan_candidate({"id": "plan-1", "content_hash": "a" * 64})
    second = store.append_plan_candidate({"id": "plan-2", "content_hash": "b" * 64})
    assert [item.record_id for item in store.recover()] == [first.record_id, second.record_id]


def test_store_persists_head_and_recovers_prepared_journal(tmp_path):
    store = ReaderEngagementStore(tmp_path)
    record = {"id": "plan-1", "content_hash": "a" * 64}
    store.append_plan_candidate(record)
    assert store.head_path.exists()
    store.journal_path.write_text('{"state":"prepared"}', encoding="utf-8")
    with pytest.raises(ValueError, match="journal"):
        ReaderEngagementStore(tmp_path).recover()


def test_store_rejects_head_drift(tmp_path):
    store = ReaderEngagementStore(tmp_path)
    store.append_plan_candidate({"id": "plan-1", "content_hash": "a" * 64})
    store.head_path.write_text('{"count":1,"head_hash":"' + 'f' * 64 + '"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="tampered_records"):
        ReaderEngagementStore(tmp_path).recover()
