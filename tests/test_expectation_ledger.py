import pytest

from creative_os.domains.reader_engagement_store import ReaderEngagementStore


def test_establish_absent_to_open_is_idempotent_and_conflict_checked(tmp_path):
    store = ReaderEngagementStore(tmp_path)
    candidate = {
        "expectation_id": "exp-1",
        "from_state": "absent",
        "to_state": "open",
        "previous_record_hash": None,
        "content_hash": "a" * 64,
        "evidence": (),
    }
    first = store.append_expectation_candidate(candidate)
    assert store.append_expectation_candidate(candidate) == first
    with pytest.raises(ValueError, match="record_id_conflict"):
        store.append_expectation_candidate({**candidate, "content_hash": "b" * 64})


def test_non_establish_transition_cannot_target_absent_expectation(tmp_path):
    store = ReaderEngagementStore(tmp_path)
    with pytest.raises(ValueError, match="missing"):
        store.append_expectation_candidate({
            "expectation_id": "missing", "from_state": "open", "to_state": "paid",
            "content_hash": "a" * 64, "evidence": (),
        })
