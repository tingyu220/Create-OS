from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from creative_os.domains.novel_continuation import ContinuationTask, build_next_chapter
from creative_os.domains.narrative_memory import load_active_narrative_decision
from creative_os.domains.novel_chapter_memory import save_chapter_candidates
from creative_os.domains.narrative_review import review_narrative
from creative_os.llm_writer import ModelMessage
from creative_os.llm_metrics import TimedCompletion
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.task_status import ChapterTaskStatus, write_chapter_status
from creative_os.validation_runtime import validate_reader_facing_text


class ContinuationClient(Protocol):
    def complete(self, messages: list[ModelMessage], *, temperature: float, max_tokens: int) -> str | TimedCompletion:
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
    target_chinese_chars: int | None = None,
    require_narrative_contract: bool = False,
) -> ContinuationRun:
    root = Path(project_root)
    task, context = build_next_chapter(
        root,
        target_chinese_chars=target_chinese_chars,
        require_narrative_contract=require_narrative_contract,
    )
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
        completion = client.complete(_messages(task, context, issues), temperature=0.78, max_tokens=20000)
        text = completion.content if isinstance(completion, TimedCompletion) else completion
        issues = _review(root, task, text)
        total_elapsed += completion.elapsed_seconds if isinstance(completion, TimedCompletion) else time.monotonic() - started
        if not issues:
            break
    draft_path = root / ".creative_os" / "llm_writer" / "drafts" / f"chapter_{task.chapter_number:03d}.md"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(text, encoding="utf-8")
    experiences = _candidate_experiences(task, issues)
    _write_review(root, task, context, issues, text)
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
        save_chapter_candidates(root, task.chapter_number)
    _write_readiness(root, task, context_path, issues)
    return ContinuationRun(task.chapter_number, "pass" if not issues else "fail", context_path, draft_path, final_path, issues, experiences)


def promote_passing_draft(
    project_root: str | Path,
    *,
    require_narrative_contract: bool = False,
) -> ContinuationRun:
    root = Path(project_root)
    task, context = build_next_chapter(root, require_narrative_contract=require_narrative_contract)
    draft_path = root / ".creative_os" / "llm_writer" / "drafts" / f"chapter_{task.chapter_number:03d}.md"
    if not draft_path.exists():
        raise FileNotFoundError(draft_path)
    text = draft_path.read_text(encoding="utf-8")
    issues = _review(root, task, text)
    context_path = _write_context(root, task, context)
    if issues:
        _write_review(root, task, context, issues, text)
        _write_readiness(root, task, context_path, issues)
        return ContinuationRun(task.chapter_number, "fail", context_path, draft_path, None, issues, _candidate_experiences(task, issues))
    final_path = root / "production" / "final_chapters" / f"chapter_{task.chapter_number:03d}.md"
    final_path.write_text(text, encoding="utf-8")
    save_chapter_candidates(root, task.chapter_number)
    _write_review(root, task, context, [], text)
    write_chapter_status(root, ChapterTaskStatus(chapter=task.chapter_number, status="pass", attempts=0, elapsed_seconds=0.0, issues=[]))
    _write_readiness(root, task, context_path, [])
    return ContinuationRun(task.chapter_number, "pass", context_path, draft_path, final_path, [], [])


