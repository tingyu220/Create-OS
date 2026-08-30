import json

import pytest

from creative_os.domains.novel_state_store import (
    StateMergeConflictError,
    compact_active_snapshots,
    load_active_snapshots,
    materialize_active_state,
)
from creative_os.memory.approval import approve_candidate
from creative_os.memory.approval import archive_memory
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.memory.store import JsonMemoryStore


def test_approved_state_change_creates_history_and_current_snapshot(tmp_path):
    project = tmp_path / "文明升阶"
    store = JsonMemoryStore(project / ".creative_os/memory")
    item = MemoryItem.new_candidate(
        id="state-chapter-003-location-龙渊", kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
        scope_id="文明升阶", title="地点状态", content=json.dumps({"schema_version": 2, "kind": "location", "subject": "龙渊", "fields": {"last_seen": "龙渊"}, "evidence": []}),
        evidence=[MemoryEvidence("chapter", "chapter_003")],
    )
    store.add_candidate(item)
    approve_candidate(store, item.id, actor="tingyu", note="批准")

    materialize_active_state(project)

    snapshots = load_active_snapshots(project)
    assert snapshots[0]["subject"] == "龙渊"
    assert (project / ".creative_os/state/changes/state-chapter-003-location-龙渊.json").exists()


def test_new_state_change_merges_fields_for_the_same_entity(tmp_path):
    project = tmp_path / "文明升阶"
    store = JsonMemoryStore(project / ".creative_os/memory")
    for item_id, fields in [("state-chapter-003-character-林子轩", {"known_facts": ["D-7"]}), ("state-chapter-004-character-林子轩", {"location": "龙渊"})]:
        item = MemoryItem.new_candidate(id=item_id, kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT, scope_id="文明升阶", title="人物状态", content=json.dumps({"schema_version": 2, "kind": "character", "subject": "林子轩", "fields": fields, "evidence": []}), evidence=[MemoryEvidence("chapter", item_id)])
        store.add_candidate(item)
        approve_candidate(store, item_id, actor="tingyu", note="批准")

    materialize_active_state(project)

    snapshot = next(item for item in load_active_snapshots(project) if item["subject"] == "林子轩")
    assert snapshot["fields"] == {"known_facts": ["D-7"], "location": "龙渊"}


def test_archived_state_is_not_returned_as_an_active_snapshot(tmp_path):
    project = tmp_path / "文明升阶"
    store = JsonMemoryStore(project / ".creative_os/memory")
    item = MemoryItem.new_candidate(id="state-chapter-003-event-main", kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT, scope_id="文明升阶", title="事件状态", content=json.dumps({"schema_version": 2, "kind": "event", "subject": "旧事件", "fields": {}, "evidence": []}), evidence=[MemoryEvidence("chapter", "chapter_003")])
    store.add_candidate(item)
    approve_candidate(store, item.id, actor="tingyu", note="批准")
    materialize_active_state(project)
    archive_memory(store, item.id, actor="tingyu", note="被修订状态替代")

    assert load_active_snapshots(project) == []


def test_additive_fields_append_and_deduplicate_across_chapters(tmp_path):
    project = tmp_path / "文明升阶"
    store = JsonMemoryStore(project / ".creative_os/memory")
    for item_id, facts in [
        ("state-chapter-003-character-林子轩", ["D-7", "龙渊" ]),
        ("state-chapter-004-character-林子轩", ["龙渊", "九年窗口"]),
    ]:
        item = MemoryItem.new_candidate(
            id=item_id, kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
            scope_id=project.name, title="人物状态",
            content=json.dumps({
                "schema_version": 2, "kind": "character", "subject": "林子轩",
                "fields": {"known_facts": facts}, "evidence": [],
            }, ensure_ascii=False),
            evidence=[MemoryEvidence("chapter", item_id)],
        )
        store.add_candidate(item)
        approve_candidate(store, item_id, actor="tingyu", note="批准")

    materialize_active_state(project)

    snapshot = next(item for item in load_active_snapshots(project) if item["subject"] == "林子轩")
    assert snapshot["fields"]["known_facts"] == ["D-7", "龙渊", "九年窗口"]


def test_same_chapter_conflicting_scalar_state_requires_manual_resolution(tmp_path):
    project = tmp_path / "文明升阶"
    store = JsonMemoryStore(project / ".creative_os/memory")
    for item_id, location in [
        ("state-chapter-004-character-林子轩-a", "安全宿舍"),
        ("state-chapter-004-character-林子轩-b", "核心解码室"),
    ]:
        item = MemoryItem.new_candidate(
            id=item_id, kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
            scope_id=project.name, title="人物状态",
            content=json.dumps({
                "schema_version": 2, "kind": "character", "subject": "林子轩",
                "fields": {"location": location}, "evidence": [],
            }, ensure_ascii=False),
            evidence=[MemoryEvidence("chapter", item_id)],
        )
        store.add_candidate(item)
        approve_candidate(store, item_id, actor="tingyu", note="批准")

    with pytest.raises(StateMergeConflictError, match="location"):
        materialize_active_state(project)


def test_materialization_is_idempotent_for_same_active_memory(tmp_path):
    project = tmp_path / "文明升阶"
    store = JsonMemoryStore(project / ".creative_os/memory")
    item_id = "state-chapter-003-character-林子轩"
    item = MemoryItem.new_candidate(
        id=item_id, kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
        scope_id=project.name, title="人物状态",
        content=json.dumps({
            "schema_version": 2, "kind": "character", "subject": "林子轩",
            "fields": {"known_facts": ["D-7"]}, "evidence": [],
        }, ensure_ascii=False),
        evidence=[MemoryEvidence("chapter", item_id)],
    )
    store.add_candidate(item)
    approve_candidate(store, item_id, actor="tingyu", note="批准")

    materialize_active_state(project)
    snapshot_path = project / ".creative_os/state/snapshots/character/林子轩.json"
    first = snapshot_path.read_text(encoding="utf-8")
    materialize_active_state(project)

    assert snapshot_path.read_text(encoding="utf-8") == first


def test_compact_active_snapshots_bounds_context_projection_without_mutating_snapshot(tmp_path):
    project = tmp_path / "文明升阶"
    store = JsonMemoryStore(project / ".creative_os/memory")
    item_id = "state-chapter-003-character-林子轩"
    facts = [f"事实{i}" for i in range(20)]
    item = MemoryItem.new_candidate(
        id=item_id, kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
        scope_id=project.name, title="人物状态",
        content=json.dumps({
            "schema_version": 2, "kind": "character", "subject": "林子轩",
            "fields": {"known_facts": facts}, "evidence": [],
        }, ensure_ascii=False),
        evidence=[MemoryEvidence("chapter", item_id)],
    )
    store.add_candidate(item)
    approve_candidate(store, item_id, actor="tingyu", note="批准")
    materialize_active_state(project)
    original = load_active_snapshots(project)[0]["fields"]["known_facts"]

    compacted = compact_active_snapshots(project, max_chars=1000)

    assert compacted[0]["fields"]["known_facts"][-1] == "还有12项"
    assert load_active_snapshots(project)[0]["fields"]["known_facts"] == original
