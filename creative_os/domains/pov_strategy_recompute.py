from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from creative_os.domains.pov_strategy_input import assemble_pov_strategy_input
from creative_os.domains.pov_strategy_model import ChapterNeeds
from creative_os.domains.pov_strategy_planner import POVStrategyPlanner
from creative_os.domains.pov_strategy_policy import load_pov_strategy_policy
from creative_os.domains.pov_strategy_review import review_pov_strategy
from creative_os.runtime.pov_strategy_store import POVStrategyAuditStore


@dataclass(frozen=True, slots=True)
class RecomputeResult:
    expired_ids: tuple[str, ...]
    next_candidate_id: str | None
    issues: tuple[str, ...] = ()


def on_chapter_materialized(
    project_root: str | Path,
    chapter_number: int,
    next_needs: ChapterNeeds | None = None,
) -> RecomputeResult:
    store = POVStrategyAuditStore(project_root)
    expired = []
    for record in store.list():
        if record.status not in {"expired", "superseded"} and record.candidate.target_chapter <= chapter_number:
            store.set_status(record.candidate.id, "expired", actor="materialization-hook")
            expired.append(record.candidate.id)
    if next_needs is None:
        _write_pending(project_root, chapter_number + 1, "chapter_needs_unavailable")
        return RecomputeResult(tuple(expired), None)
    try:
        policy = load_pov_strategy_policy(project_root)
        input_value = assemble_pov_strategy_input(project_root, chapter_number + 1, next_needs, policy)
        candidates = POVStrategyPlanner().plan(input_value, policy)
        candidates = __import__("dataclasses").replace(
            candidates, risks=review_pov_strategy(input_value, candidates, policy),
        )
        store.append_candidate(candidates)
        _clear_pending(project_root)
        return RecomputeResult(tuple(expired), candidates.id)
    except (OSError, ValueError, KeyError) as exc:
        # 正文章节已经物化，不回滚；下一次请求必须重新计算。
        issue = f"recompute_failed:{type(exc).__name__}"
        _write_pending(project_root, chapter_number + 1, issue)
        return RecomputeResult(tuple(expired), None, (issue,))


def pending_recompute(project_root) -> dict | None:
    path = _pending_path(project_root)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _write_pending(project_root, target_chapter, reason):
    path = _pending_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"target_chapter": target_chapter, "reason": reason}, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _clear_pending(project_root):
    path = _pending_path(project_root)
    if path.exists():
        path.unlink()


def _pending_path(project_root):
    return Path(project_root) / ".creative_os" / "runtime" / "pov_strategy_pending_recompute.json"
