from creative_os.memory.evaluation import MemoryUsageRecord, record_usage, summarize_effects
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope, MemoryStatus
from creative_os.memory.store import JsonMemoryStore


def test_usage_record_links_memory_to_review_outcome_without_changing_status(tmp_path):
    store = JsonMemoryStore(tmp_path / "memory")
    candidate = MemoryItem.new_candidate(
        id="exp-001",
        kind=MemoryKind.EXPERIENCE,
        scope=MemoryScope.DOMAIN,
        scope_id="novel",
        title="自然转场",
        content="转场必须服务情绪和动作。",
        evidence=[MemoryEvidence(source_type="review", source_id="review-1")],
    )
    store.add_candidate(candidate)
    log_path = tmp_path / "memory" / "usage.jsonl"

    record_usage(
        log_path,
        MemoryUsageRecord(
            run_id="run-1",
            task_id="chapter-003",
            context_fingerprint="fingerprint",
            memory_ids=("exp-001",),
            issues_before=("hard_transition", "time_word_opener"),
            issues_after=("time_word_opener",),
            human_rating=4,
        ),
    )
    effects = summarize_effects(log_path)

    assert effects["exp-001"].uses == 1
    assert effects["exp-001"].issue_delta == -1
    assert effects["exp-001"].average_human_rating == 4.0
    assert store.get("exp-001").status == MemoryStatus.CANDIDATE
