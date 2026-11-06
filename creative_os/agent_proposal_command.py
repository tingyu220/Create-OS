"""作者审阅命令：冻结提案是唯一目标，Feedback 是追加事实。"""

from dataclasses import replace
from uuid import uuid4
from creative_os.agent_proposal_store import find_review

from creative_os.domains.project_authority import project_authority_lock
from creative_os.memory.feedback import FeedbackOutcome, FeedbackRecord, FeedbackStore
from creative_os.workspace_command import (CommandRejectedError, CommandResult, CommandStatus,
                                          CommandRecordState, FileCommandResultStore, CommandError,
                                          CommandBoundary, ReserveStatus)


class AgentProposalCommandBoundary(CommandBoundary):
    """仅为可按检查点恢复的提案审阅续办保留请求，不改变通用边界语义。"""

    def execute(self, request):
        # 锁覆盖 reserve→审阅意图→副作用→回执，排除仍在执行的原请求。
        with project_authority_lock(self._handler.runtime.root):
            return super().execute(request)

    def _reservation_result(self, outcome, request):
        if outcome.status is ReserveStatus.RESERVED and outcome.record is not None:
            # reserve 已验证原指纹；保留原记录，仅在领域证据允许时续办同一请求。
            try:
                if self._handler.can_resume_reserved(request):
                    return None
            except Exception:
                # 证据不可读就保留原 reservation，不能推定无副作用。
                pass
        return super()._reservation_result(outcome, request)


