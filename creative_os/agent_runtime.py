"""Writer Agent 异步运行时：读取项目上下文并生成独立候选提案。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import Lock
from uuid import uuid4
from datetime import datetime, timezone
from copy import deepcopy
import json
import hashlib

from creative_os.llm_writer import OpenAICompatibleClient, ModelMessage
from creative_os.writer_draft_store import WriterDraftStore
from creative_os.creative_context import CreativeContextBuilder
from creative_os.runtime.runner import RuntimeRunner
from creative_os.runtime.model import RuntimeRequest
from creative_os.agent_conversation_store import AgentConversationStore
from creative_os.domains.project_authority import project_authority_lock
from creative_os.agent_proposal_store import AgentProposalStore
from creative_os.agent_proposal_command import AgentProposalCommandHandler, AgentProposalCommandBoundary
from creative_os.workspace_command import FileCommandResultStore
from creative_os.writer_lesson import WriterLessonService
from creative_os.writer_lesson_command import WriterLessonCommandHandler, WriterLessonCommandBoundary
from creative_os.writer_context_sources import ContextCapture, CapturingModelAdapter, WriterContextSourceQuery
from creative_os.writer_word_budget import WriterWordBudget, count_writer_words
from creative_os.story_architecture_store import StoryArchitectureStore
from creative_os.story_architecture_command import story_commands
from creative_os.story_context import freeze_confirmed_story, chapter_story_context
from creative_os.chapter_preflight import ChapterPreflightStore, analyze_chapter_preflight


@dataclass(frozen=True, slots=True)
class AgentJob:
    job_id: str
    status: str
    message: str
    chapter_number: int | None
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
    project_id: str = ""
    session_id: str = ""
    instruction: str = ""
    actor: str = "作者"
    error: str | None = None
    retryable: bool = False
    retry_of: str | None = None
    retry_job_id: str | None = None
    proposal_id: str | None = None
    parent_proposal_id: str | None = None
    proposal_source: str | None = None
    experience_context: dict | None = None
    context_snapshot: dict | None = None
    word_assessment: dict | None = None
    # 受理时记录开始时间；旧任务留空，不从更新时间猜测开始时间。
    started_at: str = ""
    status_updated_at: str = ""
    scope: str = "chapter"
    story_context: dict | None = None
    tool_trace: tuple = ()
    step_snapshots: tuple = ()
    requested_expert: str | None = None
    require_confirmed_combat: bool = False
    combat_context: dict | None = None
    combat_results: tuple = ()
    main_input: tuple = ()
    analysis_state: dict | None = None
    preflight_plan_id: str | None = None


class WriterAgentRuntime:
    def __init__(self, project_root: str | Path, project_id: str | None = None, *, client_factory=None, read_only=False, recover=True) -> None:
        self.root = Path(project_root)
        self.project_id = project_id or self.root.resolve().name
        self.client_factory = client_factory or (lambda: OpenAICompatibleClient.from_env())
        self.read_only = read_only
        self.story = StoryArchitectureStore(self.root, self.project_id)
        self.preflight = ChapterPreflightStore(self.root)
        self.story_commands = story_commands(self.story)
        self.store = WriterDraftStore(project_root)
        self.conversations = AgentConversationStore(self.root, self.project_id)
        self.proposals = AgentProposalStore(self.root, self.project_id)
        self._jobs: dict[str, AgentJob] = {}
        self._futures: dict[str, Future] = {}
        self._lock = Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="writer-agent")
        self._interrupted_jobs = set()
        for raw in self.conversations.load_jobs():
            raw.setdefault("require_confirmed_combat", False)
            raw.setdefault("preflight_plan_id", None)
            job = AgentJob(**raw)
            self._jobs[job.job_id] = job
            if job.status not in {"completed", "failed"} and (read_only or not recover):
                self._interrupted_jobs.add(job.job_id)
            if not read_only and recover and job.status not in {"completed", "failed"}:
                reason = "服务在保存阶段中断，保存结果待核对，请检查工作稿版本。" if job.status == "saving" else "服务重启导致任务中断，可手动重试。"
                self._set(job.job_id, status="failed", message=reason,
                          error=reason, retryable=job.status != "saving")
                if job.proposal_id:
                    self.proposals.fail_unfinished(job.proposal_id, reason)
        proposal_handler = AgentProposalCommandHandler(self)
        if not read_only and recover:
            proposal_handler.recover()
        self.proposal_commands = AgentProposalCommandBoundary(proposal_handler, version_reader=lambda _: None,
                                                store=FileCommandResultStore(self.root), request_validator=proposal_handler.validate)
        self.lessons = WriterLessonService(self)
        self.context_sources = WriterContextSourceQuery(self)
        lesson_handler = WriterLessonCommandHandler(self.lessons)
        if not read_only and recover:
            lesson_handler.recover()
        self.lesson_commands = WriterLessonCommandBoundary(lesson_handler, version_reader=lambda _: None,
                                                store=FileCommandResultStore(self.root), request_validator=lesson_handler.validate)

    def lesson_query(self, chapter_number):
        return self.lessons.query(chapter_number)

    def conversation(self, chapter_number: int) -> dict:
        session = self.conversations.conversation(chapter_number)
        for job in session["jobs"]:
            self._project_interrupted_job(job)
        if chapter_number is None:
            return {**session, **self.story.view()}
        session["proposals"] = [self.proposals.public(self.proposals.read(job["proposal_id"])) for job in session["jobs"] if job.get("proposal_id")]
        session["lesson_review"] = self.lesson_query(chapter_number)
        for job in session["jobs"]:
            job["context_available"] = job.pop("context_snapshot", None) is not None
            if job.get("preflight_plan_id"):
                try:
                    job["preflight"] = asdict(self.preflight.get(job["preflight_plan_id"]))
                except (KeyError, OSError, ValueError):
                    job["preflight"] = None
        return session

    def _project_interrupted_job(self, job):
        if job["job_id"] in self._interrupted_jobs:
            saving = job["status"] == "saving"
            job.update(observed_status=job["status"], status="failed", recovery_required=True, retryable=not saving,
                       message="保存阶段中断，请先核对工作稿，不能自动重试。" if saving else "上次任务未完成；可显式重试接管此任务。",
                       error="saving_reconciliation_required" if saving else "task_recovery_required")
        return job

    def job_view(self, job):
        view = self._project_interrupted_job(asdict(job))
        if view.get("preflight_plan_id"):
            try:
                view["preflight"] = asdict(self.preflight.get(view["preflight_plan_id"]))
            except (KeyError, OSError, ValueError):
                view["preflight"] = None
        return view

    def validate_submit(self, instruction, chapter_number, actor="作者", *, target_words=4500, tolerance_words=300,
                        session_id=None, retry_of=None, mode="analyze", decision_id=None, parent_proposal_id=None, proposal_source=None, requested_expert=None, require_confirmed_combat=False):
        """只读预检；HTTP 在写接管前调用，执行时仍在项目锁内复核。"""
        if not isinstance(instruction, str) or not instruction.strip() or not isinstance(actor, str) or not actor.strip():
            raise ValueError("instruction_required")
        if type(target_words) is not int or type(tolerance_words) is not int or target_words <= 0 or tolerance_words < 0:
            raise ValueError("word_target_invalid")
        if not isinstance(mode, str) or mode not in {"analyze", "act"}:
            raise ValueError("agent_mode_invalid")
        if type(require_confirmed_combat) is not bool or (require_confirmed_combat and chapter_number is None):
            raise ValueError("combat_plan_scope_invalid")
        if requested_expert is not None and requested_expert != "combat":
            raise ValueError("requested_expert_invalid")
        if requested_expert is not None and mode != "analyze":
            raise ValueError("expert_requires_analysis")
        if chapter_number is None and (mode != "analyze" or parent_proposal_id or decision_id):
            raise ValueError("story_mode_invalid")
        session = self.conversations.read(chapter_number)
        if session_id is not None and session_id != session["session_id"]:
            raise ValueError("session_scope_mismatch")
        if any(item["status"] not in {"completed", "failed"} and item["job_id"] != retry_of for item in session["jobs"].values()):
            raise ValueError("session_busy")
        if chapter_number is not None and not retry_of:
            freeze_confirmed_story(self.root, self.project_id, chapter_number=chapter_number,
                                   require_confirmed_combat=require_confirmed_combat)
        elif retry_of and require_confirmed_combat:
            # 显式采用重试只校验原冻结输入，不能用后来确认的计划补历史。
            original = self._jobs.get(retry_of)
            if original is None:
                raise ValueError("job_not_found")
            if (original.project_id, original.chapter_number, original.session_id) != (self.project_id, chapter_number, session["session_id"]):
                raise ValueError("session_scope_mismatch")
            if original.story_context is None:
                raise ValueError("story_confirmation_required")
            _, plans = chapter_story_context(original.story_context, chapter_number)
            if not plans:
                raise ValueError("combat_plan_confirmation_required")
        if parent_proposal_id:
            parent = self.proposals.read(parent_proposal_id)
            if parent["chapter_number"] != chapter_number or parent["session_id"] != session["session_id"] or proposal_source not in {"candidate", "base"}:
                raise ValueError("proposal_scope_mismatch")

    def submit(self, instruction: str, chapter_number: int | None, actor: str = "作者", *, target_words: int = 4500, tolerance_words: int = 300, session_id: str | None = None, retry_of: str | None = None, mode: str = "analyze", decision_id: str | None = None, parent_proposal_id: str | None = None, proposal_source: str | None = None, job_id: str | None = None, requested_expert: str | None = None, require_confirmed_combat: bool = False) -> AgentJob:
        if self.read_only:
            raise ValueError("query_runtime_readonly")
        self.validate_submit(instruction, chapter_number, actor, target_words=target_words, tolerance_words=tolerance_words,
                             session_id=session_id, retry_of=retry_of, mode=mode, decision_id=decision_id,
                             parent_proposal_id=parent_proposal_id, proposal_source=proposal_source, requested_expert=requested_expert,
                             require_confirmed_combat=require_confirmed_combat)
        min_words = max(1, target_words - tolerance_words)
        max_words = target_words + tolerance_words
        job_id = job_id or f"agent-{uuid4().hex}"
        # 文本内容不授予写入权限；Act 只能来自显式执行命令。
        job = AgentJob(job_id, "queued", "任务已排队，等待 Agent 读取上下文。", chapter_number, None, datetime.now(timezone.utc).isoformat(), mode, None, target_words, tolerance_words, min_words, max_words)
        job = replace(job, started_at=job.updated_at, status_updated_at=job.updated_at)
        with project_authority_lock(self.root), self._lock:
            self.validate_submit(instruction, chapter_number, actor, target_words=target_words, tolerance_words=tolerance_words,
                                 session_id=session_id, retry_of=retry_of, mode=mode, decision_id=decision_id,
                                 parent_proposal_id=parent_proposal_id, proposal_source=proposal_source, requested_expert=requested_expert,
                                 require_confirmed_combat=require_confirmed_combat)
            frozen_story = (self._jobs[retry_of].story_context if retry_of else freeze_confirmed_story(self.root, self.project_id,
                chapter_number=chapter_number, require_confirmed_combat=require_confirmed_combat)) if chapter_number is not None else None
            session = self.conversations.read(chapter_number)
            job = replace(job, project_id=self.project_id, session_id=session["session_id"], instruction=instruction.strip(), actor=actor, retry_of=retry_of, decision_id=decision_id,
                          parent_proposal_id=parent_proposal_id, proposal_source=proposal_source,
                          scope="story" if chapter_number is None else "chapter", story_context=frozen_story, requested_expert=requested_expert,
                          require_confirmed_combat=require_confirmed_combat)
            if mode == "act" and chapter_number is not None:
                plan = self.preflight.create(self.project_id, chapter_number)
                job = replace(job, preflight_plan_id=plan.plan_id)
            if mode == "analyze":
                from creative_os.chapter_agent_tools import freeze_combat_request
                original = self._jobs[retry_of] if retry_of else None
                job = replace(job, combat_context=freeze_combat_request(self.root, self.project_id, job, original=original),
                              main_input=original.main_input if original else (),
                              analysis_state=deepcopy(original.analysis_state) if original else None,
                              experience_context=deepcopy(original.experience_context) if original else None)
            if retry_of:
                original = self._jobs[retry_of]
                if original.retry_job_id:
                    return self._jobs[original.retry_job_id]
                original = replace(original, retry_job_id=job_id)
                session["jobs"][retry_of] = asdict(original)
                self._jobs[retry_of] = original
            else:
                session["messages"].append({"message_id": f"message-{uuid4().hex}", "task_id": job_id, "role": "user", "content": instruction.strip(), "created_at": job.updated_at})
            session["jobs"][job_id] = asdict(job)
            self.conversations.write(session)
            self._jobs[job_id] = job
            # 队列登记与持久任务处于同一身份锁内，迁移不会漏看待启动或收尾Future。
            future = self._pool.submit(self._run, job_id, instruction, chapter_number, actor)
            if future is not None:
                self._futures[job_id] = future
        return job

    def assert_migration_idle(self):
        """只读自有任务与Future；不取消、不等待、不推断中断任务已安全结束。"""
        with self._lock:
            for job in self._jobs.values():
                if not isinstance(job, AgentJob):
                    raise ValueError("project_migration_state_unknown")
                if job.status not in {"completed", "failed"}:
                    raise ValueError("project_migration_active")
            for future in self._futures.values():
                if not isinstance(future, Future):
                    raise ValueError("project_migration_state_unknown")
                if not future.done():
                    raise ValueError("project_migration_active")

    def validate_retry(self, job_id, *, chapter_number, session_id):
        job = self.get(job_id)
        if job is None:
            raise ValueError("job_not_found")
        if job.chapter_number != chapter_number or job.session_id != session_id:
            raise ValueError("session_scope_mismatch")
        if job.retry_job_id:
            return job
        interrupted = job_id in self._interrupted_jobs and job.status != "saving"
        if not interrupted and (job.status != "failed" or not job.retryable):
            raise ValueError("job_not_retryable")
        latest = next(reversed(self.conversations.read(chapter_number)["jobs"]))
        if latest != job_id:
            raise ValueError("job_retry_superseded")
        self.validate_submit(job.instruction, chapter_number, job.actor, target_words=job.target_words, tolerance_words=job.tolerance_words,
                             session_id=session_id, retry_of=job_id, mode=job.mode, decision_id=job.decision_id,
                             parent_proposal_id=job.parent_proposal_id, proposal_source=job.proposal_source, requested_expert=job.requested_expert,
                             require_confirmed_combat=job.require_confirmed_combat)
        return job

    def retry(self, job_id: str, *, chapter_number: int, session_id: str) -> AgentJob:
        self.validate_retry(job_id, chapter_number=chapter_number, session_id=session_id)
        if self.read_only:
            raise ValueError("query_runtime_readonly")
        with project_authority_lock(self.root):
            job = self.validate_retry(job_id, chapter_number=chapter_number, session_id=session_id)
            if job.retry_job_id:
                return self.get(job.retry_job_id)
            if job_id in self._interrupted_jobs:
                reason = "作者显式重试，接管此中断任务。"
                self._set(job_id, status="failed", message=reason, error=reason, retryable=True)
                if job.proposal_id:
                    self.proposals.fail_unfinished(job.proposal_id, reason)
            return self.submit(job.instruction, chapter_number, job.actor, target_words=job.target_words,
                               tolerance_words=job.tolerance_words, session_id=session_id, retry_of=job_id,
                               mode=job.mode, decision_id=job.decision_id, parent_proposal_id=job.parent_proposal_id, proposal_source=job.proposal_source, requested_expert=job.requested_expert,
                               require_confirmed_combat=job.require_confirmed_combat)

    def get(self, job_id: str) -> AgentJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_decision(self, decision_id: str) -> dict[str, object]:
        if not decision_id.startswith("decision-") or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in decision_id):
            raise ValueError("decision_id_invalid")
        path = self.root / ".creative_os" / "agent" / "decisions" / f"{decision_id}.json"
        if not path.exists():
            raise FileNotFoundError(decision_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_decision(self, decision_id, decision):
        with project_authority_lock(self.root):
            path = self.root / ".creative_os" / "agent" / "decisions" / f"{decision_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")

    def submit_from_decision(self, decision_id: str, actor: str = "作者", feedback: str = "", *, require_confirmed_combat: bool = False) -> AgentJob:
        """作者确认后，才允许把只读决策转入执行任务。"""
        try:
            decision = self.get_decision(decision_id)
        except FileNotFoundError as error:
            raise ValueError("decision_not_found") from error
        chapter = int(decision["target_chapter"])
        instruction = f"按创作决策 {decision_id} 执行修改：{decision.get('analysis', '')}"
        if feedback.strip():
            instruction += f"\n作者补充要求：{feedback.strip()}"
        return self.submit(
            instruction,
            chapter,
            actor,
            target_words=int(decision.get("target_words", 4500)),
            tolerance_words=int(decision.get("tolerance_words", 300)),
            session_id=decision.get("session_id"),
            mode="act",
            decision_id=decision_id,
            require_confirmed_combat=require_confirmed_combat,
        )

    def _set(self, job_id: str, **changes: object) -> None:
        with project_authority_lock(self.root), self._lock:
            current = self._jobs[job_id]
            reply = changes.pop("reply", None)
            now = datetime.now(timezone.utc).isoformat()
            if any(key in changes and changes[key] != getattr(current, key) for key in ("status", "message", "error")):
                changes["status_updated_at"] = now
            job = replace(current, **changes, updated_at=now)
            session = self.conversations.read(current.chapter_number)
            session["jobs"][job_id] = asdict(job)
            if reply is not None:
                message_id = self.proposals.read(job.proposal_id)["message_id"] if job.proposal_id else f"message-{uuid4().hex}"
                session["messages"].append({"message_id": message_id, "task_id": job_id, "role": "assistant", "content": str(reply), "created_at": job.updated_at, "proposal_id": job.proposal_id})
            self.conversations.write(session)
            self._jobs[job_id] = job
            if job.status in {"completed", "failed"}:
                self._interrupted_jobs.discard(job_id)

    def _run(self, job_id: str, instruction: str, chapter_number: int, actor: str) -> None:
        try:
            job = self.get(job_id)
            if job is None:
                return
            if job.scope == "story":
                from creative_os.story_architecture_agent import run_story_turn
                run_story_turn(self, job)
                return
            if job.mode == "analyze" and job.main_input and job.analysis_state:
                from creative_os.chapter_agent_tools import replay_chapter_analysis
                replay_chapter_analysis(self, job)
                return
            self._set(job_id, status="reading_context", message="正在读取前文、项目状态和相邻章节。")
            if job.preflight_plan_id:
                self.preflight.update(job.preflight_plan_id, status="running")
            final_root = self.root / "production" / "final_chapters"
            target = chapter_number
            proposal = None
            if job.mode == "act":
                proposal = self.proposals.create(job, f"message-{uuid4().hex}")
                self._set(job_id, proposal_id=proposal["proposal_id"])
            previous = []
            capture = ContextCapture()
            for number in range(max(1, target - 3), target):
                path = final_root / f"chapter_{number:03d}.md"
                if path.exists():
                    original = path.read_text(encoding="utf-8")
                    excerpt = original[-6000:]
                    # 每条前文占独立拼接段，即使正文相同也有各自的准确偏移。
                    segment_start = sum(len(text) for text in previous) + 2 * len(previous)
                    previous.append(excerpt)
                    capture.add(f"前文章节 · 第{number}章", str(path.relative_to(self.root)).replace("\\", "/"), excerpt,
                                original=original, start=max(0, len(original) - 6000), version="sha256", message_start=segment_start)
            context = CreativeContextBuilder(self.root, project_id=self.project_id).build(instruction, target, task_id=job_id)
            formal_word_count = count_writer_words(context.current_formal)
            if job.preflight_plan_id:
                preflight = analyze_chapter_preflight(
                    chapter_number=target,
                    instruction=instruction,
                    previous_text="\n\n".join(previous),
                    current_formal=context.current_formal,
                    current_draft=context.current_draft,
                    source_refs=tuple(context.source_refs),
                    requested_expert=job.requested_expert,
                    require_confirmed_combat=job.require_confirmed_combat,
                    source_hashes=tuple(
                        hashlib.sha256((self.root / ref).read_bytes()).hexdigest()
                        if (self.root / ref).is_file() else hashlib.sha256(ref.encode("utf-8")).hexdigest()
                        for ref in context.source_refs
                    ),
                    creative_state=context.creative_state,
                )
                self.preflight.update(
                    job.preflight_plan_id,
                    status="ready",
                    **preflight,
                )
            context_summary = {"recent_chapters": list(context.recent_chapters), "source_refs": list(context.source_refs), "has_current_draft": bool(context.current_draft), "formal_word_count": formal_word_count}
            self._set(job_id, status="thinking", message="上下文已读取，Agent 正在形成写作方案。", experience_context=context.experience_context)
            client = self.client_factory() if job.mode == "act" else None
            previous_text = "\n\n".join(previous)
            if context.current_formal:
                previous_text += f"\n\n【当前目标章节第{target}章正式稿】\n{context.current_formal}"
                capture.add("当前正式稿", f"production/final_chapters/chapter_{target:03d}.md",
                            context.current_formal if proposal is None else None, version="sha256",
                            message_start=len(previous_text) - len(context.current_formal),
                            reason=None if proposal is None else "frozen_input_replaced_body")
            if context.current_draft:
                previous_text += f"\n\n【当前目标章节工作稿】\n{context.current_draft}"
                capture.add("当前工作稿", f".creative_os/writer/drafts/chapter_{target:03d}.jsonl",
                            context.current_draft if proposal is None else None, version=context.current_draft_version,
                            message_start=len(previous_text) - len(context.current_draft),
                            reason=None if proposal is None else "frozen_input_replaced_body")
            if proposal is not None:
                # 执行正文只使用冻结输入；继续修改明确指定候选或原稿。
                previous_text = "\n\n".join(previous)
                previous_text += f"\n\n【本次执行冻结输入，来源 {job.proposal_source or proposal['base']['source']}】\n{proposal['input']['content']}"
                capture.add("本次执行冻结输入", proposal["input"]["ref"], proposal["input"]["content"],
                            version=proposal["input"].get("version"), proposal_id=proposal["proposal_id"],
                            message_start=len(previous_text) - len(proposal["input"]["content"]),
                            input_source=job.proposal_source or proposal["base"]["source"])
            if job.preflight_plan_id:
                previous_text += "\n\n【本章前置架构分析（写作前生成）】\n"
                previous_text += "以下内容是基于当前证据的创作建议；只有已确认故事设定和明确采用的计划属于硬约束，推断与未知项不得当作事实擅自补全。\n"
                previous_text += json.dumps(preflight, ensure_ascii=False)
                if context.creative_state:
                    previous_text += "\n【相关 Creative State（只读证据）】\n"
                    previous_text += json.dumps(context.creative_state, ensure_ascii=False)[:12000]
            input_content = proposal["input"]["content"] if proposal is not None else (context.current_draft or context.current_formal)
            if job.story_context:
                frozen = job.story_context
                ordinary, combat_plans = chapter_story_context(frozen, target)
                if ordinary:
                    previous_text += f"\n\n【作者明确确认的故事设定 version={frozen['version']} hash={frozen['hash']} source_ref={frozen['source_ref']}】\n" + ordinary
                    capture.add("已确认故事设定", frozen["source_ref"], ordinary, version=frozen["version"],
                                story_hash=frozen["hash"], message_start=len(previous_text) - len(ordinary))
                for plan in combat_plans:
                    previous_text += f"\n\n【作者明确确认的本章战斗计划 version={plan['version']} hash={plan['hash']} source_ref={plan['source_ref']}】\n" + plan["text"]
                    capture.add("已确认战斗计划", plan["source_ref"], plan["text"], version=plan["version"],
                                story_hash=plan["hash"], combat_plan={key: value for key, value in plan.items() if key not in {"text", "block"}},
                                message_start=len(previous_text) - len(plan["text"]))
            word_budget = WriterWordBudget(job.target_words, job.tolerance_words, count_writer_words(input_content))
            word_contract = word_budget.prompt(formal_words=formal_word_count, mode=job.mode)
            if context.experience_prompt:
                previous_text += "\n\n【作者已批准的写作经验，仅为适用范围内的写作参考，不是人物、世界或情节事实】\n" + context.experience_prompt
            experience_start = len(previous_text) - len(context.experience_prompt)
            for item in context.experience_context.get("selected", []):
                capture.add("作者已批准的写作经验（当次）", item["source_ref"], item["content_snapshot"],
                            version=item["version"], experience=item, message_start=experience_start)
                # 经验编译器按原选入次序用单个换行连接，不对整条消息搜索同文。
                experience_start += len(item["content_snapshot"]) + 1
            for item in context.experience_context.get("excluded", []):
                capture.add("作者经验（未入模）", f"memory:{item['memory_id']}", reason=item["reason"], experience=item)
            actual_refs = {item["source_ref"] for item in capture.entries}
            for ref in context.source_refs:
                if ref not in actual_refs:
                    capture.add("项目投影引用" if ref.endswith("projection/bundle.json") else "上下文登记引用", ref,
                                reason="reference_only_no_body")
            user_prefix = f"用户意图：{instruction}\n{word_contract}\n项目上下文摘要：{context_summary}\n目标章节：第{target}章\n以下是最近章节正文片段：\n\n"
            messages = [
                ModelMessage("system", "你是长篇小说 Writer Agent。依据当前请求分析或创作。分析时解释问题、依据与建议；创作时只输出中文小说正文。保持人物连续性和章节因果。"),
                ModelMessage("user", user_prefix + previous_text + f"\n\n{'请只分析问题、依据和建议，不要输出正文，也不要修改任何工作稿。' if job.mode == 'analyze' else f'请按上述整章预算整合创作，输出最终完整章节正文，标题为《第{target}章》。续写时将已有与新增内容整合成一章，改写时输出重组后的完整章节；总量不是新增量。'}"),
            ]
            history = self.conversation(chapter_number)["messages"]
            # 当前用户指令已在末尾上下文中出现；失败重试复用原用户消息。
            source_task = job.job_id
            while self._jobs[source_task].retry_of:
                source_task = self._jobs[source_task].retry_of
            cutoff = next((index for index, item in enumerate(history) if item["task_id"] == source_task), len(history))
            messages[1:1] = [ModelMessage(item["role"], item["content"]) for item in history[:cutoff]]
            if job.story_context and sum(len(message.content) for message in messages) > 100000:
                raise ValueError("required_story_context_budget_exceeded")
            if job.mode == "analyze":
                from creative_os import chapter_agent_tools
                from creative_os.chapter_agent_tools import run_chapter_turn, freeze_analysis_state
                if sum(len(message.content) for message in messages) + len(chapter_agent_tools.PROTOCOL) > 100000:
                    raise ValueError("required_story_context_budget_exceeded")
                for entry in capture.entries:
                    if entry.get("_message_start") is not None:
                        entry["_message_start"] += len(user_prefix)
                self._set(job_id, analysis_state=freeze_analysis_state(job, context, formal_word_count, capture))
                content = run_chapter_turn(self, job, messages, capture)
            else:
                content = RuntimeRunner().execute(
                    RuntimeRequest(
                        task_id=job_id,
                        context_id=context.decision.decision_id,
                        capability="novel-writing-agent",
                        domain="novel",
                        model="writer-agent",
                        messages=tuple(messages),
                        input_refs=tuple(("source_ref", ref) for ref in context.source_refs) + (("project_id", self.project_id), ("session_id", job.session_id), ("chapter_number", str(target)))
                                   + ((("story_source_ref", job.story_context["source_ref"]), ("story_version", str(job.story_context["version"])), ("story_hash", job.story_context["hash"])) if job.story_context else ()),
                        temperature=0.78,
                        max_tokens=12000,
                    ),
                    CapturingModelAdapter(client, lambda actual: self._set(job_id, context_snapshot=capture.snapshot(job, actual, content_offset=len(user_prefix)))),
                ).output
            decision_id = job.decision_id or context.decision.decision_id
            if job.mode == "analyze" or not job.decision_id:
                decision = {"decision_id": decision_id, "intent": instruction, "target_chapter": target,
                            "context_refs": list(context.source_refs), "analysis": str(content) if job.mode == "analyze" else instruction, "created_at": context.decision.created_at,
                            "target_words": job.target_words, "tolerance_words": job.tolerance_words,
                            "min_words": job.min_words, "max_words": job.max_words, "formal_word_count": formal_word_count,
                            "project_id": self.project_id, "session_id": job.session_id, "task_id": job_id}
                self._write_decision(decision_id, decision)
            if job.mode == "analyze":
                self._set(job_id, status="completed", message="分析已完成，正文未修改。", decision_id=decision_id, reply=content)
                return
            with project_authority_lock(self.root):
                proposal = self.proposals.read(proposal["proposal_id"])
                proposal["decision_id"] = decision_id
                self.proposals.write(proposal)
                self._set(job_id, decision_id=decision_id)
            text = str(content)
            word_assessment = word_budget.assess(text)
            actual_words = word_assessment["actual_words"]
            within_word_range = word_assessment["within_word_range"]
            range_message = word_assessment["message"]
            if word_assessment["adjustment_options"]:
                range_message += "。" + "；".join(word_assessment["adjustment_options"])
            self._set(job_id, status="saving_proposal", message=f"候选已生成，{range_message}，正在保存提案。")
            self.proposals.complete(proposal["proposal_id"], text, word_assessment=word_assessment)
            if job.preflight_plan_id:
                self.preflight.update(job.preflight_plan_id, status="consumed")
            self._set(job_id, status="completed", message=f"第{target}章候选提案待审阅，{range_message}。当前正文未修改。", actual_words=actual_words, within_word_range=within_word_range, word_assessment=word_assessment, reply=text)
        except Exception as error:
            current = self.get(job_id)
            if current.proposal_id:
                self.proposals.fail_unfinished(current.proposal_id, str(error))
            if current.preflight_plan_id:
                try:
                    self.preflight.update(current.preflight_plan_id, status="failed", unknowns=(str(error),))
                except (KeyError, OSError, ValueError):
                    pass
            self._set(job_id, status="failed", message=f"Agent 运行失败：{error}", error=str(error), retryable=current.status != "saving")

    def _execute_story_step(self, job, messages, capture, step):
        """受控单步入口；工具循环位于领域模块，透明适配器只观察并原样委派。"""
        client = self.client_factory()
        output = RuntimeRunner().execute(
            RuntimeRequest(task_id=f"{job.job_id}:step:{step}", context_id=job.session_id,
                           capability="combat-expert" if str(step).startswith("combat:") else "story-architecture-agent" if job.scope == "story" else "chapter-analysis-agent", domain="novel", model="writer-agent",
                           messages=tuple(messages), input_refs=(("project_id", self.project_id), ("scope", job.scope), ("session_id", job.session_id), ("step", str(step))),
                           temperature=0.78, max_tokens=5000),
            CapturingModelAdapter(client, lambda actual: self._capture_story_step(job, capture.snapshot(job, actual), step)),
        ).output
        current = self.get(job.job_id)
        snapshots = (*current.step_snapshots[:-1], {**current.step_snapshots[-1], "output": output})
        self._set(job.job_id, step_snapshots=snapshots)
        return output

    def _capture_story_step(self, job, snapshot, step):
        current = self.get(job.job_id)
        self._set(job.job_id, context_snapshot=snapshot, step_snapshots=(*current.step_snapshots, {"step": step, **snapshot}))
