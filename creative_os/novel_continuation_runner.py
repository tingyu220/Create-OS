from __future__ import annotations

import json
import hashlib
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from creative_os.domains.novel_continuation import ContinuationTask, build_next_chapter, continuation_task_hash
from creative_os.domains.entity_consistency import canonical_entities_from_baseline, entity_aliases_from_baseline, find_entity_warnings
from creative_os.domains.novel_chapter_memory import save_chapter_candidates
from creative_os.domains.narrative_review import review_narrative
from creative_os.domains.narrative_decision import NarrativeDecision
from creative_os.llm_writer import ModelMessage
from creative_os.llm_metrics import TimedCompletion
from creative_os.runtime import AppendOnlyEventLog, EventType, RuntimeExecutionError, RuntimeRequest, RuntimeRunner
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.domains.writer_admission import (AdmissionGrant, PreAdmissionRequest,
    RestrictedWriterAdmissionToken, WriterAdmissionService, WriterAdmissionToken)
from creative_os.task_status import ChapterTaskStatus, write_chapter_status
from creative_os.validation_runtime import validate_reader_facing_text


class ContinuationClient(Protocol):
    def complete(self, messages: list[ModelMessage], *, temperature: float, max_tokens: int) -> str | TimedCompletion:
        ...


_EXIT_GUARD = object()


@dataclass(frozen=True, slots=True)
class ContinuationRun:
    chapter_number: int
    status: str
    context_path: Path
    draft_path: Path | None
    final_chapter_path: Path | None
    issues: list[str]
    experiences: list[MemoryItem]
    entity_warnings: list[dict[str, object]] | None = None


@dataclass(frozen=True, slots=True)
class PreparedWriterRun:
    project_root: Path
    run_id: str
    task: ContinuationTask
    context: object
    projection: object
    token: WriterAdmissionToken | RestrictedWriterAdmissionToken
    admission_service: WriterAdmissionService


def prepare_continuation_run(project_root: str | Path, run_id: str,
                             admission_service: WriterAdmissionService,
                             contract_id: str) -> PreparedWriterRun:
    root = Path(project_root)
    grant = admission_service.pre_admit(PreAdmissionRequest(contract_id))
    task, context = build_next_chapter(root, require_narrative_contract=True,
                                       grant=grant, admission_service=admission_service)
    token = admission_service.finalize_admission(grant, context.fingerprint, run_id)
    return PreparedWriterRun(root, run_id, task, context, grant.projection, token, admission_service)


def continue_one_chapter(prepared: PreparedWriterRun, *, client: ContinuationClient | None,
                         dry_run: bool = False, max_attempts: int = 1,
                         runtime_runner: RuntimeRunner | None = None) -> ContinuationRun:
    if not isinstance(prepared, PreparedWriterRun):
        raise TypeError("continue_one_chapter requires PreparedWriterRun")
    _require_prepared_binding(prepared)
    return prepared.admission_service.validate_token(
        prepared.token, prepared.run_id, prepared.context.fingerprint,
        handoff=lambda: _continue_one_chapter_impl(prepared, _guard=_EXIT_GUARD, client=client, dry_run=dry_run,
                                                   max_attempts=max_attempts, runtime_runner=runtime_runner),
    )


