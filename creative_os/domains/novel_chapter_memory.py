from __future__ import annotations

import re
from pathlib import Path

from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.memory.store import JsonMemoryStore
from creative_os.domains.novel_state_model import build_state_changes


def compile_chapter_candidates(project_root: str | Path, chapter_number: int) -> list[MemoryItem]:
    root = Path(project_root)
    source = root / "production" / "final_chapters" / f"chapter_{chapter_number:03d}.md"
    text = source.read_text(encoding="utf-8")
    paragraphs = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    summary = " ".join([*paragraphs[:2], *paragraphs[-2:]])[:1200]
    characters = _characters(root, text)
    evidence = [MemoryEvidence(source_type="chapter", source_id=source.relative_to(root).as_posix())]
    items = [
        _candidate(root, chapter_number, "summary", "章节摘要", summary, evidence, {"chapter_summary", f"chapter_{chapter_number:03d}"}),
        _candidate(root, chapter_number, "characters", "人物状态", f"本章出场人物：{'、'.join(characters) or '待人工补充'}。", evidence, {"character_state", f"chapter_{chapter_number:03d}"}),
        _candidate(root, chapter_number, "events", "关键事件", summary, evidence, {"event", f"chapter_{chapter_number:03d}"}),
        _candidate(root, chapter_number, "hooks", "伏笔与待续问题", _hooks(paragraphs), evidence, {"hook", f"chapter_{chapter_number:03d}"}),
    ]
    return items


def save_chapter_candidates(project_root: str | Path, chapter_number: int) -> list[MemoryItem]:
    root = Path(project_root)
    store = JsonMemoryStore(root / ".creative_os" / "memory")
    saved: list[MemoryItem] = []
    for item in compile_chapter_candidates(root, chapter_number):
        try:
            store.add_candidate(item)
        except ValueError:
            item = store.get(item.id)
        saved.append(item)
    evidence = [MemoryEvidence(source_type="chapter", source_id=f"production/final_chapters/chapter_{chapter_number:03d}.md")]
    for change in build_state_changes(root, chapter_number):
        item = MemoryItem.new_candidate(
            id=f"state-{change.id}", kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
            scope_id=root.name, title=f"第 {chapter_number} 章状态：{change.kind}", content=change.to_json(),
            evidence=evidence, applicability=("writing",), tags={"novel", "state", change.kind}, confidence=0.6,
        )
        try:
            store.add_candidate(item)
        except ValueError:
            item = store.get(item.id)
        saved.append(item)
    # POV 候选只在状态物化完成后失效；延迟导入避免领域初始化环。
    from creative_os.domains.pov_strategy_recompute import on_chapter_materialized
    on_chapter_materialized(root, chapter_number)
    return saved


def _candidate(root: Path, chapter: int, suffix: str, title: str, content: str, evidence: list[MemoryEvidence], tags: set[str]) -> MemoryItem:
    return MemoryItem.new_candidate(
        id=f"chapter-{chapter:03d}-{suffix}", kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
        scope_id=root.name, title=f"第 {chapter} 章{title}", content=content, evidence=evidence,
        applicability=("writing",), tags={"novel", *tags}, confidence=0.7,
    )


def _characters(root: Path, text: str) -> list[str]:
    baseline = root / ".creative_os" / "import" / "active_baseline.json"
    if not baseline.exists():
        return []
    import json
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    return [item["title"] for item in payload.get("characters", []) if item.get("title") in text]


def _hooks(paragraphs: list[str]) -> str:
    questions = [sentence.strip() for sentence in re.split(r"[。！？]", " ".join(paragraphs)) if "？" in sentence]
    return "；".join(questions[-3:]) or "待人工确认本章新增伏笔。"
