from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from creative_os.foundation.knowledge import KnowledgeItem
from creative_os.foundation.state import ProjectState
from creative_os.foundation.task import Task
from creative_os.memory.context_compiler import CompileRequest, CompiledContext, ContextCompiler
from creative_os.memory.retriever import MemoryQuery, MemoryRetrievalResult, MemoryRetriever
from creative_os.memory.store import JsonMemoryStore
from creative_os.domains.narrative_decision import NarrativeDecision
from creative_os.domains.narrative_memory import load_active_narrative_decision
from creative_os.domains.novel_state_store import compact_active_snapshots


class ContinuationBlockedError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ContinuationTask:
    chapter_number: int
    previous_chapter: int
    narrative_goal: str
    required_facts: list[str]
    forbidden_contradictions: list[str]
    open_hooks: list[str]
    last_chapter_ending: str
    character_states: list[str]
    target_chinese_chars: int
    min_chinese_chars: int
    narrative_contract: NarrativeDecision | None = None


def build_next_chapter(
    project_root: str | Path,
    *,
    target_chinese_chars: int | None = None,
    require_narrative_contract: bool = False,
) -> tuple[ContinuationTask, CompiledContext]:
    root = Path(project_root)
    _ensure_conflicts_resolved(root)
    chapters = _load_canon_chapters(root)
    if not chapters:
        raise ContinuationBlockedError("no canonical chapter is available for continuation")
    last_number, last_path, last_text = chapters[-1]
    import_root = root / ".creative_os" / "import"
    active_baseline = import_root / "active_baseline.json"
    baseline = _read_json(active_baseline if active_baseline.exists() else import_root / "baseline.json")
    continuation = _continuation_task(last_number, last_text, baseline, target_chinese_chars)
    narrative_contract = load_active_narrative_decision(root, continuation.chapter_number)
    if require_narrative_contract and narrative_contract is None:
        raise ContinuationBlockedError(
            f"missing approved narrative decision for chapter {continuation.chapter_number}"
        )
    if narrative_contract is not None:
        contract = narrative_contract.chapter_contract
        continuation = replace(
            continuation,
            target_chinese_chars=contract.target_chinese_chars,
            min_chinese_chars=max(1000, int(contract.target_chinese_chars * 0.75)),
            forbidden_contradictions=list(
                dict.fromkeys([*continuation.forbidden_contradictions, *contract.forbidden])
            ),
        )
    continuation = replace(continuation, narrative_contract=narrative_contract)
    task = Task(
        id=f"chapter-{continuation.chapter_number:03d}",
        title=f"续写第 {continuation.chapter_number} 章",
        kind="writing",
        domain="novel",
        goal=continuation.narrative_goal,
        tags={"continuation", "novel"},
    )
    state = ProjectState("Draft", task.id, task.goal, "novel")
    memory = MemoryRetriever().retrieve(
        MemoryQuery(task_id=task.id, project_id=root.name, user_id="local", domain="novel", task_kind="writing", tags={"novel", "continuation"}),
        [JsonMemoryStore(root / ".creative_os" / "memory")],
        limit=16,
    )
    retained_memory = [item for item in memory.items if not _is_legacy_state_memory(item)]
    memory = MemoryRetrievalResult(
        items=retained_memory,
        reasons={item.id: memory.reasons[item.id] for item in retained_memory},
    )
    knowledge = [
        KnowledgeItem(
            id=last_path.relative_to(root).as_posix(),
            kind="previous_chapter",
            title=f"第 {last_number} 章收束",
            body=_compact(last_text, 1800),
            tags={"continuation", "previous_chapter"},
        ),
        *_baseline_knowledge(baseline),
        *[
            KnowledgeItem(
                id=f"state:{snapshot['kind']}:{snapshot['subject']}",
                kind="active_state_snapshot",
                title=f"当前{snapshot['kind']}状态：{snapshot['subject']}",
                body=json.dumps(snapshot.get("fields", {}), ensure_ascii=False),
                tags={"state", snapshot["kind"], "continuation"},
            )
            for snapshot in compact_active_snapshots(root, max_chars=6000)
        ],
        *(
            [
                KnowledgeItem(
                    id=f"narrative:chapter:{narrative_contract.chapter:03d}",
                    kind="narrative_decision",
                    title=f"第 {narrative_contract.chapter} 章叙事合同",
                    body=narrative_contract.to_json(),
                    tags={"narrative", "narrative_decision", "continuation"},
                )
            ]
            if narrative_contract is not None
            else []
        ),
    ]
    compiled = ContextCompiler().compile(
        CompileRequest(
            user_input="继续当前小说，不改写既有正式正文或核心设定。",
            task=task,
            state=state,
            knowledge=knowledge,
            memory=memory,
            domain_rules=["character_consistency", "world_consistency", "continuity"],
        ),
        max_chars=20000,
    )
    return continuation, compiled


