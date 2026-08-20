import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.memory.approval import approve_candidate
from creative_os.memory.store import JsonMemoryStore, MemoryStoreError


def _candidate(item_id: str = "exp-001") -> MemoryItem:
    return MemoryItem.new_candidate(
        id=item_id,
        kind=MemoryKind.EXPERIENCE,
        scope=MemoryScope.DOMAIN,
        scope_id="novel",
        title="避免模板化开头",
        content="章节开头不应连续使用统一时间词。",
        evidence=[MemoryEvidence(source_type="review", source_id="run-12")],
        tags={"continuity", "writing"},
    )


def test_store_round_trips_candidate_without_cross_project_leakage(tmp_path):
    first = JsonMemoryStore(tmp_path / "projects" / "甲" / ".creative_os" / "memory")
    second = JsonMemoryStore(tmp_path / "projects" / "乙" / ".creative_os" / "memory")
    candidate = _candidate()

    first.add_candidate(candidate)

    assert first.get(candidate.id) == candidate
    assert second.list() == []


def test_revision_preserves_previous_version(tmp_path):
    store = JsonMemoryStore(tmp_path / "memory")
    original = _candidate()
    store.add_candidate(original)

    revised = store.save_revision(original.id, content="修订内容", actor="tingyu")

    assert revised.version == 2
    assert revised.content == "修订内容"
    assert store.revisions(original.id)[0] == original


def test_store_rejects_duplicate_id_and_invalid_json(tmp_path):
    store = JsonMemoryStore(tmp_path / "memory")
    store.add_candidate(_candidate())

    with pytest.raises(MemoryStoreError):
        store.add_candidate(_candidate())

    (store.items_dir / "broken.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(MemoryStoreError):
        store.list()


def test_revising_active_memory_requires_fresh_approval(tmp_path):
    store = JsonMemoryStore(tmp_path / "memory")
    store.add_candidate(_candidate())
    approve_candidate(store, "exp-001", actor="tingyu", note="first approval")

    revised = store.save_revision("exp-001", content="修改后的规则", actor="tingyu")

    assert revised.status.value == "candidate"
    assert revised.approved_by is None


def test_immutable_add_is_idempotent_only_for_the_equal_item(tmp_path):
    store = JsonMemoryStore(tmp_path / "memory")
    original = _candidate("contract-physical-v0001")

    assert store.add_immutable(original) == original
    assert store.add_immutable(original) == original

    with pytest.raises(MemoryStoreError, match="immutable memory conflict"):
        store.add_immutable(replace(original, content="不能覆盖的另一份内容"))

    assert store.get(original.id) == original


def _race_immutable_adds(root, items):
    stores = tuple(JsonMemoryStore(root) for _ in items)
    barrier = Barrier(len(items))

    def add(index):
        barrier.wait()
        try:
            return stores[index].add_immutable(items[index])
        except Exception as error:  # The assertion below verifies the public error boundary.
            return error

    with ThreadPoolExecutor(max_workers=len(items)) as executor:
        return tuple(executor.map(add, range(len(items))))


def test_concurrent_equal_immutable_writes_are_all_idempotent_without_temp_residue(tmp_path):
    item = _candidate("contract-physical-v0001")

    for round_number in range(12):
        root = tmp_path / f"equal-{round_number}"
        results = _race_immutable_adds(root, (item,) * 8)

        assert results == (item,) * 8
        assert JsonMemoryStore(root).get(item.id) == item
        assert list((root / "items").glob("*.tmp")) == []


def test_concurrent_different_immutable_writes_have_one_winner_and_public_conflicts(tmp_path):
    first = _candidate("contract-physical-v0001")
    second = replace(first, content="同一物理键的冲突内容")

    for round_number in range(12):
        root = tmp_path / f"different-{round_number}"
        items = tuple(first if index % 2 == 0 else second for index in range(8))
        results = _race_immutable_adds(root, items)
        successes = tuple(result for result in results if isinstance(result, MemoryItem))
        errors = tuple(result for result in results if isinstance(result, Exception))

        assert len(successes) == 4
        assert len(errors) == 4
        assert len(set(successes)) == 1
        assert all(isinstance(error, MemoryStoreError) for error in errors)
        assert all("immutable memory conflict" in str(error) for error in errors)
        assert JsonMemoryStore(root).get(first.id) == successes[0]
        assert list((root / "items").glob("*.tmp")) == []


def test_strict_get_rejects_extensions_without_changing_legacy_get(tmp_path):
    store = JsonMemoryStore(tmp_path / "memory")
    item = _candidate()
    store.add_candidate(item)
    path = store.items_dir / f"{item.id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["legacy_extension"] = {"kept_for_legacy_get": True}
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.get(item.id) == item
    with pytest.raises(MemoryStoreError, match="invalid strict memory envelope"):
        store.get_strict(item.id)
    with pytest.raises(MemoryStoreError, match="immutable memory conflict"):
        store.add_immutable(item)
