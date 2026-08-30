import json
import pytest
from creative_os.domains.target_chapter_grouping import TargetChapterGroupingCandidate, encode_grouping
from creative_os.runtime.target_chapter_grouping_store import TargetGroupingStore

def test_grouping_candidate_is_hashed_and_encoded():
    value=TargetChapterGroupingCandidate("m",1,(1,2),((5,1),(5,2)),3800,("hook",))
    payload=json.loads(encode_grouping(value))
    assert payload["candidate_hash"] == value.candidate_hash
    assert payload["schema_version"] == 1


def test_grouping_store_appends_revision_without_overwriting_history(tmp_path):
    store = TargetGroupingStore(tmp_path)
    original = TargetChapterGroupingCandidate(
        "migration-civilization-v2",
        5,
        (1, 2, 3),
        tuple((5, paragraph) for paragraph in range(1, 43)),
        3012,
        ("通路检验仍在进行",),
    )
    revised = TargetChapterGroupingCandidate(
        "migration-civilization-v2",
        5,
        (1, 2, 3, 4),
        tuple((5, paragraph) for paragraph in range(1, 63)),
        4800,
        ("他不想去敲。",),
    )

    store.append(original)
    revision_hash = store.append_revision(
        revised,
        replaces_candidate_hash=original.candidate_hash,
        reason="补齐目标第5章的选择、代价与结果闭环",
    )

    rows = [json.loads(line) for line in store.records.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["candidate_hash"] == original.candidate_hash
    assert rows[1]["kind"] == "candidate_revision"
    assert rows[1]["candidate_hash"] == revised.candidate_hash
    assert rows[1]["replaces_candidate_hash"] == original.candidate_hash
    assert store.load_current("migration-civilization-v2", 5).candidate_hash == revision_hash


def test_grouping_store_rejects_revision_from_non_current_candidate(tmp_path):
    store = TargetGroupingStore(tmp_path)
    original = TargetChapterGroupingCandidate("m", 5, (1,), ((5, 1),), 100, ("hook",))
    revised = TargetChapterGroupingCandidate("m", 5, (1, 2), ((5, 1), (5, 2)), 200, ("hook-2",))
    store.append(original)

    with pytest.raises(ValueError, match="grouping_revision_base_mismatch"):
        store.append_revision(revised, replaces_candidate_hash="0" * 64, reason="错误基线")


def test_grouping_store_lists_only_current_versions_in_target_order(tmp_path):
    store = TargetGroupingStore(tmp_path)
    first = TargetChapterGroupingCandidate("m", 5, (1,), ((5, 1),), 100, ("hook",))
    second = TargetChapterGroupingCandidate("m", 6, (2,), ((5, 2),), 100, ("hook-2",))
    revised = TargetChapterGroupingCandidate("m", 5, (1, 3), ((5, 1), (5, 3)), 200, ("hook-3",))
    store.append(first)
    store.append(second)
    store.append_revision(revised, replaces_candidate_hash=first.candidate_hash, reason="补齐闭环")

    assert store.list_current("m") == (revised, second)
