"""章节前置架构分析的状态与冻结结果存储。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ChapterPlan:
    plan_id: str
    project_id: str
    chapter_number: int
    version: int
    status: str
    main_goal: str = ""
    scene_types: tuple[str, ...] = ()
    conflicts: tuple[dict, ...] = ()
    resolve_threads: tuple[str, ...] = ()
    plant_threads: tuple[str, ...] = ()
    state_changes: tuple[str, ...] = ()
    ending_hook: str = ""
    combat_plan: dict | None = None
    unknowns: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    source_hashes: tuple[str, ...] = ()
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChapterPreflightStore:
    def __init__(self, root: Path):
        self.path = root / ".creative_os" / "chapter-preflight.json"

    def _read(self) -> dict:
        if not self.path.exists():
            return {"plans": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, value: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def create(self, project_id: str, chapter_number: int) -> ChapterPlan:
        plan = ChapterPlan(str(uuid4()), project_id, chapter_number, 1, "queued")
        data = self._read()
        data["plans"][plan.plan_id] = asdict(plan)
        self._write(data)
        return plan

    def update(self, plan_id: str, **changes) -> ChapterPlan:
        data = self._read()
        current = data["plans"][plan_id]
        current.update(changes, updated_at=datetime.now(timezone.utc).isoformat())
        self._write(data)
        return ChapterPlan(**current)

    def get(self, plan_id: str) -> ChapterPlan:
        return ChapterPlan(**self._read()["plans"][plan_id])
