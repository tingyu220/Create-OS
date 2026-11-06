/* 运行进度只展示持久时间；本地计时不发请求，不推测模型进度。 */
class WriterAgentProgress {
  constructor(owner) {
    this.owner = owner;
    this.timer = null;
    this.job = null;
    this.queryError = false;
  }

  active(job = this.job) {
    return !!job && !["completed", "failed"].includes(job.status);
  }

  label(job) {
    if (job.status === "thinking") return job.mode === "analyze" ? "正在分析本章" : "正在生成候选";
    return { queued: "等待执行", reading_context: "正在读取上下文", saving: "正在保存工作稿", saving_proposal: "正在保存候选提案", completed: "已完成", failed: "运行失败" }[job.status] || job.status;
  }

  reset() {
    window.clearTimeout(this.timer);
    this.job = null;
    this.queryError = false;
    this.owner.$("agent-progress-time").textContent = "";
    this.owner.$("agent-progress-note").textContent = "";
  }

  update(job, scope) {
    this.job = job;
    this.queryError = false;
    this.tick(scope);
  }

  timestamp(value) {
    const parsed = typeof value === "string" && value ? Date.parse(value) : NaN;
    return Number.isFinite(parsed) ? parsed : null;
  }

  duration(milliseconds) {
    const seconds = Math.floor(Math.max(0, milliseconds) / 1000);
    return `${Math.floor(seconds / 60)}分${String(seconds % 60).padStart(2, "0")}秒`;
  }

  tick(scope) {
    if (!this.owner.scopeValid(scope)) return;
    window.clearTimeout(this.timer);
    const job = this.job;
    const time = this.owner.$("agent-progress-time");
    const note = this.owner.$("agent-progress-note");
    if (!job) { time.textContent = ""; note.textContent = ""; return; }
    const now = Date.now();
    const start = this.timestamp(job.started_at);
    const changed = this.timestamp(job.status_updated_at);
    const updated = this.timestamp(job.updated_at);
    const end = this.active() ? now : updated;
    time.textContent = start === null ? "旧任务未记录开始时间，无法计算总用时" : end === null || end < start ? "任务时间不可核对，暂无法计算用时" : `${this.active() ? "已用时" : "用时"} ${this.duration(end - start)}`;
    if (changed !== null) {
      time.textContent += ` · 最近状态更新 ${new Date(changed).toLocaleTimeString("zh-CN", { hour12: false })}`;
    } else if (updated !== null) {
      time.textContent += ` · 最近任务记录 ${new Date(updated).toLocaleTimeString("zh-CN", { hour12: false })}（旧任务未记录状态时间）`;
    }
    note.textContent = "";
    if (this.queryError) {
      note.textContent = "状态查询暂不可用，尚未确认任务完成或失败。将自动重新查询，也可点“查看状态”；请勿重复发送。";
    } else if (this.active() && changed !== null && now - changed >= 60000) {
      const waiting = job.status === "thinking" ? "仍在等待模型服务响应" : "仍在等待当前阶段更新";
      note.textContent = `状态已 ${this.duration(now - changed)} 未变化，${waiting}。可点“查看状态”重新查询。`;
    } else if (this.active() && changed === null) {
      note.textContent = "未记录阶段时间；正在查询任务状态。";
    }
    // 与网络轮询分离，网络暂不可用时也保持真实经过时间。
    if (this.active()) this.timer = window.setTimeout(() => this.tick(scope), 1000);
  }

  busyReason() {
    if (this.owner.reviewing) return "正在核对候选审阅结果，请等待操作完成。";
    if (this.queryError) return "任务状态尚未确认，暂不能提交新任务；请查看状态，避免重复发送。";
    if (this.active()) return "本章任务正在运行，完成后可继续操作；暂不支持中断。可编辑补充要求，或查看已有候选和来源。";
    return "正在提交或核对本章任务，请等待确认，避免重复发送。";
  }
}
