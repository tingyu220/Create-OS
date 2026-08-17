from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from creative_os.domains.novel_continuation import ContinuationTask, build_next_chapter
from creative_os.llm_writer import ModelMessage
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.task_status import ChapterTaskStatus, write_chapter_status
from creative_os.validation_runtime import validate_reader_facing_text


class ContinuationClient(Protocol):
    def complete(self, messages: list[ModelMessage], *, temperature: float, max_tokens: int) -> str:
        ...


@dataclass(frozen=True, slots=True)
class ContinuationRun:
    chapter_number: int
    status: str
    context_path: Path
    draft_path: Path | None
    final_chapter_path: Path | None
    issues: list[str]
    experiences: list[MemoryItem]


def continue_one_chapter(
    project_root: str | Path,
    *,
    client: ContinuationClient | None,
    dry_run: bool = False,
    max_attempts: int = 1,
) -> ContinuationRun:
    root = Path(project_root)
    task, context = build_next_chapter(root)
    context_path = _write_context(root, task, context)
    if dry_run:
        _write_readiness(root, task, context_path, [])
        return ContinuationRun(task.chapter_number, "dry_run", context_path, None, None, [], [])
    if client is None:
        raise ValueError("client is required unless dry_run is enabled")

    text = ""
    issues: list[str] = []
    total_elapsed = 0.0
    for _ in range(max_attempts):
        started = time.monotonic()
        text = client.complete(_messages(task, context), temperature=0.78, max_tokens=12000)
        issues = _review(task, text)
        total_elapsed += time.monotonic() - started
        if not issues:
            break
    draft_path = root / ".creative_os" / "llm_writer" / "drafts" / f"chapter_{task.chapter_number:03d}.md"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(text, encoding="utf-8")
    experiences = _candidate_experiences(task, issues)
    review_path = root / ".creative_os" / "reviews" / f"chapter_{task.chapter_number:03d}_continuation.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(json.dumps({"issues": issues, "context": context.fingerprint}, ensure_ascii=False, indent=2), encoding="utf-8")
    write_chapter_status(
        root,
        ChapterTaskStatus(
            chapter=task.chapter_number,
            status="pass" if not issues else "fail",
            attempts=max_attempts,
            elapsed_seconds=round(total_elapsed, 3),
            issues=issues,
        ),
    )
    final_path: Path | None = None
    if not issues:
        final_path = root / "production" / "final_chapters" / f"chapter_{task.chapter_number:03d}.md"
        final_path.write_text(text, encoding="utf-8")
    _write_readiness(root, task, context_path, issues)
    return ContinuationRun(task.chapter_number, "pass" if not issues else "fail", context_path, draft_path, final_path, issues, experiences)


def _messages(task: ContinuationTask, context: object) -> list[ModelMessage]:
    memory_sources = getattr(context, "sources")
    source_text = "\n".join(f"- {source.source_id}: {source.reason}" for source in memory_sources)
    prompt = (
        f"续写小说第 {task.chapter_number} 章，只输出 Markdown 正文。\n"
        f"剧情目标：{task.narrative_goal}\n"
        f"必须延续：{task.last_chapter_ending}\n"
        f"禁止违反：{'；'.join(task.forbidden_contradictions)}\n"
        f"未解决伏笔：{'；'.join(task.open_hooks)}\n"
        f"最低中文字符数：{task.min_chinese_chars}\n"
        f"Context 来源：\n{source_text}"
    )
    return [ModelMessage(role="system", content="你是长篇小说 Writer，只输出读者可见正文。"), ModelMessage(role="user", content=prompt)]


def _review(task: ContinuationTask, text: str) -> list[str]:
    issues = validate_reader_facing_text(text)
    if _chinese_char_count(text) < task.min_chinese_chars:
        issues.append("below_minimum_chinese_chars")
    return issues


def _candidate_experiences(task: ContinuationTask, issues: list[str]) -> list[MemoryItem]:
    return [
        MemoryItem.new_candidate(
            id=f"continuation-{task.chapter_number:03d}-{issue}",
            kind=MemoryKind.EXPERIENCE,
            scope=MemoryScope.PROJECT,
            scope_id="continuation",
            title=f"第 {task.chapter_number} 章质量问题",
            content=issue,
            evidence=[MemoryEvidence(source_type="review", source_id=f"chapter-{task.chapter_number:03d}")],
            tags={"continuation", issue},
        )
        for issue in issues
    ]


def _write_context(root: Path, task: ContinuationTask, context: object) -> Path:
    path = root / ".creative_os" / "contexts" / "compiled" / f"chapter_{task.chapter_number:03d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "chapter": task.chapter_number,
        "task": asdict(task),
        "fingerprint": getattr(context, "fingerprint"),
        "sources": [asdict(source) for source in getattr(context, "sources")],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_readiness(root: Path, task: ContinuationTask, context_path: Path, issues: list[str]) -> None:
    path = root / "production" / "reports" / "continuation_readiness.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 接续准备", "", f"- 下一章：{task.chapter_number}", f"- Context：{context_path}", f"- 状态：{'通过' if not issues else '待修复'}"]
    if issues:
        lines.append(f"- 问题：{'；'.join(issues)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _chinese_char_count(value: str) -> int:
    return sum("\u4e00" <= char <= "\u9fff" for char in value)
