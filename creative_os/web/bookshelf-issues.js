/* 书架异常交互：状态由服务端提供，任何恢复或轮询都只GET。 */
class BookshelfIssues {
  constructor(options = {}) {
    this.doc = options.document || document;
    this.$ = id => this.doc.getElementById(id);
    this.fetch = options.fetch || globalThis.fetch.bind(globalThis);
    try { this.storage = options.storage || globalThis.sessionStorage; } catch (_) { this.storage = null; }
    this.autoPoll = options.autoPoll !== false;
    this.requestId = options.requestId || (() => globalThis.crypto?.randomUUID?.() || "request-" + Date.now() + "-" + (++this.nonce));
    this.nonce = 0; this.issueEpoch = 0; this.previewEpoch = 0; this.statusEpoch = 0;
    this.rows = new Map(); this.previewButtons = []; this.checked = 0; this.nextOffset = 0; this.total = 0;
    this.revision = null; this.stale = false; this.listBusy = false; this.busy = false;
    this.confirmation = null; this.operation = null; this.serverState = null; this.timer = null;
    this.$("view-issues").addEventListener("click", () => this.open());
    this.$("close-issues").addEventListener("click", () => this.close());
    this.$("issues-panel").addEventListener("cancel", event => { event.preventDefault(); this.close(); });
    this.$("recheck-issues").addEventListener("click", () => this.check());
    this.$("more-issues").addEventListener("click", () => this.more());
    this.$("cancel-migration-preview").addEventListener("click", () => this.cancelPreview());
    this.$("confirm-migration").addEventListener("click", () => this.confirm());
    this.$("migration-confirm-check").addEventListener("change", () => this.sync());
    this.$("refresh-migration-status").addEventListener("click", () => this.readStatus());
    this.$("reconcile-migration").addEventListener("click", () => this.reconcile());
    this.$("continue-migration").addEventListener("click", () => this.beginContinue());
    this.$("migration-preview").hidden = true; this.$("migration-operation").hidden = true;
    this.sync();
  }
  async http(url, options = {}) {
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timeout = controller ? setTimeout(() => controller.abort(), 15000) : null;
    try {
      const response = await this.fetch(url, { ...options, ...(controller ? { signal: controller.signal } : {}) });
      let data;
      try { data = await response.json(); } catch (_) { throw new Error("服务返回了无法识别的数据，请稍后重新读取。"); }
      if (!response.ok) {
        const error = new Error(typeof data.error?.message === "string" ? data.error.message : "读取或处理失败，请重新检查。");
        error.status = response.status; error.details = data.error; throw error;
      }
      return data;
    } finally { if (timeout) clearTimeout(timeout); }
  }
  open() {
    if (!this.$("issues-panel").open) this.$("issues-panel").showModal();
    this.$("issues-title").focus();
    return this.check();
  }
  close() {
    this.cancelPreview(false); this.$("issues-panel").close(); this.$("view-issues").focus();
  }
  check() { return this.loadIssues(false); }
  more() { return this.stale || this.listBusy || this.nextOffset >= this.total ? Promise.resolve() : this.loadIssues(true); }
  async loadIssues(append) {
    const epoch = append ? this.issueEpoch : ++this.issueEpoch;
    const offset = append ? this.nextOffset : 0;
    this.listBusy = true; this.$("issues-summary").textContent = "正在检查作品…"; this.sync();
    try {
      const data = await this.http("/api/projects/issues?" + new URLSearchParams({ offset, limit: 20 }));
      if (epoch !== this.issueEpoch) return;
      if (!Array.isArray(data.items) || typeof data.catalog_revision !== "string") throw new Error("invalid");
      if (append && this.revision !== data.catalog_revision) {
        this.stale = true; this.$("issues-summary").textContent = "作品目录已变化，旧详情可能过期。请重新检查。"; return;
      }
      if (!append) { this.rows.clear(); this.checked = 0; }
      this.revision = data.catalog_revision; this.stale = false;
      for (const item of data.items) this.rows.set(JSON.stringify([item.directory, item.project_id, item.code]), item);
      this.total = Number(data.total_projects ?? data.total) || 0;
      this.checked = Math.min(this.total, this.checked + (Number(data.checked_projects) || 0));
      this.nextOffset = Number(data.next_offset ?? offset + 20);
      this.renderRows();
      this.$("issues-summary").textContent = `已检查 ${this.checked} / ${this.total} 部作品；已展开 ${this.rows.size} 项问题。` +
        (this.nextOffset < this.total ? " 还有作品未检查。" : this.rows.size ? " 可逐项查看和处理。" : " 当前未发现可显示的问题。");
    } catch (_) {
      if (epoch === this.issueEpoch) { this.stale = true; this.$("issues-summary").textContent = "检查失败，已保留上次详情；旧详情可能过期，请重新检查。"; }
    } finally { if (epoch === this.issueEpoch) { this.listBusy = false; this.sync(); } }
  }
  element(tag, text, className) {
    const node = this.doc.createElement(tag);
    if (text != null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }
  button(label, action) {
    const node = this.element("button", label); node.type = "button";
    node.addEventListener("click", action); return node;
  }
  renderRows() {
    const list = this.$("issues-list"); list.replaceChildren(); this.previewButtons = [];
    for (const item of this.rows.values()) {
      const row = this.element("article", null, "issue-entry");
      row.append(this.element("h3", item.title), this.element("p", item.message), this.element("p", "影响：" + item.impact, "muted"));
      const count = key => item.known_counts?.[key] == null ? "未知" : item.known_counts[key];
      row.append(this.element("p", `正式稿 ${count("formal")} · 工作稿 ${count("draft")} · 待确认候选 ${count("candidate")}`, "issue-counts"));
      row.append(this.element("p", "目录：" + item.directory, "muted"));
      const actions = this.element("div", null, "issue-actions");
      if (item.actions?.includes("preview_migration") && item.code === "directory_name_mismatch") {
        const button = this.button("预览目录整理", () => this.preview(item.project_id, button));
        this.previewButtons.push(button); actions.append(button);
      }
      if (item.actions?.some(value => ["open", "open_project"].includes(value)) && !["project_unavailable", "project_identity_ambiguous"].includes(item.code)) {
        const link = this.element("a", "打开作品"); link.href = "/p/" + encodeURIComponent(item.project_id) + "/"; actions.append(link);
      }
      row.append(actions); list.append(row);
    }
  }
  async preview(projectId, focus = null) {
    if (this.busy || this.operation && !["verified", "failed"].includes(this.serverState?.stage)) return;
    const epoch = ++this.previewEpoch;
    this.confirmation = null; this.previewFocus = focus; this.$("migration-confirm-check").checked = false;
    this.$("migration-preview").hidden = true; this.sync();
    this.$("migration-note").textContent = "正在读取目录整理预览…";
    try {
      const data = await this.http("/api/projects/migration-preview?" + new URLSearchParams({ project_id: projectId }));
      if (epoch !== this.previewEpoch) return;
      if (!data.available) { this.$("migration-note").textContent = "该目录当前不能整理，请重新检查作品状态。"; return; }
      this.confirmation = { kind: "begin", data }; this.showConfirmation(data);
    } catch (_) { if (epoch === this.previewEpoch) this.$("migration-note").textContent = "预览读取失败，请重新检查；尚未执行迁移。"; }
    this.sync();
  }
  showConfirmation(data) {
    this.$("migration-note").textContent = "请核对以下目录和备份位置；勾选确认后才会执行。";
    this.$("migration-preview").hidden = false;
    this.$("migration-preview-title").textContent = this.confirmation.kind === "begin" ? "确认目录整理" : "再次确认继续本次迁移";
    this.$("migration-preview-details").textContent = `作品 ID：${data.project_id}\n原目录：${data.source_directory}\n目标目录：${data.target_directory}\n备份：${data.backup_directory}`;
    this.$("migration-preview-impact").textContent = this.confirmation.kind === "begin" ?
      `将完整备份并校验后整理目录，稿件和作品 ID 保持不变。${data.file_count} 个文件，${data.directory_count} 个目录。` : "复用本次已经验证的备份，再次检查后继续整理；不会新建另一项迁移。";
    this.$("migration-confirm-check").checked = false;
    this.$("migration-preview-title").focus(); this.sync();
  }
  cancelPreview(focus = true) {
    ++this.previewEpoch; this.confirmation = null;
    this.$("migration-preview").hidden = true; this.$("migration-confirm-check").checked = false;
    if (focus) (this.previewFocus?.isConnected === false ? this.$("view-issues") : this.previewFocus || this.$("view-issues")).focus();
    this.sync();
  }
  async confirm() {
    if (this.busy || !this.confirmation || !this.$("migration-confirm-check").checked) return;
    const { kind, data } = this.confirmation;
    const payload = { plan_fingerprint: data.plan_fingerprint, confirmed: true };
    if (kind === "begin") { payload.operation_id = data.operation_id; payload.preview_token = data.preview_token; }
    else payload.continuation_no = data.continuation_no;
    this.cancelPreview(false);
    return this.submit(kind === "begin" ? "migrate_project_directory" : "continue_project_directory", data, payload);
  }
  beginContinue() {
    if (this.busy || !this.serverState?.actions?.includes("continue")) return;
    this.confirmation = { kind: "continue", data: { ...this.serverState } }; this.showConfirmation(this.confirmation.data);
  }
  reconcile() {
    if (this.busy || !this.serverState?.needs_reconciliation && this.serverState?.stage !== "needs_reconciliation") return;
    return this.submit("reconcile_project_directory", this.serverState, { plan_fingerprint: this.serverState.plan_fingerprint });
  }
  async submit(commandId, data, payload) {
    if (this.busy) return;
    if (this.operation?.operation_id !== data.operation_id) {
      this.serverState = null;
      this.$("migration-status").textContent = "正在读取本次操作状态…";
      this.$("migration-operation-details").textContent = "操作号：" + data.operation_id;
      this.$("reconcile-migration").hidden = true; this.$("continue-migration").hidden = true;
      this.$("migration-open").hidden = true; this.$("migration-reload").textContent = "";
    }
    this.busy = true; this.operation = { operation_id: data.operation_id }; this.$("migration-operation").hidden = false;
    this.$("migration-note").textContent = "请求已发送；下方只展示后端读取到的实际状态。";
    try { this.storage?.setItem("creative-os-directory-operation", data.operation_id); } catch (_) { /* 存储不可用仍可留在本页读取状态。 */ }
    const requestId = this.requestId();
    const suffix = commandId === "migrate_project_directory" ? "migrate" : commandId === "reconcile_project_directory" ? "reconcile" : "continue";
    const key = `directory-${suffix}:${data.operation_id}` + (suffix === "reconcile" ? ":" + requestId : suffix === "continue" ? ":" + payload.continuation_no : "");
    const target = { project_id: data.project_id };
    if (suffix !== "migrate") target.operation_id = data.operation_id;
    const body = { command_id: commandId, request_id: requestId, actor: "作者", target, payload, expected_version: null, idempotency_key: key };
    this.sync();
    const pending = this.http("/api/commands/" + commandId.replaceAll("_", "-"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    void this.readStatus();
    let rejectedBeforeStart = false;
    try { await pending; }
    catch (error) {
      const proof = error.details;
      if (commandId === "migrate_project_directory" && error.status === 409 && proof?.code === "preview_stale" &&
          proof.operation_created === false && proof.operation_id === data.operation_id && proof.project_id === data.project_id) {
        // 仅服务端绑定本次身份的明确拒绝可解锁；404或丢响应不代表未执行。
        rejectedBeforeStart = true; ++this.statusEpoch; clearTimeout(this.timer); this.timer = null;
        this.operation = null; this.serverState = null; this.$("migration-operation").hidden = true;
        try { this.storage?.removeItem("creative-os-directory-operation"); } catch (_) { /* 不影响当前页面重新预览。 */ }
        this.$("migration-note").textContent = "预览已过期，本次整理尚未开始。请重新检查并重新预览。";
      } else this.$("migration-note").textContent = "响应尚未确认，正在读取原操作状态；不会自动重发或创建新操作。";
    }
    finally { if (!rejectedBeforeStart) await this.readStatus(); this.busy = false; this.sync(); }
  }
  async restore() {
    let id;
    try { id = this.storage?.getItem("creative-os-directory-operation"); } catch (_) { return; }
    if (!/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(id || "")) return;
    this.operation = { operation_id: id }; return this.readStatus();
  }
  async readStatus() {
    if (!this.operation) return;
    clearTimeout(this.timer); this.timer = null;
    const id = this.operation.operation_id, epoch = ++this.statusEpoch;
    try {
      const data = await this.http("/api/projects/migrations/" + encodeURIComponent(id));
      if (epoch !== this.statusEpoch || this.operation.operation_id !== id) return;
      if (data.operation_id !== id) throw new Error("invalid");
      if (this.confirmation?.kind === "continue" && (data.continuation_no !== this.confirmation.data.continuation_no || !data.actions?.includes("continue"))) this.cancelPreview(false);
      this.serverState = data; this.renderOperation();
      this.$("migration-note").textContent = "已读取原操作的最新状态，请以下方结果为准。";
      if (this.autoPoll && !["verified", "failed"].includes(data.stage) && !data.needs_reconciliation && !data.actions?.includes("continue")) this.timer = setTimeout(() => this.readStatus(), 1000);
    } catch (_) {
      if (epoch === this.statusEpoch) {
        this.$("migration-operation").hidden = false;
        this.$("migration-note").textContent = "状态读取失败，以上详情可能过期；请重新读取原操作状态，不要重复提交。";
        if (this.autoPoll && this.busy) this.timer = setTimeout(() => this.readStatus(), 1000);
      }
    }
    this.sync();
  }
  renderOperation() {
    const data = this.serverState;
    const labels = { reserved: "已受理，等待备份", backing_up: "正在完整备份并校验", backup_verified: "备份已校验",
      moving: "正在整理目录", verified: "目录处理已完成", failed: "本次处理未完成，原文件和已有备份已保留", needs_reconciliation: "结果待核对，请先核对本次迁移" };
    this.$("migration-operation").hidden = false;
    this.$("migration-status").textContent = labels[data.stage] || "状态暂不可确认，请重新读取。";
    this.$("migration-status").dataset.stage = data.stage;
    this.$("migration-operation-details").textContent = `操作编号：${data.operation_id}\n作品 ID：${data.project_id}\n原目录：${data.source_directory}\n目标目录：${data.target_directory}\n备份：${data.backup_directory}`;
    this.$("reconcile-migration").hidden = !data.needs_reconciliation && data.stage !== "needs_reconciliation";
    this.$("continue-migration").hidden = !data.actions?.includes("continue");
    this.$("migration-open").hidden = data.stage !== "verified";
    this.$("migration-open").href = "/p/" + encodeURIComponent(data.project_id) + "/";
    this.$("migration-reload").textContent = data.stage === "verified" && data.reload_required ? "旧默认入口需要重载服务。可以从下方作品入口重新打开。" : "";
    this.sync();
  }
  sync() {
    this.$("confirm-migration").disabled = this.busy || !this.confirmation || !this.$("migration-confirm-check").checked;
    this.$("migration-confirm-check").disabled = this.busy;
    this.$("cancel-migration-preview").disabled = this.busy;
    this.$("reconcile-migration").disabled = this.busy;
    this.$("continue-migration").disabled = this.busy;
    this.$("more-issues").disabled = this.listBusy || this.stale || this.nextOffset >= this.total;
    for (const button of this.previewButtons) button.disabled = this.busy || Boolean(this.operation && !["verified", "failed"].includes(this.serverState?.stage));
  }
}
if (typeof module !== "undefined") module.exports = { BookshelfIssues };
if (typeof document !== "undefined" && document.getElementById("view-issues")) {
  window.bookshelfIssues = new BookshelfIssues(); void window.bookshelfIssues.restore();
}
