/* 章节对话控制器：消息来自持久会话，运行状态独立展示。 */
class WriterAgentConversation {
  constructor({ chapter, wordTarget, onDraft, onProposal = async () => {}, onSource = () => {}, beforeExecute = async () => true }) {
    this.chapter = chapter;
    this.wordTarget = wordTarget;
    this.onDraft = onDraft;
    this.onProposal = onProposal;
    this.beforeExecute = beforeExecute;
    this.epoch = 0;
    this.timer = null;
    this.session = null;
    this.handled = new Set();
    this.reviewRequests = new Map();
    this.requestCounter = 0;
    this.proposalEpoch = 0;
    this.reviewing = false;
    this.refreshEpoch = 0;
    this.$ = id => document.getElementById(id);
    this.reconcileButton = document.createElement("button");
    this.reconcileButton.id = "reconcile-agent-review";
    this.reconcileButton.type = "button";
    this.reconcileButton.textContent = "核对原审阅操作";
    this.reconcileButton.hidden = true;
    this.reconcileButton.addEventListener("click", () => this.reconcileReview());
    this.reconcileActions = document.createElement("div");
    this.reconcileActions.className = "review-actions";
    this.reconcileActions.hidden = true;
    this.reconcileActions.append(this.reconcileButton);
    this.$("agent-proposal-summary").insertAdjacentElement("afterend", this.reconcileActions);
    this.progress = new WriterAgentProgress(this);
    this.$("agent-refresh-status").addEventListener("click", () => {
      if (this.scope && this.scopeValid(this.scope)) this.refresh(this.scope);
    });
    this.lessonReview = typeof WriterLessonReview === "undefined" ? null : new WriterLessonReview(this);
    this.sources = typeof WriterContextSources === "undefined" ? null : new WriterContextSources(this, onSource);
    this.combat = typeof CombatPanel === "undefined" ? null : new CombatPanel({ projectId: null, chapter: this.chapter, submit: (instruction, mode, options) => this.submit(instruction, mode, options), onStatus: text => { this.$("agent-state-text").textContent = text; } });
    this.$("combat-expert-entry")?.addEventListener("click", () => this.combat?.request("请战斗场景编排专家读取本章上下文，确定是否需要战斗或对抗场景；如需要，给出可直接写入本章候选的场景目标、敌我行动链、关键转折、技术或能力约束、代价、节奏节点和后续伏笔；如不需要，说明替代的冲突推进安排。"));
  }

  scopeValid(scope) {
    return scope.epoch === this.epoch && scope.chapter === this.chapter();
  }

  async open(projectId) {
    window.clearTimeout(this.timer);
    const scope = { projectId, chapter: this.chapter(), epoch: ++this.epoch };
    this.scope = scope;
    this.progress.reset();
    this.sources?.reset();
    this.lessonReview?.render(undefined, scope);
    this.session = null;
    this.selectedProposalId = null;
    this.proposalEpoch++;
    this.$("agent-thread").replaceChildren();
    delete this.$("agent-thread").dataset.signature;
    this.$("agent-task-status").replaceChildren();
    this.$("agent-session-actions").replaceChildren();
    this.$("agent-review-actions").hidden = true;
    this.$("agent-proposal-list").replaceChildren();
    this.$("agent-proposal-summary").textContent = "";
    this.reconcileButton.hidden = true;
    this.reconcileActions.hidden = true;
    this.setBusy(true);
    await this.refresh(scope, true);
  }

  setBusy(busy) {
    busy = !!(busy || this.reviewing || this.progress.queryError || (this.pendingRequest && this.scopeValid(this.pendingRequest)));
    this.busy = busy;
    const reason = busy ? this.progress.busyReason() : "";
    const buttons = ["agent-send", "agent-check", "agent-continue"].map(id => this.$(id));
    buttons.push(...this.$("agent-session-actions").querySelectorAll("button"), ...this.$("agent-review-actions").querySelectorAll("button"));
    buttons.push(this.reconcileButton);
    buttons.forEach(button => { button.disabled = busy; button.title = reason; button.setAttribute("aria-describedby", "agent-action-reason"); });
    this.$("agent-action-reason").textContent = reason;
  }

