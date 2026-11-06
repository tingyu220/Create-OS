/* 经验审阅独立控制器：沿用会话作用域与命令边界，不改编辑器。 */
class WriterLessonReview {
  constructor(conversation) {
    this.conversation = conversation;
    this.$ = conversation.$;
    this.requests = new Map();
    this.data = { feedback: [], lessons: [] };
    this.busy = false;
    this.counter = 0;
    this.$("lesson-create").addEventListener("click", () => this.create());
    this.$("lesson-create").disabled = true;
  }

  render(data, scope) {
    this.data = data || { feedback: [], lessons: [] };
    if (this.scope !== scope) {
      this.scope = scope;
      ["lesson-title", "lesson-content", "lesson-note"].forEach(id => { this.$(id).value = ""; });
      this.$("lesson-range").value = "chapter";
      this.$("lesson-status").textContent = "";
    }
    const selected = this.$("lesson-feedback").value;
    this.$("lesson-feedback").replaceChildren(...this.data.feedback.map(feedback => {
      const option = document.createElement("option");
      option.value = feedback.id;
      const labels = { accepted: "接受", rejected: "拒绝", cancelled: "取消", revised: "继续修改" };
      option.textContent = `${labels[feedback.outcome] || feedback.outcome}：${feedback.reason || "未填写原因，可自行总结具体经验"}`;
      return option;
    }));
    if (this.data.feedback.some(item => item.id === selected)) this.$("lesson-feedback").value = selected;
    this.$("lesson-create").disabled = this.busy || !this.data.feedback.length;
    const labels = { candidate: "待作者确认", active: "已批准 · 后续适用请求可使用", rejected: "已拒绝", archived: "已归档" };
    this.$("lesson-list").replaceChildren(...this.data.lessons.map(item => {
      const node = document.createElement("section");
      node.className = "lesson-item";
      const heading = document.createElement("h3");
      heading.textContent = `${item.title} · ${labels[item.status] || item.status}`;
      const text = document.createElement("p");
      const body = item.detail;
      text.textContent = `${body.range === "project" ? "本项目" : `第${body.chapter_number}章`}：${body.content}`;
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "查看原反馈与提案证据";
      const evidence = document.createElement("pre");
      evidence.textContent = `原反馈：${body.feedback.reason || "未填写原因"}\n反馈：${body.feedback.id}\n提案：${body.proposal_id}\n原稿：${body.base.ref} · 版本 ${body.base.version ?? "无"}\n原稿 SHA256：${body.base.hash}\n候选：${body.result.ref}\n候选 SHA256：${body.result.hash}`;
      details.append(summary, evidence);
      const actions = document.createElement("div");
      actions.className = "review-actions";
      const options = item.status === "candidate" ? [["approve", "批准经验"], ["reject", "拒绝经验"]]
        : ["active", "rejected"].includes(item.status) ? [["archive", "归档经验"]] : [];
      options.forEach(([action, label]) => {
        const button = document.createElement("button");
        button.textContent = label;
        button.disabled = this.busy;
        button.addEventListener("click", () => this.review(item, action));
        actions.append(button);
      });
      node.append(heading, text, details, actions);
      return node;
    }));
    if (!this.data.lessons.length) this.$("lesson-list").textContent = "暂无经验；没有可复用内容时无需创建。";
  }

  create() {
    const feedback = this.data.feedback.find(item => item.id === this.$("lesson-feedback").value);
    if (!feedback) return;
    const title = this.$("lesson-title").value.trim();
    const content = this.$("lesson-content").value.trim();
    if (!title || !content) {
      this.$("lesson-status").textContent = "请填写具体经验及标题；接受或拒绝本身不会成为经验。";
      return;
    }
    return this.execute(feedback, { action: "create", title, content, range: this.$("lesson-range").value });
  }

  review(item, action) {
    const note = this.$("lesson-note").value.trim();
    if (!note) {
      this.$("lesson-status").textContent = "请填写经验审阅说明，再明确批准、拒绝或归档。";
      this.$("lesson-note").focus();
      return;
    }
    return this.execute(item.detail.feedback, { action, memory_id: item.id, version: item.version, note });
  }

  async execute(feedback, payload) {
    const scope = this.scope;
    const conversation = this.conversation;
    if (this.busy || !conversation.scopeValid(scope)) return;
    const target = { project_id: scope.projectId, chapter_number: feedback.chapter_number,
      session_id: feedback.session_id, feedback_id: feedback.id };
    const identity = JSON.stringify({ target, payload });
    if (!this.requests.has(identity)) {
      const requestId = `lesson-${Date.now()}-${++this.counter}`;
      this.requests.set(identity, { command_id: "manage_writer_lesson", request_id: requestId,
        actor: "作者", target, payload, expected_version: null, idempotency_key: requestId });
    }
    this.busy = true;
    this.render(this.data, scope);
    try {
      const response = await fetch("/api/commands/manage-writer-lesson", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(this.requests.get(identity)) });
      const result = await response.json();
      if (!conversation.scopeValid(scope)) return;
      if (!response.ok || result.status !== "accepted") throw new Error(result.error?.message || "经验操作结果未确认，请刷新核对");
      this.$("lesson-status").textContent = payload.action === "create" ? "候选已保存，明确批准后才用于后续请求。" : "经验状态已保存。";
      await conversation.refresh(scope);
    } catch (error) {
      if (conversation.scopeValid(scope)) this.$("lesson-status").textContent = `${error.message}；可用原操作重试核对。`;
    } finally {
      this.busy = false;
      if (conversation.scopeValid(this.scope)) this.render(this.data, this.scope);
    }
  }
}
