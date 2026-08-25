from creative_os.domains.pov_strategy_recompute import on_chapter_materialized, pending_recompute
from creative_os.runtime.pov_strategy_store import POVStrategyAuditStore
from tests.pov_strategy_helpers import candidate_set


def test_materialization_expires_old_candidate_idempotently(tmp_path):
    store = POVStrategyAuditStore(tmp_path)
    store.append_candidate(candidate_set())
    first = on_chapter_materialized(tmp_path, 27)
    second = on_chapter_materialized(tmp_path, 27)
    assert first.expired_ids == ("pov-strategy-027",)
    assert second.expired_ids == ()
    assert store.read("pov-strategy-027").status == "expired"
    assert pending_recompute(tmp_path) == {"target_chapter": 28, "reason": "chapter_needs_unavailable"}
