"""章节前置架构分析的状态与冻结结果存储。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import hashlib
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


def analyze_chapter_preflight(*, chapter_number: int, instruction: str, previous_text: str,
                              current_formal: str = "", current_draft: str = "",
                              source_refs: tuple[str, ...] = (), requested_expert: str | None = None,
                              require_confirmed_combat: bool = False,
                              source_hashes: tuple[str, ...] = (),
                              creative_state: dict | None = None) -> dict:
    """在正文生成前形成独立计划；证据不足时保留未知，不把关键词当作战斗证据。"""
    body = "\n".join(part for part in (previous_text, current_formal, current_draft) if part)
    scene_types = ["continuation"]
    conflicts: list[dict] = []
    resolve_threads: list[str] = []
    plant_threads: list[str] = []
    state_changes: list[str] = []
    unknowns: list[str] = []
    if current_formal or current_draft:
        scene_types.append("revision_or_continuation")
    explicit_action = requested_expert == "combat" or require_confirmed_combat
    if explicit_action:
        scene_types.extend(("conflict", "action"))
        conflicts.append({"type": "action", "basis": "作者或已确认计划明确要求行动编排", "parties": [], "stakes": "待补充"})
        unknowns.append("需要补齐敌我双方、资源状态、行动代价和战后状态。")
    else:
        scene_types.append("plot_progression")
        unknowns.append("尚未确认本章是否存在需要行动链解决的对抗；保持普通写作路径。")
    if "未解决" in body or "待解决" in body or "悬而未决" in body:
        resolve_threads.append("承接前文未解决事项，具体对象需由作者设定或上下文证据确认。")
    if "伏笔" in body or "线索" in body:
        resolve_threads.append("检查前文线索是否在本章回收。")
        plant_threads.append("若本章继续埋设线索，记录其后续回收位置。")
    if not resolve_threads:
        unknowns.append("未发现可安全确认的历史遗留事项，写作时不得擅自补写未证实设定。")
    if creative_state:
        resolve_threads.append("已读取项目冲突与知识基线；仅将其中明确标记为事实的内容作为证据。")
    else:
        unknowns.append("当前项目没有可读取的结构化冲突/知识基线。")
    if current_formal and current_draft:
        state_changes.append("比较正式稿与工作稿，明确本章新增状态变化后再写作。")
    else:
        state_changes.append("记录本章结束时人物、关系、目标和信息状态的变化。")
    source_hashes = source_hashes or tuple(hashlib.sha256(ref.encode("utf-8")).hexdigest() for ref in source_refs)
    return {
        "main_goal": instruction.strip(),
        "scene_types": tuple(dict.fromkeys(scene_types)),
        "conflicts": tuple(conflicts),
        "resolve_threads": tuple(resolve_threads),
        "plant_threads": tuple(plant_threads),
        "state_changes": tuple(state_changes),
        "ending_hook": "待由前置分析根据本章目标和未决事项确定。",
        "combat_plan": conflicts[0] if conflicts else None,
        "unknowns": tuple(unknowns),
        "source_refs": tuple(source_refs),
        "source_hashes": source_hashes,
    }
