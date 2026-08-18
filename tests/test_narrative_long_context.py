import json

from creative_os.domains.novel_state_store import compact_active_snapshots, load_active_snapshots, materialize_active_state
from creative_os.memory.approval import approve_candidate
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.memory.store import JsonMemoryStore


def test_one_hundred_chapters_keep_raw_state_and_bound_context_projection(tmp_path):
    project = tmp_path / "文明升阶"
    store = JsonMemoryStore(project / ".creative_os/memory")
    for chapter in range(1, 101):
        for kind, subject, fields in (
            ("character", "主角", {"known_facts": [f"第{chapter}章事实"]}),
            ("hook", f"hook-{chapter:03d}", {"status": "open", "question": f"第{chapter}章问题"}),
        ):
            item_id = f"state-chapter-{chapter:03d}-{kind}-{subject}"
            item = MemoryItem.new_candidate(
                id=item_id, kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
                scope_id=project.name, title="状态",
                content=json.dumps({
                    "schema_version": 2, "kind": kind, "subject": subject,
                    "fields": fields, "evidence": [],
                }, ensure_ascii=False),
                evidence=[MemoryEvidence("chapter", f"chapter_{chapter:03d}")],
            )
            store.add_candidate(item)
            approve_candidate(store, item_id, actor="tingyu", note="测试批准")

    materialize_active_state(project)
    compacted = compact_active_snapshots(project, max_chars=6000)

    assert len(load_active_snapshots(project)) == 101
    assert len(json.dumps(compacted, ensure_ascii=False)) <= 6000
    assert len(compacted) > 0