def _continue_one_chapter_impl(
    prepared: PreparedWriterRun,
    *,
    _guard: object,
    client: ContinuationClient | None,
    dry_run: bool = False,
    max_attempts: int = 1,
    runtime_runner: RuntimeRunner | None = None,
) -> ContinuationRun:
    if _guard is not _EXIT_GUARD:
        raise PermissionError("writer exit implementation requires admission handoff")
    root = prepared.project_root
    event_log = AppendOnlyEventLog(root / ".creative_os" / "runtime" / "events.jsonl")
    task, context = prepared.task, prepared.context
    event_log.append_simple(EventType.TASK_CREATED, task_id=f"chapter-{task.chapter_number:03d}", payload={"chapter": task.chapter_number})
    event_log.append_simple(EventType.TASK_STARTED, task_id=f"chapter-{task.chapter_number:03d}", payload={"previous_chapter": task.previous_chapter})
    context_path = _write_context(root, task, context)
    event_log.append_simple(
        EventType.CONTEXT_BUILT,
        task_id=f"chapter-{task.chapter_number:03d}",
        payload={"context_id": str(getattr(context, "fingerprint")), "path": str(context_path)},
    )
    if dry_run:
        _write_readiness(root, task, context_path, [])
        return ContinuationRun(task.chapter_number, "dry_run", context_path, None, None, [], [])
    if client is None:
        raise ValueError("client is required unless dry_run is enabled")

    text = ""
    issues: list[str] = []
    entity_warnings: list[dict[str, object]] = []
    total_elapsed = 0.0
    runtime = runtime_runner or RuntimeRunner(record_sink=event_log.append_execution, clock=time.monotonic)
    for _ in range(max_attempts):
        messages = (
            _length_extension_messages(task, text)
            if text and issues == ["below_minimum_chinese_chars"]
            else _messages(task, context, issues)
        )
        try:
            runtime_result = runtime.execute(
                RuntimeRequest(
                    task_id=f"chapter-{task.chapter_number:03d}",
                    context_id=str(getattr(context, "fingerprint")),
                    capability="writing",
                    domain="novel",
                    model=str(getattr(client, "model", "unknown")),
                    messages=tuple(messages),
                    input_refs=(("previous_chapter", str(task.previous_chapter)), ("context", str(getattr(context, "fingerprint")))),
                    temperature=0.78,
                    max_tokens=20000,
                ),
                client,
            )
        except RuntimeExecutionError:
            issues = ["model_execution_failed"]
            break
        generated = runtime_result.output
        text = _append_extension(text, generated) if text and issues == ["below_minimum_chinese_chars"] else generated
        issues = _review(root, task, text)
        entity_warnings = _entity_warnings(root, text)
        total_elapsed += runtime_result.reported_elapsed_seconds
        if not issues:
            break
    draft_path = root / ".creative_os" / "llm_writer" / "drafts" / f"chapter_{task.chapter_number:03d}.md"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(text, encoding="utf-8")
    experiences = _candidate_experiences(task, issues)
    _write_review(root, task, context, issues, text, entity_warnings)
    event_log.append_simple(
        EventType.REVIEW_PASSED if not issues else EventType.REVIEW_FAILED,
        task_id=f"chapter-{task.chapter_number:03d}",
        payload={"issues": issues},
    )
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
        event_log.append_simple(
            EventType.KNOWLEDGE_UPDATED,
            task_id=f"chapter-{task.chapter_number:03d}",
            payload={"chapter": task.chapter_number},
        )
        event_log.append_simple(
            EventType.STATE_CHANGED,
            task_id=f"chapter-{task.chapter_number:03d}",
            payload={"chapter": task.chapter_number},
        )
        event_log.append_simple(
            EventType.TASK_COMPLETED,
            task_id=f"chapter-{task.chapter_number:03d}",
            payload={"chapter": task.chapter_number, "status": "pass"},
        )
    else:
        event_log.append_simple(
            EventType.TASK_FAILED,
            task_id=f"chapter-{task.chapter_number:03d}",
            payload={"chapter": task.chapter_number, "issues": issues},
        )
    _write_readiness(root, task, context_path, issues, entity_warnings)
    return ContinuationRun(task.chapter_number, "pass" if not issues else "fail", context_path, draft_path, final_path, issues, experiences, entity_warnings)


def promote_passing_draft(prepared: PreparedWriterRun) -> ContinuationRun:
    if not isinstance(prepared, PreparedWriterRun):
        raise TypeError("promote_passing_draft requires PreparedWriterRun")
    _require_prepared_binding(prepared)
    return prepared.admission_service.validate_token(
        prepared.token, prepared.run_id, prepared.context.fingerprint,
        handoff=lambda: _promote_passing_draft_impl(prepared, _guard=_EXIT_GUARD),
    )