  async refresh(scope, initial = false) {
    if (!this.scopeValid(scope)) return;
    initial = initial || !this.session;
    window.clearTimeout(this.timer);
    const refreshEpoch = ++this.refreshEpoch;
    try {
      const response = await fetch(`/api/agent/conversations/${scope.chapter}?project_id=${encodeURIComponent(scope.projectId)}`);
      if (!response.ok) throw new Error(`会话读取失败（${response.status}）`);
      const session = await response.json();
      if (!this.scopeValid(scope) || refreshEpoch !== this.refreshEpoch) return;
      if (session.project_id !== scope.projectId || session.chapter_number !== scope.chapter) throw new Error("会话章节不匹配");
      this.session = session;
      if (this.combat) { this.combat.projectId = scope.projectId; this.combat.render(session.jobs.flatMap(job => job.combat_results || [])); }
      this.lessonReview?.render(session.lesson_review, scope);
      const signature = JSON.stringify(session.messages);
      if (this.$("agent-thread").dataset.signature !== signature) {
        this.$("agent-thread").replaceChildren(...session.messages.map(message => {
          const node = document.createElement("p");
          node.dataset.messageId = message.message_id;
          node.textContent = `${message.role === "user" ? "你" : "Agent"}：${message.content}`;
          if (this.sources) node.append(this.sourceButton(message.task_id, scope));
          return node;
        }));
        this.$("agent-thread").dataset.signature = signature;
      }
      const active = session.jobs.some(job => !["completed", "failed"].includes(job.status));
      this.renderStatus(session);
      this.renderActions(session, scope);
      this.renderProposals(session, scope);
      this.setBusy(active);
      // 初次恢复只还原对话；只对本次页面观察到完成的任务打开新工作稿。
      for (const job of session.jobs) {
        if ((initial && job.status === "completed") || job.status === "failed") this.handled.add(job.job_id);
        if (job.status === "completed" && !this.handled.has(job.job_id)) {
          this.handled.add(job.job_id);
          if (job.draft_version != null) await this.onDraft(job, () => this.scopeValid(scope));
          if (job.proposal_id) await this.viewProposal(job.proposal_id, scope);
        }
      }
      if (active && this.scopeValid(scope)) this.schedule(scope);
    } catch (error) {
      if (!this.scopeValid(scope) || refreshEpoch !== this.refreshEpoch) return;
      this.$("agent-state-text").textContent = `状态查询暂不可用：${error.message}`;
      this.progress.queryError = true;
      this.progress.tick(scope);
      this.setBusy(true);
      this.schedule(scope);
    }
  }

