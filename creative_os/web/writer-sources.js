/* 来源只经任务 Query 读取；代次同时隔离切章、切任务与切来源的迟到响应。 */
class WriterContextSources {
  constructor(conversation, onOpen = () => {}) {
    this.owner = conversation;
    this.onOpen = onOpen;
    this.epoch = 0;
    this.$ = id => document.getElementById(id);
  }

  reset() {
    this.epoch++;
    this.jobId = null;
    this.$("agent-source-list").replaceChildren();
    this.$("source-detail").replaceChildren();
    this.$("source-detail-status").textContent = "从 Agent 消息或任务选择当次来源。";
  }

  valid(scope, epoch) {
    return this.owner.scopeValid(scope) && epoch === this.epoch;
  }

  async read(jobId, scope, sourceId) {
    const sessionId = this.owner.session?.session_id;
    const query = new URLSearchParams({ project_id: scope.projectId, chapter_number: scope.chapter, session_id: sessionId });
    if (sourceId) query.set("source_id", sourceId);
    const response = await fetch(`/api/agent/jobs/${encodeURIComponent(jobId)}/context-sources?${query}`);
    const data = await response.json();
    if (!response.ok) throw new Error("当次来源读取失败，请重新选择任务。");
    if (data.project_id !== scope.projectId || data.chapter_number !== scope.chapter || data.session_id !== sessionId || data.job_id !== jobId || (sourceId && data.source?.source_id !== sourceId)) throw new Error("来源归属不匹配。");
    return data;
  }

  async selectJob(jobId, scope = this.owner.scope) {
    if (!scope || !this.owner.scopeValid(scope) || !this.owner.session?.jobs.some(job => job.job_id === jobId)) return;
    const epoch = ++this.epoch;
    this.jobId = jobId;
    this.$("agent-source-list").textContent = "正在读取当次来源…";
    this.$("source-detail").replaceChildren();
    this.$("source-detail-status").textContent = "正在读取当次来源…";
    try {
      const data = await this.read(jobId, scope);
      if (!this.valid(scope, epoch)) return;
      const heading = document.createElement("p");
      heading.textContent = `当次来源 · ${jobId}`;
      this.$("agent-source-list").replaceChildren(heading, ...data.sources.map(source => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.sourceId = source.source_id;
        button.textContent = `${source.label} · ${this.usage(source.usage)}`;
        button.addEventListener("click", () => this.selectSource(jobId, source.source_id, scope));
        return button;
      }));
      if (data.sources.length) await this.selectSource(jobId, data.sources[0].source_id, scope);
      else this.$("source-detail-status").textContent = "本任务暂无来源记录。";
    } catch (error) {
      if (!this.valid(scope, epoch)) return;
      this.$("agent-source-list").textContent = error.message;
      this.$("source-detail-status").textContent = error.message;
    }
  }

  usage(value) {
    return { included: "当次入模", not_in_model: "未入模", unavailable: "快照不可用", recorded: "旧任务选入记录" }[value] || "状态未知";
  }

  reason(value) {
    return { budget_exceeded: "超出经验预算，整条排除", chapter_scope_mismatch: "不适用本章", reference_only_no_body: "仅登记来源引用，未读取或发送正文", frozen_input_replaced_body: "正文由冻结输入替代；正式稿可能仅用于字数统计", legacy_snapshot_missing: "任务没有保存当次内容快照，无法还原历史输入", legacy_selection_only: "仅有经验选入快照，缺少完整调用快照，送达情况未知" }[value] || value;
  }

  async selectSource(jobId, sourceId, scope = this.owner.scope) {
    if (!scope || !this.owner.scopeValid(scope) || this.jobId !== jobId) return;
    const epoch = ++this.epoch;
    this.$("source-detail").replaceChildren();
    this.$("source-detail-status").textContent = "正在读取来源片段…";
    this.onOpen();
    try {
      const data = await this.read(jobId, scope, sourceId);
      if (!this.valid(scope, epoch)) return;
      const source = data.source;
      this.$("source-detail-status").textContent = `${this.usage(source.usage)} · 第${data.chapter_number}章`;
      const root = this.$("source-detail");
      const heading = document.createElement("h3");
      heading.textContent = source.label;
      root.append(heading);
      const line = (label, value, target = root) => {
        const node = document.createElement("p");
        node.textContent = `${label}：${value}`;
        target.append(node);
      };
      line("历史说明", "这是当次调用记录，不代表资料当前状态或经验当前是否已归档。");
      if (source.reason) line("使用说明", this.reason(source.reason));
      line("版本", source.version ?? "无独立版本，以当次内容哈希标识");
      if (source.excerpt_start != null) line("截断范围", `${source.truncated ? "已截断" : "完整内容"} · 字符 [${source.excerpt_start}, ${source.excerpt_end}) / ${source.original_chars}（从 0 起）`);
      const content = document.createElement("pre");
      content.className = "source-content";
      content.textContent = source.content_snapshot ?? "没有可展示的当次正文；不会读取当前文件补作历史内容。";
      root.append(content);
      const metadata = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "来源与校验信息";
      metadata.append(summary);
      line("任务", jobId, metadata);
      line("会话", data.session_id, metadata);
      if (data.delivery === "adapter_call_started") line("调用状态", "已开始模型适配器调用；调用失败或中断时，远端接收情况未知。", metadata);
      if (data.captured_at) line("记录时间", data.captured_at, metadata);
      if (source.source_ref) line("来源标识", source.source_ref, metadata);
      if (source.content_hash) line("片段 SHA256", source.content_hash, metadata);
      if (source.original_hash) line("原内容 SHA256", source.original_hash, metadata);
      if (source.message_location) line("消息位置", `第 ${source.message_location.index + 1} 条 · ${source.message_location.role} · 字符 [${source.message_location.start}, ${source.message_location.end})`, metadata);
      root.append(metadata);
      if (source.experience) {
        const evidence = document.createElement("details");
        const title = document.createElement("summary");
        title.textContent = "当次经验依据与选择原因";
        const body = document.createElement("pre");
        body.textContent = JSON.stringify(source.experience, null, 2);
        evidence.append(title, body);
        root.append(evidence);
      }
      this.$("agent-source-list").querySelectorAll("button").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.sourceId === sourceId)));
    } catch (error) {
      if (this.valid(scope, epoch)) this.$("source-detail-status").textContent = error.message;
    }
  }
}
