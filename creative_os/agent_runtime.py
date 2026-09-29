"""Writer Agent 异步运行时：读取有限项目上下文并生成 Working Draft。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from uuid import uuid4
from datetime import datetime, timezone
import json

from creative_os.llm_writer import OpenAICompatibleClient, ModelMessage
from creative_os.writer_draft_store import WriterDraftStore
from creative_os.creative_context import CreativeContextBuilder
from creative_os.runtime.runner import RuntimeRunner
from creative_os.runtime.model import RuntimeRequest


@dataclass(frozen=True, slots=True)
class AgentJob:
    job_id: str
    status: str
    message: str
    chapter_number: int
    draft_version: int | None = None
    updated_at: str = ""
    mode: str = "act"
    decision_id: str | None = None
    target_words: int = 4500
    tolerance_words: int = 300
    min_words: int = 4200
    max_words: int = 4800
    actual_words: int | None = None
    within_word_range: bool | None = None


class WriterAgentRuntime:
    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root)
        self.store = WriterDraftStore(project_root)
        self._jobs: dict[str, AgentJob] = {}
        self._lock = Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="writer-agent")

    def submit(self, instruction: str, chapter_number: int, actor: str = "作者", *, target_words: int = 4500, tolerance_words: int = 300) -> AgentJob:
        if type(target_words) is not int or type(tolerance_words) is not int or target_words <= 0 or tolerance_words < 0:
            raise ValueError("word_target_invalid")
        min_words = max(1, target_words - tolerance_words)
        max_words = target_words + tolerance_words
        job_id = f"agent-{uuid4().hex}"
        mode = "analyze" if any(token in instruction for token in ("不要修改", "只分析", "检查一下", "有什么问题")) else "act"
        job = AgentJob(job_id, "queued", "任务已排队，等待 Agent 读取上下文。", chapter_number, None, datetime.now(timezone.utc).isoformat(), mode, None, target_words, tolerance_words, min_words, max_words)
        with self._lock:
            self._jobs[job_id] = job
        self._pool.submit(self._run, job_id, instruction, chapter_number, actor)
        return job

    def get(self, job_id: str) -> AgentJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_decision(self, decision_id: str) -> dict[str, object]:
        path = self.root / ".creative_os" / "agent" / "decisions" / f"{decision_id}.json"
        if not path.exists():
            raise FileNotFoundError(decision_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def submit_from_decision(self, decision_id: str, actor: str = "作者") -> AgentJob:
        """作者确认后，才允许把只读决策转入执行任务。"""
        try:
            decision = self.get_decision(decision_id)
        except FileNotFoundError as error:
            raise ValueError("decision_not_found") from error
        chapter = int(decision["target_chapter"])
        instruction = f"按创作决策 {decision_id} 执行修改：{decision.get('analysis', '')}"
        return self.submit(
            instruction,
            chapter,
            actor,
            target_words=int(decision.get("target_words", 4500)),
            tolerance_words=int(decision.get("tolerance_words", 300)),
        )

    def _set(self, job_id: str, **changes: object) -> None:
        with self._lock:
            current = self._jobs[job_id]
            self._jobs[job_id] = AgentJob(current.job_id, str(changes.get("status", current.status)), str(changes.get("message", current.message)), current.chapter_number, changes.get("draft_version", current.draft_version), datetime.now(timezone.utc).isoformat(), current.mode, changes.get("decision_id", current.decision_id), current.target_words, current.tolerance_words, current.min_words, current.max_words, changes.get("actual_words", current.actual_words), changes.get("within_word_range", current.within_word_range))

    def _run(self, job_id: str, instruction: str, chapter_number: int, actor: str) -> None:
        try:
            job = self.get(job_id)
            if job is None:
                return
            self._set(job_id, status="reading_context", message="正在读取前文、项目状态和相邻章节。")
            final_root = self.root / "production" / "final_chapters"
            latest = max((int(path.stem.split("_")[-1]) for path in final_root.glob("chapter_*.md")), default=chapter_number)
            target = max(chapter_number, latest + 1) if job.mode == "act" and ("继续" in instruction or "写" in instruction) and not instruction.startswith("按创作决策") else chapter_number
            previous = []
            for number in range(max(1, target - 3), target):
                path = final_root / f"chapter_{number:03d}.md"
                if path.exists():
                    previous.append(path.read_text(encoding="utf-8")[-6000:])
            context = CreativeContextBuilder(self.root).build(instruction, target)
            formal_word_count = len("".join(context.current_formal.split())) if context.current_formal else 0
            context_summary = {"recent_chapters": list(context.recent_chapters), "source_refs": list(context.source_refs), "has_current_draft": bool(context.current_draft), "formal_word_count": formal_word_count}
            self._set(job_id, status="thinking", message="上下文已读取，Agent 正在形成写作方案。")
            client = OpenAICompatibleClient.from_env()
            previous_text = "\n\n".join(previous)
            if context.current_formal:
                previous_text += f"\n\n【当前目标章节第{target}章正式稿】\n{context.current_formal[-12000:]}"
            if context.current_draft:
                previous_text += f"\n\n【当前目标章节工作稿】\n{context.current_draft[-12000:]}"
            word_contract = f"目标字数：{job.target_words} 字，允许误差：±{job.tolerance_words} 字，范围：{job.min_words}-{job.max_words} 字。当前正式稿精确字数：{formal_word_count} 字。优先保证剧情和人物质量，不要为凑字数重复内容。"
            messages = [
                ModelMessage("system", "你是长篇小说 Writer Agent。只输出中文小说正文，不输出提纲、解释或系统术语。保持人物连续性和章节因果，不要机械分段。"),
                ModelMessage("user", f"用户意图：{instruction}\n{word_contract}\n项目上下文摘要：{context_summary}\n目标章节：第{target}章\n以下是最近章节正文片段：\n\n{previous_text}\n\n{'请只分析问题、依据和建议，不要输出正文，也不要修改任何工作稿。' if job.mode == 'analyze' else f'请基于这些上下文继续创作，输出完整章节正文，标题为《第{target}章》，正文长度控制在上述范围内。'}"),
            ]
            runtime_result = RuntimeRunner().execute(
                RuntimeRequest(
                    task_id=job_id,
                    context_id=context.decision.decision_id,
                    capability="novel-writing-agent",
                    domain="novel",
                    model="writer-agent",
                    messages=tuple(messages),
                    input_refs=tuple(("source_ref", ref) for ref in context.source_refs),
                    temperature=0.78,
                    max_tokens=12000,
                ),
                client,
            )
            content = runtime_result.output
            if job.mode == "analyze":
                decision_id = context.decision.decision_id
                decision_path = self.root / ".creative_os" / "agent" / "decisions" / f"{decision_id}.json"
                decision_path.parent.mkdir(parents=True, exist_ok=True)
                decision_path.write_text(json.dumps({"decision_id": decision_id, "intent": instruction, "target_chapter": target, "context_refs": list(context.source_refs), "analysis": str(content), "created_at": context.decision.created_at, "target_words": job.target_words, "tolerance_words": job.tolerance_words, "min_words": job.min_words, "max_words": job.max_words, "formal_word_count": formal_word_count}, ensure_ascii=False, indent=2), encoding="utf-8")
                self._set(job_id, status="completed", message="分析已完成，正文未修改。", decision_id=decision_id)
                return
            self._set(job_id, status="saving", message="正文已生成，正在写入 Working Draft。")
            current = self.store.current(target)
            expected_version = None if current is None else current[0].version
            text = str(content)
            actual_words = len("".join(text.split()))
            within_word_range = job.min_words <= actual_words <= job.max_words
            version = self.store.save(target, text, actor=actor, expected_version=expected_version)
            range_message = "，字数在目标范围内" if within_word_range else f"，实际 {actual_words} 字，未落在 {job.min_words}-{job.max_words} 字范围内"
            self._set(job_id, status="completed", message=f"第{target}章已生成到 Working Draft{range_message}。", draft_version=version.version, actual_words=actual_words, within_word_range=within_word_range)
        except Exception as error:
            self._set(job_id, status="failed", message=f"Agent 运行失败：{error}")