  schedule(scope) {
    window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => this.refresh(scope), 1500);
  }

  renderStatus(session) {
    const latest = session.jobs.at(-1);
    this.$("agent-state-text").textContent = latest ? this.progress.label(latest) : "可以开始对话";
    this.progress.update(latest, this.scope);
    if (latest?.status === "completed" && latest.word_assessment?.severity === "significant") {
      this.$("agent-state-text").textContent = "已完成 · 字数显著偏离，待作者审阅";
    }
    this.$("agent-task-status").replaceChildren(...session.jobs.map(job => {
      const node = document.createElement("p");
      node.dataset.taskId = job.job_id;
      const actual = job.actual_words == null ? "" : ` · 实际 ${job.actual_words} 字`;
      node.textContent = `${this.progress.label(job)}：${job.error || job.message}${actual}\n任务：${job.job_id} · ${job.updated_at || "未记录更新时间"}`;
      if (this.sources) node.append(this.sourceButton(job.job_id, this.scope));
      return node;
    }));
  }

  sourceButton(jobId, scope) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "source-task-button";
    button.textContent = "查看当次来源";
    button.addEventListener("click", () => this.sources.selectJob(jobId, scope));
    return button;
  }

  renderActions(session, scope) {
    const actions = this.$("agent-session-actions");
    actions.replaceChildren();
    const latest = session.jobs.at(-1);
    if (!latest) return;
    const button = document.createElement("button");
    if (latest.status === "failed" && latest.retryable) {
      button.textContent = "重试失败任务";
      button.addEventListener("click", () => this.request(`/api/agent/jobs/${latest.job_id}/retry`, {}, scope));
    } else if (latest.status === "completed" && latest.decision_id && !latest.proposal_id) {
      button.id = "agent-act";
      button.className = "primary";
      button.textContent = latest.mode === "act" ? "按补充要求再次修改" : "按此方案修改";
      button.addEventListener("click", () => {
        this.executeDecision(latest.decision_id, scope);
      });
    } else return;
    actions.append(button);
  }

  async executeDecision(decisionId, scope = this.scope) {
    if (!this.scopeValid(scope) || !await this.beforeExecute() || !this.scopeValid(scope)) return;
    if (!window.confirm("确认让 Agent 按此方案及补充要求生成独立候选提案？")) return;
    return this.request("/api/agent/decisions/act", { decision_id: decisionId, actor: "作者", feedback: this.$("decision-feedback").value }, scope);
  }

  async revise() {
    return this.review("revise");
  }

  renderProposals(session, scope) {
    const proposals = session.proposals || [];
    if (!proposals.some(item => item.proposal_id === this.selectedProposalId)) this.selectedProposalId = proposals.at(-1)?.proposal_id;
    const labels = { generating: "生成中", failed: "生成失败", pending: "待审阅", reviewing: "审阅结果核对中", accepted: "已接受为工作稿", rejected: "已拒绝", cancelled: "已取消", revised: "已按要求继续修改" };
    const selected = proposals.find(item => item.proposal_id === this.selectedProposalId);
    this.$("agent-proposal-list").replaceChildren(...proposals.map((proposal, index) => {
      const button = document.createElement("button");
      button.textContent = `候选 ${index + 1} · ${labels[proposal.status] || proposal.status} · 阅读与差异`;
      button.disabled = !proposal.result;
      button.title = button.disabled ? (proposal.status === "failed" ? "候选生成失败，请查看任务原因及可用的重试操作。" : "候选正文尚未生成，请等待本章任务完成。") : "打开候选正文和冻结差异";
      button.addEventListener("click", () => this.viewProposal(proposal.proposal_id, scope));
      return button;
    }));
    const recovery = selected?.review_recovery;
    this.reconcileButton.hidden = !recovery?.required;
    this.reconcileActions.hidden = !recovery?.required;
    this.$("agent-review-actions").hidden = selected?.status !== "pending" || !!recovery?.required;
    this.$("agent-proposal-summary").textContent = selected ? `${labels[selected.status] || selected.status} · ${selected.proposal_id}${selected.review?.identity?.reason ? ` · 原因：${selected.review.identity.reason}` : ""}` : "";
    if (selected?.status === "generating") this.$("agent-proposal-summary").textContent += " · 正文生成后即可阅读与审阅，请查看上方任务状态。";
    if (recovery?.required) this.$("agent-proposal-summary").textContent += ` · 原审阅操作待核对，将沿用${recovery.actor}已记录的决定补齐保存、反馈和回执。`;
    if (selected?.word_assessment) {
      const report = selected.word_assessment;
      this.$("agent-proposal-summary").textContent += ` · ${report.message}。${(report.adjustment_options || []).join("；")}`;
    }
  }

  async viewProposal(proposalId, scope = this.scope) {
    if (!this.scopeValid(scope)) return;
    const epoch = ++this.proposalEpoch;
    try {
      const query = new URLSearchParams({ project_id: scope.projectId, chapter_number: scope.chapter, session_id: this.session.session_id });
      const response = await fetch(`/api/agent/proposals/${proposalId}?${query}`);
      const proposal = await response.json();
      if (!this.scopeValid(scope) || epoch !== this.proposalEpoch) return;
      if (!response.ok || proposal.project_id !== scope.projectId || proposal.chapter_number !== scope.chapter || proposal.session_id !== this.session.session_id || proposal.proposal_id !== proposalId) throw new Error("候选提案读取失败或作用域不匹配");
      this.selectedProposalId = proposalId;
      this.renderProposals(this.session, scope);
      await this.onProposal(proposal, () => this.scopeValid(scope) && epoch === this.proposalEpoch);
    } catch (error) {
      if (this.scopeValid(scope) && epoch === this.proposalEpoch) this.$("agent-state-text").textContent = error.message;
    }
  }

  async review(action) {
    const scope = this.scope;
    const proposal = this.session?.proposals?.find(item => item.proposal_id === this.selectedProposalId);
    if (!scope || !this.scopeValid(scope) || this.busy || this.reviewing || proposal?.status !== "pending" || proposal.review_recovery?.required) return;
    const reason = this.$("decision-feedback").value.trim();
    if (action !== "accept" && !reason) {
      this.$("decision-feedback").focus();
      this.$("agent-state-text").textContent = "请填写审阅原因或继续修改要求";
      return;
    }
    const source = this.$("proposal-source").value || "candidate";
    const target = { project_id: scope.projectId, chapter_number: scope.chapter, session_id: this.session.session_id, proposal_id: proposal.proposal_id };
    const payload = { action, reason, ...(action === "revise" ? { source } : {}) };
    this.reviewing = true;
    this.setBusy(true);
    try {
      if (!await this.beforeExecute() || !this.scopeValid(scope)) return;
      const identity = JSON.stringify({ target, payload });
      if (!this.reviewRequests.has(identity)) {
        const requestId = `review-${proposal.proposal_id}-${Date.now()}-${++this.requestCounter}`;
        this.reviewRequests.set(identity, { command_id: "review_writer_proposal", request_id: requestId, actor: "作者", target, payload, expected_version: null, idempotency_key: requestId });
      }
      const response = await fetch("/api/commands/review-writer-proposal", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(this.reviewRequests.get(identity)) });
      const result = await response.json();
      if (!this.scopeValid(scope)) return;
      if (!response.ok || result.status !== "accepted") throw new Error(result.error?.message || "审阅结果未确认，请核对提案状态");
      if (action === "accept") await this.onDraft({ chapter_number: scope.chapter, proposal_id: proposal.proposal_id }, () => this.scopeValid(scope));
      await this.refresh(scope);
    } catch (error) {
      if (!this.scopeValid(scope)) return;
      this.$("agent-state-text").textContent = error.message;
      // 响应不明时仅查询提案；不自动重新发起写作或审阅。
      this.schedule(scope);
    } finally {
      this.reviewing = false;
      this.setBusy(this.session?.jobs.some(job => !["completed", "failed"].includes(job.status)) || false);
    }
  }

  async reconcileReview() {
    const scope = this.scope;
    const proposal = this.session?.proposals?.find(item => item.proposal_id === this.selectedProposalId);
    const recovery = proposal?.review_recovery;
    if (!scope || !this.scopeValid(scope) || this.busy || this.reviewing || !recovery?.required) return;
    const target = { project_id: scope.projectId, chapter_number: scope.chapter, session_id: this.session.session_id, proposal_id: proposal.proposal_id };
    const identity = JSON.stringify({ command: "reconcile_writer_proposal", target, actor: recovery.actor, payload: recovery.payload });
    if (!this.reviewRequests.has(identity)) {
      const key = `reconcile-${proposal.proposal_id}-${Date.now()}-${++this.requestCounter}`;
      this.reviewRequests.set(identity, { command_id: "reconcile_writer_proposal", request_id: key, actor: recovery.actor,
        target, payload: recovery.payload, expected_version: null, idempotency_key: key });
    }
    this.reviewing = true;
    this.setBusy(true);
    try {
      const response = await fetch("/api/commands/reconcile-writer-proposal", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(this.reviewRequests.get(identity)) });
      const result = await response.json();
      if (!this.scopeValid(scope)) return;
      await this.refresh(scope);
      if (!response.ok || result.status !== "accepted") throw new Error(result.error?.message || "原审阅结果仍待核对");
      this.$("agent-state-text").textContent = "原审阅操作已核对；编辑器当前内容保持不变。";
    } catch (error) {
      if (!this.scopeValid(scope)) return;
      this.$("agent-state-text").textContent = error.message;
      this.schedule(scope);
    } finally {
      this.reviewing = false;
      this.setBusy(this.session?.jobs.some(job => !["completed", "failed"].includes(job.status)) || false);
    }
  }

  async request(url, payload, scope = this.scope) {
    if (!scope || !this.scopeValid(scope) || !this.session || this.busy) return;
    this.pendingRequest = scope;
    this.setBusy(true);
    window.clearTimeout(this.timer);
    try {
      const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...payload, project_id: scope.projectId, chapter_number: scope.chapter, session_id: this.session.session_id }) });
      const data = await response.json();
      if (!this.scopeValid(scope)) return;
      this.pendingRequest = null;
      if (!response.ok) throw new Error(data.error?.message || "请求未能受理");
      if (url === "/api/agent/intents") this.$("agent-instruction").value = "";
      await this.refresh(scope);
    } catch (error) {
      if (!this.scopeValid(scope)) return;
      this.$("agent-state-text").textContent = `${error.message}。正在核对任务状态，请勿重复发送。`;
      // 请求结果不确定时只重新查询；不会自动重复付费请求。
      this.schedule(scope);
    } finally {
      if (this.pendingRequest === scope) this.pendingRequest = null;
    }
  }

  async submit(instruction, mode = "analyze", options = {}) {
    if (!instruction.trim()) {
      this.$("agent-state-text").textContent = "请直接告诉 Agent 你的目标。";
      return;
    }
    return this.request("/api/agent/intents", { instruction, actor: "作者", mode, ...this.wordTarget(), ...options });
  }
}
