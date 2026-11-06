/* 书架只读取目录和真实最近记录，不在点击或 GET 时更新位置。 */
class Bookshelf {
  constructor() {
    this.$ = id => document.getElementById(id);
    this.offset = 0; this.limit = 20; this.epoch = 0; this.total = 0; this.positions = {}; this.recentKnown = false;
    this.$("book-search").addEventListener("input", () => { this.offset = 0; return this.load(); });
    this.$("refresh-books").addEventListener("click", () => this.load());
    this.$("previous-page").addEventListener("click", () => { this.offset = Math.max(0, this.offset - this.limit); return this.load(); });
    this.$("next-page").addEventListener("click", () => { this.offset += this.limit; return this.load(); });
    this.legacyEntry();
  }
  legacyEntry() {
    const hash = window.location.hash;
    if (!hash || hash === "#all-books" || hash === "#recent-section") return;
    const box = this.$("legacy-entry"); box.hidden = false;
    const match = hash.match(/^#chapter[-_](\d+)$/);
    const link = document.createElement("a"); link.textContent = match ? "打开旧章节入口 →" : "打开原作品摘要 →";
    link.href = match ? "/writer?chapter=" + Number(match[1]) : "/overview" + hash;
    box.textContent = "旧总览入口已移入作品内部。 "; box.append(link);
  }
  async get(url) {
    const response = await fetch(url);
    let data;
    try { data = await response.json(); } catch (_) { throw new Error("读取失败，服务返回了无法识别的数据，请稍后刷新。"); }
    if (!response.ok) throw new Error(data.error?.message || "读取失败，请稍后重试。");
    return data;
  }
  async load() {
    const epoch = ++this.epoch;
    this.$("catalog-status").textContent = "正在读取作品目录…";
    this.$("previous-page").disabled = true; this.$("next-page").disabled = true;
    const query = new URLSearchParams({ query: this.$("book-search").value.trim(), offset: String(this.offset), limit: String(this.limit) });
    const results = await Promise.allSettled([this.get("/api/projects?" + query), this.get("/api/projects/recent")]);
    if (epoch !== this.epoch) return;
    const [catalog, recent] = results;
    this.recentKnown = recent.status === "fulfilled";
    this.positions = this.recentKnown ? (recent.value.positions || Object.fromEntries((recent.value.items || []).map(item => [item.project_id, item]))) : {};
    if (this.recentKnown) this.renderRecent(recent.value);
    else { this.$("recent-books").replaceChildren(); this.$("recent-empty").hidden = true; this.$("recent-status").textContent = recent.reason.message + " 全部作品仍可打开。"; }
    if (catalog.status === "fulfilled") this.renderCatalog(catalog.value);
    else { this.$("book-list").replaceChildren(); this.$("books-empty").hidden = true; this.$("catalog-status").textContent = catalog.reason.message; this.$("catalog-warning").hidden = true; }
  }
  prefix(id) { return "/p/" + encodeURIComponent(id); }
  date(value) {
    if (!value) return this.recentKnown ? "暂无记录" : "记录暂不可用";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "时间暂不可用" : new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
  }
  renderCatalog(data) {
    this.total = data.total;
    const list = this.$("book-list"); list.replaceChildren();
    this.$("book-total").textContent = data.total + " 部作品";
    this.$("catalog-status").textContent = "";
    this.$("catalog-warning").hidden = !(data.warnings || []).length;
    this.$("catalog-warning").textContent = (data.warnings || []).length + " 个作品的目录或摘要需要核对；其余作品可正常打开。";
    this.$("books-empty").hidden = data.items.length > 0;
    this.$("books-empty").textContent = this.$("book-search").value.trim() ? "没有找到匹配的作品。可以换个书名搜索，或从新灵感开始。" : "书架还是空的。点击“新建小说”，从一个灵感开始。";
    data.items.forEach(item => {
      const row = document.createElement("div"); row.className = "book-row";
      const name = document.createElement("span"); name.className = "book-name"; name.textContent = "▤　" + item.title;
      const counts = document.createElement("span"); counts.className = "book-counts";
      const count = key => item.counts?.[key] == null ? "暂不可用" : item.counts[key];
      counts.textContent = count("formal") + " 章正式稿 · " + count("draft") + " 章工作稿 · " + count("candidate") + " 份待确认";
      const opened = document.createElement("span"); opened.className = "book-opened"; opened.textContent = this.date(this.positions[item.project_id]?.opened_at);
      const link = document.createElement("a"); link.className = "book-open"; link.textContent = "打开"; link.href = this.prefix(item.project_id) + "/";
      link.setAttribute("aria-label", "打开作品：" + item.title);
      row.append(name, counts, opened, link); list.append(row);
    });
    this.$("page-status").textContent = data.total ? (this.offset + 1) + "–" + Math.min(this.offset + this.limit, data.total) + " / " + data.total : "0 部作品";
    this.$("previous-page").disabled = this.offset === 0;
    this.$("next-page").disabled = this.offset + this.limit >= data.total;
  }
  renderRecent(data) {
    const list = this.$("recent-books"); list.replaceChildren();
    this.$("recent-status").textContent = data.warnings?.length ? "部分最近作品暂不可用，可从全部作品重新选择。" : "只展示你成功打开过的作品。";
    this.$("recent-empty").hidden = data.items.length > 0;
    this.$("recent-empty").textContent = "还没有最近打开的作品，从下方选择一本开始。";
    data.items.slice(0, 4).forEach(item => {
      const card = document.createElement("article"); card.className = "recent-card";
      const icon = document.createElement("span"); icon.className = "book-symbol"; icon.textContent = "▤"; icon.setAttribute("aria-hidden", "true");
      const copy = document.createElement("div"); copy.className = "recent-copy";
      const title = document.createElement("strong"); title.textContent = item.title;
      const meta = document.createElement("p"); meta.textContent = (item.page === "story" ? "故事构思" : "第 " + item.chapter_number + " 章") + " · " + this.date(item.opened_at);
      const link = document.createElement("a"); link.className = "book-open"; link.textContent = item.page === "story" ? "继续讨论" : "继续创作";
      link.href = this.prefix(item.project_id) + (item.page === "story" ? "/story" : "/writer?" + new URLSearchParams({ chapter: item.chapter_number, source: ["draft", "formal"].includes(item.source) ? item.source : "auto" }));
      copy.append(title, meta); card.append(icon, copy, link); list.append(card);
    });
  }
}
if (typeof document !== "undefined" && document.getElementById("bookshelf-page")) { window.bookshelf = new Bookshelf(); window.bookshelf.load(); }
