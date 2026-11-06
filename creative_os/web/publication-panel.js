(() => {
  const STATUS_LABELS = { ready_to_publish: "待发布", checking: "检查中", filling: "填充中", publishing: "发布中", published: "已发布", paused: "已暂停", failed: "检查失败", unknown: "需核对", version_conflict: "版本冲突" };
  class PublicationPanel {
    constructor(options = {}) {
      this.document = options.document || document;
      this.fetchImpl = options.fetchImpl || (typeof fetch === "function" ? fetch : null);
      this.endpoint = options.endpoint || "/api/publication";
      this.getScope = options.getScope || (() => null);
      this.getSnapshot = options.getSnapshot || null;
      this.scope = null; this.operationId = null;
      this.ids = ["publication-status", "publication-meta", "publication-step", "publication-evidence", "publication-error", "publication-run", "publication-pause-safe", "publication-pause-immediate", "publication-continue", "publication-reconcile"];
      this.bind();
    }
    $(id) { return this.document.getElementById(id); }
    bind() {
      this.$("publication-pause-scope"); this.$("publication-pause-step");
      const action = (id, payload) => { const node = this.$(id); if (node && node.addEventListener) node.addEventListener("click", () => this.control(payload)); };
      action("publication-run", { action: "run" });
      action("publication-pause-safe", { action: "pause", mode: "safe" });
      action("publication-pause-immediate", { action: "pause", mode: "immediate" });
      action("publication-continue", { action: "continue" });
      action("publication-reconcile", { action: "reconcile" });
    }
    setScope(scope) {
      const next = scope || null;
      const keepDeepLink = !this.scope && this.operationId;
      if (!next || !this.scope || next.projectId !== this.scope.projectId || next.chapter !== this.scope.chapter || next.epoch !== this.scope.epoch) this.clear();
      if (keepDeepLink) this.operationId = keepDeepLink;
      this.scope = next;
    }
    clear() {
      this.operationId = null;
      this.ids.forEach(id => { const node = this.$(id); if (!node) return; if ("disabled" in node) node.disabled = false; node.textContent = ""; if (node.replaceChildren) node.replaceChildren(); });
      const run = this.$("publication-run"); if (run) run.disabled = false;
    }
    _belongs(data) { const scope = this.getScope() || this.scope; return !!scope && data && String(data.book_id) === String(scope.projectId) && Number(data.chapter_number) === Number(scope.chapter); }
    render(data) {
      if (!this._belongs(data)) return false;
      this.operationId = data.operation_id || this.operationId;
      const versionConflict = data.status === "version_conflict" || data.pause_reason === "version_conflict";
      this.$("publication-status").textContent = STATUS_LABELS[versionConflict ? "version_conflict" : data.status] || String(data.status || "状态未知");
      this.$("publication-meta").textContent = `作品：${data.book_id || "—"} · 章节：${data.chapter_number ?? "—"} · 正式稿版本：${data.source_revision || "—"} · 正文哈希：${data.content_sha256 || "—"}`;
      this.$("publication-step").textContent = `当前步骤：${data.current_step || "—"}`;
      this.$("publication-evidence").textContent = data.evidence ? JSON.stringify(data.evidence) : "暂无证据";
      const failed = data.pause_reason || (data.checks && Object.keys(data.checks).filter(key => data.checks[key] === false).join(", "));
      this.$("publication-error").textContent = data.error || (failed ? `阻断原因：${failed}` : "");
      const terminal = data.status === "published" || versionConflict;
      const run = this.$("publication-run"); if (run) run.disabled = terminal || data.status === "failed";
      return true;
    }
    async refresh() {
      const scope = this.getScope() || this.scope; if (!scope || !this.fetchImpl) return null;
      const op = this.operationId; if (!op) return null;
      try { const response = await this.fetchImpl(`${this.endpoint}?operation_id=${encodeURIComponent(op)}`); const data = await response.json(); if (response.ok !== false) this.render(data); return data; }
      catch (error) { this.$("publication-error").textContent = "发布状态暂不可用，请稍后重试"; return null; }
    }
    async control(payload) {
      const scope = this.getScope() || this.scope; if (!scope || !this.fetchImpl) return null;
      if (payload.action === "run" && !this.operationId && this.getSnapshot) {
        const snapshot = this.getSnapshot();
        const submit = await this.control({ action: "submit", ...snapshot });
        if (!submit || !submit.operation_id) return submit;
        this.operationId = submit.operation_id;
      }
      const selectedScope = this.$("publication-pause-scope")?.value || "chapter";
      const body = { ...payload, operation_id: this.operationId, book_id: scope.projectId, chapter_number: scope.chapter };
      if (payload.action === "pause" || payload.action === "continue") {
        body.scope = selectedScope;
        if (selectedScope === "global") { delete body.book_id; delete body.chapter_number; delete body.operation_id; }
        if (selectedScope === "book") { delete body.operation_id; }
        if (selectedScope === "step") body.step = this.$("publication-pause-step")?.value || "";
      }
      try { const response = await this.fetchImpl(this.endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); const data = await response.json(); if (response.ok !== false && data.error == null) this.render(data); else this.$("publication-error").textContent = String(data.error || "发布控制失败"); return data; }
      catch (error) { this.$("publication-error").textContent = String(error.message || "发布控制失败"); return null; }
    }
  }
  globalThis.PublicationPanel = PublicationPanel;
})();