def _require_prepared_binding(prepared: PreparedWriterRun) -> None:
    token = prepared.token
    projection = prepared.projection
    if (type(token) not in {WriterAdmissionToken, RestrictedWriterAdmissionToken}
            or not isinstance(prepared.task, ContinuationTask)
            or type(prepared.admission_service) is not WriterAdmissionService
            or not hasattr(projection, "canonical_json")):
        raise TypeError("prepared run requires final token and frozen projection")
    compiled_task = getattr(prepared.context, "task", None)
    task_binding = next(
        (item for item in getattr(prepared.context, "knowledge", ())
         if item.id == f"writer-task:chapter:{prepared.task.chapter_number:03d}"),
        None,
    )
    expected_task_body = continuation_task_hash(prepared.task)
    projection_hash_mismatch = (
        token.projection_hash != hashlib.sha256(
            json.dumps(asdict(projection), ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")).encode()
        ).hexdigest()
    )
    if (
        prepared.project_root.resolve() != prepared.admission_service.project_root.resolve()
        or prepared.task.contract_projection != projection
        or getattr(compiled_task, "id", None) != f"chapter-{prepared.task.chapter_number:03d}"
        or getattr(compiled_task, "goal", None) != prepared.task.narrative_goal
        or task_binding is None
        or task_binding.body != expected_task_body
    ):
        raise ValueError("prepared task/context binding mismatch")
    if (
        token.project_id != prepared.project_root.name
        or token.chapter_id != f"chapter_{prepared.task.chapter_number:03d}"
        or token.contract_id != projection.contract_id
        or token.contract_version != projection.contract_version
        or token.contract_content_hash != projection.contract_content_hash
        or projection_hash_mismatch
    ):
        raise ValueError("prepared run binding mismatch")


def _promote_passing_draft_impl(prepared: PreparedWriterRun, *, _guard: object) -> ContinuationRun:
    if _guard is not _EXIT_GUARD:
        raise PermissionError("writer exit implementation requires admission handoff")
    root = prepared.project_root
    task, context = prepared.task, prepared.context
    draft_path = root / ".creative_os" / "llm_writer" / "drafts" / f"chapter_{task.chapter_number:03d}.md"
    if not draft_path.exists():
        raise FileNotFoundError(draft_path)
    text = draft_path.read_text(encoding="utf-8")
    issues = _review(root, task, text)
    entity_warnings = _entity_warnings(root, text)
    context_path = _write_context(root, task, context)
    if issues:
        _write_review(root, task, context, issues, text, entity_warnings)
        _write_readiness(root, task, context_path, issues, entity_warnings)
        return ContinuationRun(task.chapter_number, "fail", context_path, draft_path, None, issues, _candidate_experiences(task, issues), entity_warnings)
    final_path = root / "production" / "final_chapters" / f"chapter_{task.chapter_number:03d}.md"
    final_path.write_text(text, encoding="utf-8")
    save_chapter_candidates(root, task.chapter_number)
    _write_review(root, task, context, [], text, entity_warnings)
    write_chapter_status(root, ChapterTaskStatus(chapter=task.chapter_number, status="pass", attempts=0, elapsed_seconds=0.0, issues=[]))
    _write_readiness(root, task, context_path, [], entity_warnings)
    return ContinuationRun(task.chapter_number, "pass", context_path, draft_path, final_path, [], [], entity_warnings)


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
    if task.contract_projection is not None:
        contract = NarrativeDecision.from_json(task.contract_projection.canonical_json).chapter_contract
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
        prompt += f"\n\n上一版未通过质量门禁：{'；'.join(previous_issues)}。"
        if "duplicate_reader_paragraph" in previous_issues:
            prompt += "正文存在完全重复的段落。请重新生成整章时逐段检查，任何内容相同的段落只保留一次；不要用复制段落凑字数，不要把重复段落挪到别处，保持动作、对话和转场自然连续。"
        prompt += "请完整重写，确保满足最低中文字符数。"
    return [ModelMessage(role="system", content="你是长篇小说 Writer，只输出读者可见正文。"), ModelMessage(role="user", content=prompt)]


def _length_extension_messages(task: ContinuationTask, draft: str) -> list[ModelMessage]:
    remaining = max(1200, task.min_chinese_chars - _chinese_char_count(draft) + 500)
    tail = draft[-1800:]
    prompt = (
        f"下面是小说第 {task.chapter_number} 章的已写正文末段。正文尚差篇幅，请从最后一个动作或对话的下一秒自然续写约 {remaining} 个中文字符。\n"
        "只输出可直接接在末段后的正文，不要重复标题、不要概述前文、不要解释写作过程、不要使用场景标签或分隔线。\n"
        "保持人物、地点、时间和对话对象连续；让新增内容推进当前冲突，而不是另起一个割裂场景。\n\n"
        f"已写末段：\n{tail}"
    )
    return [
        ModelMessage(role="system", content="你是长篇小说 Writer，只输出读者可见的连续正文。"),
        ModelMessage(role="user", content=prompt),
    ]


def _append_extension(draft: str, extension: str) -> str:
    cleaned = extension.strip()
    if cleaned.startswith("#"):
        cleaned = "\n".join(line for line in cleaned.splitlines() if not line.lstrip().startswith("#")).strip()
    return f"{draft.rstrip()}\n\n{cleaned}\n"


def _review(project_root: Path, task: ContinuationTask, text: str) -> list[str]:
    issues = validate_reader_facing_text(text)
    if _chinese_char_count(text) < task.min_chinese_chars:
        issues.append("below_minimum_chinese_chars")
    narrative_issues = _narrative_issues(project_root, task, text)
    issues.extend(f"narrative:{issue.code}" for issue in narrative_issues)
    return list(dict.fromkeys(issues))


def _narrative_issues(project_root: Path, task: ContinuationTask, text: str):
    if task.contract_projection is None:
        return []
    return review_narrative(NarrativeDecision.from_json(task.contract_projection.canonical_json), [], text)


def _entity_warnings(project_root: Path, text: str) -> list[dict[str, object]]:
    baseline_path = project_root / ".creative_os" / "import" / "active_baseline.json"
    if not baseline_path.exists():
        baseline_path = project_root / ".creative_os" / "import" / "baseline.json"
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entities = canonical_entities_from_baseline(baseline)
    aliases = entity_aliases_from_baseline(baseline)
    return [warning.to_dict() for warning in find_entity_warnings(text, entities, aliases=aliases)]


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
        "contract_binding": {
            "contract_id": task.contract_projection.contract_id,
            "contract_version": task.contract_projection.contract_version,
            "contract_content_hash": task.contract_projection.contract_content_hash,
            "context_fingerprint": getattr(context, "fingerprint"),
        },
        "size_chars": getattr(context, "size_chars"),
        "sources": [asdict(source) for source in getattr(context, "sources")],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_review(root: Path, task: ContinuationTask, context: object, issues: list[str], text: str, entity_warnings: list[dict[str, object]] | None = None) -> None:
    path = root / ".creative_os" / "reviews" / f"chapter_{task.chapter_number:03d}_continuation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    narrative_issues = [asdict(issue) for issue in _narrative_issues(root, task, text)]
    path.write_text(
        json.dumps(
            {"issues": issues, "entity_warnings": entity_warnings or [], "narrative_issues": narrative_issues, "context": getattr(context, "fingerprint")},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_readiness(root: Path, task: ContinuationTask, context_path: Path, issues: list[str], entity_warnings: list[dict[str, object]] | None = None) -> None:
    path = root / "production" / "reports" / "continuation_readiness.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 接续准备", "", f"- 下一章：{task.chapter_number}", f"- Context：{context_path}", f"- 状态：{'通过' if not issues else '待修复'}"]
    if issues:
        lines.append(f"- 问题：{'；'.join(issues)}")
    if entity_warnings:
        lines.append(f"- 实体一致性人工复核：{len(entity_warnings)} 条")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _chinese_char_count(value: str) -> int:
    return sum("\u4e00" <= char <= "\u9fff" for char in value)
