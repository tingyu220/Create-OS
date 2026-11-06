/* 共享书内导航只处理位置和离开保护，不拥有正文或创作命令。 */
class WorkspaceNavigation {
  constructor({ page, isDirty = () => false, beforeLeave = () => {} }) {
    this.page = page; this.isDirty = isDirty; this.beforeLeave = beforeLeave;
    this.projectId = null; this.loadEpoch = 0; this.leaving = false; this.recentQueue = Promise.resolve();
    this.$ = id => document.getElementById(id);
    this.$("project-switch")?.addEventListener("change", () => {
      const id = this.$("project-switch").value;
      const destination = id === "__all__" ? "/" : "/p/" + encodeURIComponent(id) + "/";
      if (!this.go(destination)) this.$("project-switch").value = this.projectId || "";
    });
    document.querySelectorAll("[data-workspace-leave]").forEach(link => link.addEventListener("click", event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); this.go(link.getAttribute("href"));
    }));
    window.addEventListener("beforeunload", event => {
      if (!this.leaving && this.isDirty()) { event.preventDefault(); event.returnValue = ""; }
    });
  }
  async ready(projectId, title) {
    const changed = this.projectId !== projectId;
    this.projectId = projectId;
    const name = this.$("workspace-book-name"); if (name) name.textContent = title || projectId || "未命名新书";
    const prefix = projectId ? "/p/" + encodeURIComponent(projectId) : "";
    if (projectId && !this.legacyShown && ["#overview", "#chapters"].includes(window.location.hash)) {
      this.legacyShown = true;
      this.notice("旧总览入口已移入作品摘要。 ");
      const link = document.createElement("a"); link.textContent = "打开原作品摘要 →";
      const destination = prefix + "/overview" + window.location.hash;
      link.href = destination;
      link.addEventListener("click", event => { event.preventDefault(); this.go(destination); });
      this.$("workspace-notice")?.append(link);
    }
    for (const [id, path] of [["workspace-back", "/"], ["workspace-story-link", prefix + "/story"], ["workspace-writer-link", prefix + "/writer?chapter=1"], ["workspace-overview-link", prefix + "/overview"]]) {
      const link = this.$(id); if (link) link.href = path;
    }
    if (!changed && this.loaded) return;
    const token = ++this.loadEpoch;
    const select = this.$("project-switch");
    if (!select) return;
    try {
      const response = await fetch("/api/projects?limit=20");
      const data = await response.json();
      if (token !== this.loadEpoch) return;
      if (!response.ok) throw new Error("作品列表暂不可用");
      select.replaceChildren();
      const items = [...data.items];
      if (!items.some(item => item.project_id === projectId)) items.unshift({ project_id: projectId || "", title: title || projectId || "未命名新书" });
      items.forEach(item => { const option = document.createElement("option"); option.value = item.project_id; option.textContent = item.title; select.append(option); });
      const more = document.createElement("option"); more.value = "__all__"; more.textContent = "返回全部作品…"; select.append(more);
      select.value = projectId || ""; this.loaded = true;
    } catch (error) {
      if (token === this.loadEpoch) this.notice("作品切换暂不可用，可返回我的作品重新选择。");
    }
  }
  notice(message) {
    const node = this.$("workspace-notice"); if (node) { node.textContent = message; node.hidden = false; }
  }
  go(url, confirmed = false) {
    if (typeof url !== "string" || !url.startsWith("/") || url.startsWith("//")) return false;
    if (!confirmed && this.isDirty() && !window.confirm("有尚未保存的编辑。继续离开将放弃这些编辑，是否继续？")) return false;
    this.beforeLeave(); this.leaving = true; window.location.assign(url); return true;
  }
  opened(location) {
    const projectId = this.projectId;
    if (!projectId) return Promise.resolve();
    const record = { ...location, project_id: projectId };
    const signature = JSON.stringify(record);
    if (this.queuedLocation === signature) return this.recentQueue;
    this.queuedLocation = signature;
    this.recentQueue = this.recentQueue.then(async () => {
      try {
        const response = await fetch("/api/projects/recent", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(record), keepalive: true });
        if (!response.ok) throw new Error("最近位置未记录");
      } catch (error) {
        if (this.queuedLocation === signature) this.queuedLocation = null;
        if (this.projectId === projectId) this.notice("最近位置未记录，当前创作仍可继续；返回书架后也可从全部作品打开。");
      }
    });
    return this.recentQueue;
  }
}

class ChapterDirectory {
  constructor(onSelect) {
    this.onSelect = onSelect; this.items = []; this.filter = "all";
    this.$ = id => document.getElementById(id);
    this.$("chapter-search")?.addEventListener("input", () => this.render());
    document.querySelectorAll("[data-directory-filter]").forEach(button => button.addEventListener("click", () => this.setFilter(button.dataset.directoryFilter)));
  }
  update(items) { this.items = [...items].sort((a, b) => a.chapter_number - b.chapter_number); this.render(); }
  setFilter(filter) { this.filter = filter; this.render(); }
  select(number) { this.selected = number; this.render(); }
  render() {
    const container = this.$("chapter-directory"); if (!container) return;
    const query = (this.$("chapter-search")?.value || "").trim().toLocaleLowerCase();
    const items = this.items.filter(item => (String(item.chapter_number).includes(query) || (item.title || "").toLocaleLowerCase().includes(query))
      && (this.filter === "all" || this.filter === "draft" && item.has_draft || this.filter === "candidate" && item.pending_candidates > 0));
    container.replaceChildren();
    document.querySelectorAll("[data-directory-filter]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.directoryFilter === this.filter)));
    if (!items.length) { const empty = document.createElement("p"); empty.className = "empty-state"; empty.textContent = this.items.length ? "没有匹配的章节" : "还没有章节，可从故事设定开始"; container.append(empty); }
    items.forEach(item => {
      const button = document.createElement("button"); button.type = "button"; button.className = "directory-chapter";
      button.setAttribute("aria-current", String(item.chapter_number === this.selected));
      const title = document.createElement("strong"); title.textContent = item.title || "第 " + item.chapter_number + " 章";
      const meta = document.createElement("small"); meta.textContent = [item.has_formal ? "正式稿" : "", item.has_draft ? "工作稿" : "", item.pending_candidates ? item.pending_candidates + " 份待确认" : ""].filter(Boolean).join(" · ");
      button.append(title, meta);
      button.addEventListener("click", () => this.onSelect(item.chapter_number, item.has_draft ? "draft" : item.has_formal ? "formal" : "auto", this.filter === "candidate" || !item.has_draft && !item.has_formal));
      container.append(button);
    });
  }
}
