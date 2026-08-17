from creative_os.memory.approval import approve_candidate
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.memory.retriever import MemoryQuery, MemoryRetriever
from creative_os.memory.store import JsonMemoryStore


def _add(store: JsonMemoryStore, item_id: str, scope: MemoryScope, scope_id: str, *, active: bool = True, applicability=()):
    store.add_candidate(
        MemoryItem.new_candidate(
            id=item_id,
            kind=MemoryKind.EXPERIENCE,
            scope=scope,
            scope_id=scope_id,
            title=item_id,
            content=f"content for {item_id}",
            evidence=[MemoryEvidence(source_type="review", source_id=f"source-{item_id}")],
            applicability=applicability,
            tags={"continuity", "writing"},
            confidence=0.8,
        )
    )
    if active:
        approve_candidate(store, item_id, actor="tingyu", note="test")


def test_retriever_excludes_candidates_and_other_project_memory(tmp_path):
    store = JsonMemoryStore(tmp_path / "memory")
    _add(store, "project-a-decision", MemoryScope.PROJECT, "project-a")
    _add(store, "novel-method", MemoryScope.DOMAIN, "novel")
    _add(store, "user-style", MemoryScope.USER, "tingyu")
    _add(store, "project-b-decision", MemoryScope.PROJECT, "project-b")
    _add(store, "candidate-rule", MemoryScope.DOMAIN, "novel", active=False)

    result = MemoryRetriever().retrieve(
        MemoryQuery(
            task_id="chapter-003",
            project_id="project-a",
            user_id="tingyu",
            domain="novel",
            task_kind="writing",
            tags={"continuity"},
        ),
        [store],
        limit=8,
    )

    assert [item.id for item in result.items] == ["project-a-decision", "user-style", "novel-method"]
    assert "candidate-rule" not in result.reasons
    assert "project-b-decision" not in result.reasons
    assert "scope:project" in result.reasons["project-a-decision"]


def test_retriever_filters_inapplicable_task_kind(tmp_path):
    store = JsonMemoryStore(tmp_path / "memory")
    _add(store, "review-only", MemoryScope.DOMAIN, "novel", applicability=("review",))

    result = MemoryRetriever().retrieve(
        MemoryQuery("chapter-003", "project-a", "tingyu", "novel", "writing", {"continuity"}),
        [store],
    )

    assert result.items == []
