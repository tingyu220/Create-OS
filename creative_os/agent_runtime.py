"""Writer Agent 异步运行时：读取有限项目上下文并生成 Working Draft。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from uuid import uuid4
from datetime import datetime, timezone

from creative_os.llm_writer import OpenAICompatibleClient, ModelMessage
from creative_os.writer_draft_store import WriterDraftStore


@dataclass(frozen=True, slots=True)
class AgentJob:
    job_id: str
    status: str
    message: str
    chapter_number: int
    draft_version: int | None = None
    updated_at: str = ""


class WriterAgentRuntime:
    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root)
        self.store = WriterDraftStore(project_root)
        self._jobs: dict[str, AgentJob] = {}
        self._lock = Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="writer-agent")

    def submit(self, instruction: str, chapter_number: int, actor: str = "作者") -> AgentJob:
        job_id = f"agent-{uuid4().hex}"
        job = AgentJob(job_id, "queued", "任务已排队，等待 Agent 读取上下文。", chapter_number, None, datetime.now(timezone.utc).isoformat())
        with self._lock:
            self._jobs[job_id] = job
        self._pool.submit(self._run, job_id, instruction, chapter_number, actor)
        return job

    def get(self, job_id: str) -> AgentJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _set(self, job_id: str, **changes: object) -> None:
        with self._lock:
            current = self._jobs[job_id]
            self._jobs[job_id] = AgentJob(current.job_id, str(changes.get("status", current.status)), str(changes.get("message", current.message)), current.chapter_number, changes.get("draft_version", current.draft_version), datetime.now(timezone.utc).isoformat())

    def _run(self, job_id: str, instruction: str, chapter_number: int, actor: str) -> None:
        try:
            self._set(job_id, status="reading_context", message="正在读取前文、项目状态和相邻章节。")
            final_root = self.root / "production" / "final_chapters"
            latest = max((int(path.stem.split("_")[-1]) for path in final_root.glob("chapter_*.md")), default=chapter_number)
            target = max(chapter_number, latest + 1) if "继续" in instruction or "写" in instruction else chapter_number
            previous = []
            for number in range(max(1, target - 3), target):
                path = final_root / f"chapter_{number:03d}.md"
                if path.exists():
                    previous.append(path.read_text(encoding="utf-8")[-6000:])
            context_summary = {
                "formal_chapters": len(tuple(final_root.glob("chapter_*.md"))),
                "working_drafts": len(tuple(self.store.root.glob("chapter_*.jsonl"))) if self.store.root.exists() else 0,
                "recent_chapters": list(range(max(1, target - 3), target)),
            }
            self._set(job_id, status="thinking", message="上下文已读取，Agent 正在形成写作方案。")
            client = OpenAICompatibleClient.from_env()
            previous_text = "\n\n".join(previous)
            messages = [
                ModelMessage("system", "你是长篇小说 Writer Agent。只输出中文小说正文，不输出提纲、解释或系统术语。保持人物连续性和章节因果，不要机械分段。"),
                ModelMessage("user", f"用户意图：{instruction}\n项目上下文摘要：{context_summary}\n目标章节：第{target}章\n以下是最近章节正文片段：\n\n{previous_text}\n\n请基于这些上下文继续创作，输出完整章节正文，标题为《第{target}章》。"),
            ]
            result = client.complete(messages, temperature=0.78, max_tokens=12000)
            content = getattr(result, "content", result)
            self._set(job_id, status="saving", message="正文已生成，正在写入 Working Draft。")
            current = self.store.current(target)
            expected_version = None if current is None else current[0].version
            version = self.store.save(target, str(content), actor=actor, expected_version=expected_version)
            self._set(job_id, status="completed", message=f"第{target}章已生成到 Working Draft。", draft_version=version.version)
        except Exception as error:
            self._set(job_id, status="failed", message=f"Agent 运行失败：{error}")
