"""按平台进度追赶本地正式稿目标的通用发布循环。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PublicationTarget:
    """一次连续发布目标；目标章包含在范围内。"""

    book_id: str
    work_id: str
    target_chapter: int


class TargetPublicationRunner:
    """只负责逐章调度，平台 DOM 和发布细节仍由 PublicationOrchestrator 处理。"""

    def __init__(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator

    def run_until_target(
        self,
        target: PublicationTarget,
        *,
        platform_chapter: int,
        snapshot_for: Callable[[int], Any],
        checks_for: Callable[[Any], dict[str, bool]],
        target_for: Callable[[Any, int], Any],
    ) -> dict[str, Any]:
        if target.target_chapter <= 0 or platform_chapter < 0:
            raise ValueError("publication_target_invalid")
        start = max(1, platform_chapter + 1)
        results: list[dict[str, Any]] = []
        for chapter_number in range(start, target.target_chapter + 1):
            snapshot = snapshot_for(chapter_number)
            task = self.orchestrator.submit(
                snapshot,
                target_for(snapshot, chapter_number),
                checks=checks_for(snapshot),
                work_id=target.work_id,
            )
            state = self.orchestrator.run(task.operation_id)
            results.append(state)
            if state.get("status") != "published":
                return {
                    "status": state.get("status"),
                    "target_chapter": target.target_chapter,
                    "next_chapter": chapter_number,
                    "results": results,
                }
        return {
            "status": "target_reached",
            "target_chapter": target.target_chapter,
            "next_chapter": target.target_chapter + 1,
            "results": results,
        }


__all__ = ["PublicationTarget", "TargetPublicationRunner"]