class AgentProposalCommandHandler:
    def __init__(self, runtime) -> None:
        self.runtime = runtime
        self.store = runtime.proposals

    def validate(self, request) -> None:
        if request.command_id not in {"review_writer_proposal", "reconcile_writer_proposal"}:
            raise CommandRejectedError("command_not_allowed", "当前命令不属于提案审阅。")
        target, payload = request.target, request.payload
        if not isinstance(target, dict) or set(target) != {"project_id", "chapter_number", "session_id", "proposal_id"}:
            raise CommandRejectedError("proposal_scope_mismatch", "提案目标必须包含项目、章节、会话及提案。")
        if target["project_id"] != self.runtime.project_id or type(target["chapter_number"]) is not int or target["chapter_number"] <= 0:
            raise CommandRejectedError("proposal_scope_mismatch", "提案所属项目或章节不匹配。")
        if request.command_id == "reconcile_writer_proposal":
            if request.expected_version is not None or set(payload) != {"feedback_id", "review_hash"} or any(not isinstance(value, str) or not value.strip() for value in payload.values()):
                raise CommandRejectedError("validation_failed", "核对必须明确绑定原反馈编号及审阅指纹。")
            review = find_review(self._scoped(target), payload)
            if review is None or request.actor != review["actor"] or not review["commands"]:
                raise CommandRejectedError("proposal_review_identity_mismatch", "原审阅身份或作者不匹配。")
            records = FileCommandResultStore(self.runtime.root)
            if any(records.read(command["key"]) is None for command in review["commands"]):
                raise CommandRejectedError("proposal_review_evidence_missing", "原审阅命令记录缺失，不能推定操作结果。")
            return
        if request.expected_version is not None or set(payload) - {"action", "reason", "source"}:
            raise CommandRejectedError("validation_failed", "提案使用冻结基线校验，审阅载荷无效。")
        if payload.get("action") not in {"accept", "reject", "cancel", "revise"} or not isinstance(payload.get("reason", ""), str):
            raise CommandRejectedError("validation_failed", "审阅操作或原因无效。")
        if payload["action"] != "accept" and not payload.get("reason", "").strip():
            raise CommandRejectedError("validation_failed", "请填写拒绝、取消或继续修改的原因。")
        if payload["action"] == "revise" and payload.get("source") not in {"candidate", "base"}:
            raise CommandRejectedError("validation_failed", "继续修改必须明确选择候选或冻结原稿。")
        if payload["action"] != "revise" and "source" in payload:
            raise CommandRejectedError("validation_failed", "仅继续修改支持指定来源。")
        self._scoped(target)

    def _scoped(self, target):
        try:
            proposal = self.store.read(target["proposal_id"])
        except (FileNotFoundError, ValueError, TypeError) as error:
            raise CommandRejectedError("proposal_not_found", "提案不存在。") from error
        if any(proposal[key] != target[key] for key in ("project_id", "chapter_number", "session_id")):
            raise CommandRejectedError("proposal_scope_mismatch", "提案所属项目、章节或会话不匹配。")
        return proposal

    def can_resume_reserved(self, request) -> bool:
        """调用方持有项目锁；既有意图可幂等续办，缺意图时须排除未归属副作用。"""
        proposal = self._scoped(request.target)
        if proposal["review"] is not None:
            return True
        if proposal["status"] != "pending":
            return False
        proposal_id = proposal["proposal_id"]
        if self.runtime.store.saved_operation(proposal["chapter_number"], proposal_id) is not None:
            return False
        jobs = self.runtime.conversations.read(proposal["chapter_number"])["jobs"].values()
        if any(job.get("parent_proposal_id") == proposal_id for job in jobs):
            return False
        feedback_path = self.runtime.root / ".creative_os" / "runtime" / "feedback.jsonl"
        if feedback_path.exists() and any(record.proposal_id == proposal_id for record in FeedbackStore(self.runtime.root).list()):
            return False
        # 本处理器总先持久化 review 才落稿、建后继任务或反馈；无这些证据才可从头续办。
        return True

    def __call__(self, request):
        self.validate(request)
        if request.command_id == "reconcile_writer_proposal":
            with project_authority_lock(self.runtime.root):
                proposal = self._scoped(request.target)
                review = find_review(proposal, request.payload)
                command = {"key": request.idempotency_key or request.request_id, "request_id": request.request_id,
                           "command_id": "reconcile_writer_proposal"}
                if command not in review["commands"]:
                    review["commands"].append(command)
                    self.store.write(proposal)
                return self._reconcile(proposal, review, skip_key=command["key"])
        with project_authority_lock(self.runtime.root):
            proposal = self._scoped(request.target)
            action = request.payload["action"]
            reason = request.payload.get("reason", "").strip()
            identity = {"action": action, "reason": reason, "source": request.payload.get("source")}
            command = {"key": request.idempotency_key or request.request_id, "request_id": request.request_id}
            review = proposal["review"]
            if review:
                if review["identity"] != identity:
                    raise CommandRejectedError("proposal_already_reviewed", "该提案已记录另一项审阅决定。")
            else:
                if proposal["status"] != "pending" or proposal["result"] is None:
                    raise CommandRejectedError("proposal_not_ready", "提案尚未生成完成。")
                if action == "accept":
                    current = self.store.baseline(proposal["chapter_number"])
                    if any(current[key] != proposal["base"][key] for key in ("source", "version", "hash")):
                        raise CommandRejectedError("proposal_base_conflict", "原稿已被修改，此提案不能覆盖当前正文，请基于当前稿重新生成。")
                if action == "revise":
                    session = self.runtime.conversations.read(proposal["chapter_number"])
                    if any(job["status"] not in {"completed", "failed"} for job in session["jobs"].values()):
                        raise CommandRejectedError("session_busy", "本章已有任务正在运行。")
                outcomes = {"accept": FeedbackOutcome.ACCEPTED, "reject": FeedbackOutcome.REJECTED,
                            "cancel": FeedbackOutcome.CANCELLED, "revise": FeedbackOutcome.REVISED}
                feedback = FeedbackRecord.new(project_id=proposal["project_id"], task_id=proposal["task_id"],
                                              result_ref=proposal["result"]["ref"], outcome=outcomes[action],
                                              reason=reason, chapter_number=proposal["chapter_number"])
                feedback = replace(feedback, proposal_id=proposal["proposal_id"], session_id=proposal["session_id"],
                                   message_id=proposal["message_id"], decision_id=proposal["decision_id"],
                                   base_ref=proposal["base"]["ref"], base_hash=proposal["base"]["hash"],
                                   result_hash=proposal["result"]["hash"])
                review = {"identity": identity, "actor": request.actor, "feedback": feedback.to_dict(),
                          "job_id": f"agent-{uuid4().hex}" if action == "revise" else None, "event_refs": [],
                          "commands": [command]}
                if action == "revise":
                    review["feedback"]["revision_ref"] = f"agent-job:{review['job_id']}"
                proposal["review"] = review
                proposal["status"] = "reviewing"
                # 先落审阅意图，重启或响应失败后副作用可按稳定编号核对。
                self.store.write(proposal)
            if command not in review["commands"]:
                review["commands"].append(command)
                self.store.write(proposal)
            try:
                return self._finish(proposal)
            except CommandRejectedError as rejected:
                self._reject_review_attempt(proposal, rejected)
                raise

    def _reject_review_attempt(self, proposal, rejected):
        proposal.setdefault("review_attempts", []).append({**proposal["review"], "error": rejected.code})
        proposal["review"] = None
        proposal["status"] = "pending"
        self.store.write(proposal)

    def _finish(self, proposal):
        review = proposal["review"]
        if proposal["status"] != "reviewing":
            return tuple(review["event_refs"])
        action = review["identity"]["action"]
        refs = [f"writer-proposal:{proposal['proposal_id']}:{action}"]
        if action == "accept":
            if review.get("draft_version") is None:
                if self.runtime.store.saved_operation(proposal["chapter_number"], proposal["proposal_id"]) is None:
                    current = self.store.baseline(proposal["chapter_number"])
                    if any(current[key] != proposal["base"][key] for key in ("source", "version", "hash")):
                        raise CommandRejectedError("proposal_base_conflict", "恢复审阅时发现原稿变化，禁止覆盖当前正文。")
                version = self.runtime.store.save(proposal["chapter_number"], proposal["result"]["content"],
                                                  actor=review["actor"], expected_version=proposal["base"]["version"],
                                                  operation_id=proposal["proposal_id"])
                # 新版本以 operation_id 证明已应用；同内容接受以 draft_version 落盘为提交点。
                # 此回执写入前中断且无新版本时，只有审阅意图，恢复必须重新校验基线。
                review["draft_version"] = version.version
                self.store.write(proposal)
            refs.append(f"writer-draft:{proposal['chapter_number']}:{review['draft_version']}")
        elif action == "revise":
            job = self.runtime.get(review["job_id"])
            if job is None:
                original = self.runtime.get(proposal["task_id"])
                job = self.runtime.submit(
                    f"依据指定{('候选' if review['identity']['source'] == 'candidate' else '冻结原稿')}继续修改。作者要求：{review['identity']['reason']}",
                    proposal["chapter_number"], review["actor"], mode="act", session_id=proposal["session_id"],
                    target_words=original.target_words, tolerance_words=original.tolerance_words,
                    decision_id=proposal["decision_id"], parent_proposal_id=proposal["proposal_id"],
                    proposal_source=review["identity"]["source"], job_id=review["job_id"])
            refs.append(f"agent-job:{job.job_id}")
        # 后续 LessonCandidate 可明确消费这条记录；此处仅保存事实，不激活经验。
        FeedbackStore(self.runtime.root).append_once(FeedbackRecord.from_dict(review["feedback"]))
        refs.append(f"feedback:{review['feedback']['id']}")
        review["event_refs"] = refs
        proposal["status"] = {"accept": "accepted", "reject": "rejected", "cancel": "cancelled", "revise": "revised"}[action]
        self.store.write(proposal)
        return tuple(refs)

    def _reconcile(self, proposal, review, *, skip_key=None):
        """与启动恢复共用单个原审阅的幂等完成路径，不扫描或接管其它对象。"""
        error = CommandError(review["error"], "原审阅因基线冲突已拒绝，未覆盖当前稿。", False) if review.get("error") else None
        try:
            if error is None and proposal["review"] is review and proposal["status"] == "reviewing":
                self._finish(proposal)
        except CommandRejectedError as rejected:
            error = CommandError(rejected.code, rejected.message, rejected.retryable)
            self._reject_review_attempt(proposal, rejected)
        commands = FileCommandResultStore(self.runtime.root)
        for command in review["commands"]:
            record = commands.read(command["key"])
            if command["key"] != skip_key and record and record.state is CommandRecordState.RESERVED:
                result = CommandResult(CommandStatus.REJECTED if error else CommandStatus.ACCEPTED,
                                       command.get("command_id", "review_writer_proposal"), command["request_id"], error=error,
                                       emitted_event_refs=tuple(review["event_refs"]))
                commands.complete(command["key"], record.fingerprint, result)
        if error:
            raise CommandRejectedError(error.code, error.message, error.retryable)
        return tuple(review["event_refs"])

    def recover(self):
        with project_authority_lock(self.runtime.root):
            for path in self.store.root.glob("proposal-*.json"):
                proposal = self.store.read(path.stem)
                if proposal["review"]:
                    try:
                        self._reconcile(proposal, proposal["review"])
                    except CommandRejectedError:
                        pass