def _messages(task: ContinuationTask, context: object, previous_issues: list[str] | None = None) -> list[ModelMessage]:
    knowledge = getattr(context, "knowledge")
    memory = getattr(context, "memory")
    knowledge_text = "\n\n".join(
        f"## {item.title}\n来源：{item.id}\n{item.body}" for item in knowledge
    )
    memory_text = "\n\n".join(
        f"## Active Memory: {item.title}\n{item.content}" for item in memory
    )
    prompt = (
        f"续写小说第 {task.chapter_number} 章，只输出读者可见的 Markdown 正文。\n"
        f"首行必须使用一级标题 `# 第 {task.chapter_number} 章：标题`，后续不得使用 Markdown 小标题。\n"
        "相邻对话必须与上一句的说话人、指代和提问对象一致；不能把“你”和“我”的回应关系写反。\n"
        f"剧情目标：{task.narrative_goal}\n"
        f"必须从上一章最后一幕直接续写，不能重写、概述或改写已发生的情节：{task.last_chapter_ending}\n"
        f"禁止违反：{'；'.join(task.forbidden_contradictions)}\n"
        f"未解决伏笔：{'；'.join(task.open_hooks)}\n"
        f"目标中文字符数：约 {task.target_chinese_chars}，允许上下浮动 15%。最低不得少于 {task.min_chinese_chars}。"
        "标题只能使用首行的一个 `#`，正文禁止出现任何 `##` 标题。\n"
        f"\n获批 Context：\n{knowledge_text}\n\n{memory_text}"
    )
    if task.narrative_contract is not None:
        contract = task.narrative_contract.chapter_contract
        choice = contract.protagonist_choice
        reader = contract.reader_change
        prompt += (
            "\n\n章节叙事合同（已批准，必须执行）：\n"
            f"章节功能：{'；'.join(contract.functions)}\n"
            f"戏剧问题：{contract.dramatic_question}\n"
            f"人物主动选择：{choice.actor}应{choice.action}\n"
            f"选择代价：{choice.cost}\n"
            f"选择后果：{choice.consequence}\n"
            f"读者认知变化：从{reader.before}到{reader.after}\n"
            f"压力曲线：{contract.pressure_curve.start} -> {contract.pressure_curve.turn} -> {contract.pressure_curve.end}\n"
            f"伏笔动作：{'；'.join(contract.foreshadow_actions)}\n"
            f"结尾新失衡：{contract.ending_shift}\n"
            f"禁止项：{'；'.join(contract.forbidden)}"
        )
    if previous_issues:
        prompt += f"\n\n上一版未通过质量门禁：{'；'.join(previous_issues)}。请完整重写，确保满足最低中文字符数。"
    return [ModelMessage(role="system", content="你是长篇小说 Writer，只输出读者可见正文。"), ModelMessage(role="user", content=prompt)]


def _review(project_root: Path, task: ContinuationTask, text: str) -> list[str]:
    issues = validate_reader_facing_text(text)
    if _chinese_char_count(text) < task.min_chinese_chars:
        issues.append("below_minimum_chinese_chars")
    narrative_issues = _narrative_issues(project_root, task, text)
    issues.extend(f"narrative:{issue.code}" for issue in narrative_issues)
    return list(dict.fromkeys(issues))


def _narrative_issues(project_root: Path, task: ContinuationTask, text: str):
    if task.narrative_contract is None:
        return []
    recent_contracts = [
        decision
        for chapter in range(max(1, task.chapter_number - 2), task.chapter_number)
        if (decision := load_active_narrative_decision(project_root, chapter)) is not None
    ]
    return review_narrative(task.narrative_contract, recent_contracts, text)


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


def _write_review(root: Path, task: ContinuationTask, context: object, issues: list[str], text: str) -> None:
    path = root / ".creative_os" / "reviews" / f"chapter_{task.chapter_number:03d}_continuation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    narrative_issues = [asdict(issue) for issue in _narrative_issues(root, task, text)]
    path.write_text(
        json.dumps(
            {"issues": issues, "narrative_issues": narrative_issues, "context": getattr(context, "fingerprint")},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_readiness(root: Path, task: ContinuationTask, context_path: Path, issues: list[str]) -> None:
    path = root / "production" / "reports" / "continuation_readiness.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 接续准备", "", f"- 下一章：{task.chapter_number}", f"- Context：{context_path}", f"- 状态：{'通过' if not issues else '待修复'}"]
    if issues:
        lines.append(f"- 问题：{'；'.join(issues)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _chinese_char_count(value: str) -> int:
    return sum("\u4e00" <= char <= "\u9fff" for char in value)