def _continuation_task(
    last_number: int,
    last_text: str,
    baseline: dict[str, Any],
    target_chinese_chars: int | None,
) -> ContinuationTask:
    next_number = last_number + 1
    milestone = _chapter_outline_goal(baseline, next_number) or _first_content(
        baseline, "plot_milestones", "推进主线并延续上一章结果"
    )
    world = _contents(baseline, "world_rules")
    hooks = _contents(baseline, "hooks")
    characters = _contents(baseline, "characters")
    target = target_chinese_chars or _target_chinese_chars(milestone)
    if target < 1000:
        raise ValueError("target_chinese_chars must be at least 1000")
    return ContinuationTask(
        chapter_number=next_number,
        previous_chapter=last_number,
        narrative_goal=milestone,
        required_facts=world[:3] + hooks[:3],
        forbidden_contradictions=world[:3],
        open_hooks=hooks,
        last_chapter_ending=_tail(last_text, 1200),
        character_states=characters[:8],
        target_chinese_chars=target,
        min_chinese_chars=max(1000, int(target * 0.75)),
    )


def _load_canon_chapters(root: Path) -> list[tuple[int, Path, str]]:
    chapters: list[tuple[int, Path, str]] = []
    for path in (root / "production" / "final_chapters").glob("chapter_*.md"):
        match = re.search(r"chapter_(\d+)", path.stem)
        if match:
            chapters.append((int(match.group(1)), path, path.read_text(encoding="utf-8")))
    return sorted(chapters, key=lambda item: item[0])


def _baseline_knowledge(baseline: dict[str, Any]) -> list[KnowledgeItem]:
    items: list[KnowledgeItem] = []
    for key in ("world_rules", "characters", "plot_milestones", "hooks", "style_constraints"):
        for artifact in baseline.get(key, [])[:3]:
            source_path = str(artifact.get("source_path", artifact.get("title", key)))
            items.append(
                KnowledgeItem(
                    id=f"import:{source_path}",
                    kind=key,
                    title=str(artifact.get("title", key)),
                    body=_compact(str(artifact.get("content", "")), 800),
                    tags={"import", key},
                )
            )
    return items


def _ensure_conflicts_resolved(root: Path) -> None:
    conflicts = _read_json(root / ".creative_os" / "import" / "conflicts.json")
    approval = _read_json(root / ".creative_os" / "import" / "approval.json")
    resolutions = approval.get("resolutions", {})
    unresolved = [item["code"] for item in conflicts if item.get("severity") == "high" and item.get("code") not in resolutions]
    if unresolved:
        raise ContinuationBlockedError(f"unresolved import conflicts: {', '.join(unresolved)}")


def _is_legacy_state_memory(item: object) -> bool:
    item_id = getattr(item, "id", "")
    if not str(item_id).startswith("state-chapter-"):
        return False
    try:
        return json.loads(str(getattr(item, "content"))).get("schema_version") != 2
    except json.JSONDecodeError:
        return True


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _contents(baseline: dict[str, Any], key: str) -> list[str]:
    return [str(artifact.get("content", "")) for artifact in baseline.get(key, []) if artifact.get("content")]


def _first_content(baseline: dict[str, Any], key: str, fallback: str) -> str:
    values = _contents(baseline, key)
    return values[0] if values else fallback


def _chapter_outline_goal(baseline: dict[str, Any], chapter_number: int) -> str | None:
    for artifact in baseline.get("plot_milestones", []):
        for line in str(artifact.get("content", "")).splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 3 or cells[0] != str(chapter_number):
                continue
            title, event = cells[1], cells[2]
            length = cells[3] if len(cells) > 3 else ""
            suffix = f"；目标字数 {length}" if length.isdigit() else ""
            return f"第 {chapter_number} 章《{title}》：{event}{suffix}"
    return None


def _compact(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit].rstrip() + "…"


def _tail(value: str, limit: int) -> str:
    return value if len(value) <= limit else "…" + value[-limit:].lstrip()


def _chinese_char_count(value: str) -> int:
    return sum("\u4e00" <= char <= "\u9fff" for char in value)


def _target_chinese_chars(narrative_goal: str) -> int:
    match = re.search(r"目标字数\s*(\d+)", narrative_goal)
    if match:
        return int(match.group(1))
    return 7000
