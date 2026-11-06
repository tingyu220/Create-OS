/* 作者首页只读展示真实稿件；技术投影仅补充明确阻塞，不能替代稿件事实。 */
const $ = id => document.getElementById(id);
const projectPrefix = window.writerProjectPrefix || "";
const scopedPath = path => projectPrefix + path;
const workspaceNavigation = Object.freeze([
  { id: "overview", label: "总览", href: "#overview" },
  { id: "chapters", label: "章节", href: "#chapters" },
  { id: "writer", label: "写作工作台", href: scopedPath("/writer") },
  { id: "story", label: "故事设定", href: scopedPath("/story") },
]);
let home = null;
let readEpoch = 0;
let projectAttention = [];
let projectAttentionId = "";

function renderWorkspaceNavigation() {
  $("workspace-navigation").replaceChildren();
  workspaceNavigation.forEach(item => {
    const link = document.createElement("a");
    link.className = "nav-item";
    link.href = item.href;
    link.textContent = item.label;
    $("workspace-navigation").append(link);
  });
  updateWorkspaceNavigation();
}

function updateWorkspaceNavigation() {
  const active = window.location.hash === "#chapters" ? "#chapters" : "#overview";
  document.querySelectorAll("[data-navigation-target]").forEach(section => {
    section.hidden = section.dataset.navigationTarget !== active;
  });
  $("workspace-navigation").querySelectorAll("a").forEach(link => {
    if (link.getAttribute("href") === active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  $("page-title").textContent = active === "#chapters" ? "我的章节" : "创作首页";
  document.title = `Creative OS · ${$("page-title").textContent}`;
}

function renderWorkspaceState(state, label, detail = "") {
  $("workspace-state").className = `workspace-state state-${state}`;
  $("workspace-state").querySelector(".status-label").textContent = label;
  $("workspace-state-detail").textContent = detail;
  $("workspace-state-action").hidden = !["error", "partial"].includes(state);
}

function writerLink(number, source = "auto") {
  const selected = ["draft", "formal"].includes(source) ? `&source=${source}` : "";
  return scopedPath(`/writer?chapter=${encodeURIComponent(number)}${selected}`);
}

function manuscriptRow(item) {
  const link = document.createElement("a");
  link.className = "manuscript-row";
  link.href = writerLink(item.chapter_number, item.has_draft ? "draft" : item.has_formal ? "formal" : "auto");
  const main = document.createElement("span");
  const title = document.createElement("strong");
  title.textContent = item.title || `第 ${item.chapter_number} 章`;
  const labels = [];
  if (item.has_formal) labels.push("正式稿");
  if (item.has_draft) labels.push("工作稿");
  if (item.pending_candidates) labels.push(`${item.pending_candidates} 份候选待确认`);
  const meta = document.createElement("span");
  meta.className = "manuscript-meta";
  meta.textContent = labels.join(" · ");
  main.append(title, meta);
  const arrow = document.createElement("span");
  arrow.className = "row-action";
  arrow.textContent = "打开 →";
  link.append(main, arrow);
  return link;
}

function renderChapterMatrix() {
  const query = $("chapter-filter").value.trim();
  const rows = (home?.chapters || []).filter(item => String(item.chapter_number).includes(query));
  $("chapter-filter-count").textContent = home ? `${rows.length} 个章节` : "";
  const list = $("chapter-list");
  list.replaceChildren();
  if (!home) list.textContent = "稿件尚未读取，请刷新后重试。";
  else if (!rows.length) list.textContent = query ? "没有找到这个章节，也可以在首页输入编号打开。" : "还没有稿件，从故事设定开始，或在首页打开第一章。";
  else rows.sort((a, b) => a.chapter_number - b.chapter_number).forEach(item => list.append(manuscriptRow(item)));
}

function renderAttention() {
  const list = $("attention-items");
  list.replaceChildren();
  const scopedAttention = !home || !projectAttentionId || projectAttentionId === home.project_id ? projectAttention : [];
  const items = [...(home?.attention || []), ...scopedAttention];
  (home?.notices || []).forEach(message => items.push({ kind: "notice", message }));
  $("attention-panel").hidden = items.length === 0;
  $("attention-shortcut").hidden = items.length === 0;
  $("attention-shortcut").textContent = `${items.length} 项待处理`;
  items.forEach(item => {
    const row = document.createElement("div");
    row.className = `attention-item attention-${item.kind}`;
    const message = document.createElement("span");
    message.textContent = (item.chapter_number ? `第 ${item.chapter_number} 章 · ` : "") + item.message;
    const link = document.createElement("a");
    const diagnostic = item.kind === "projection" || item.kind === "notice";
    link.href = item.chapter_number ? writerLink(item.chapter_number) : diagnostic ? scopedPath("/inspector") : scopedPath("/story");
    link.textContent = diagnostic ? "查看诊断" : "打开查看";
    row.append(message, link);
    list.append(row);
  });
}

function renderHome(value) {
  home = value;
  $("project-name").textContent = value.title;
  for (const kind of ["formal", "draft", "candidate"]) $(kind + "-count").textContent = value.counts[kind] ?? "—";
  const resume = value.resume;
  const button = $("continue-writing");
  button.removeAttribute("aria-disabled");
  if (resume) {
    $("continue-title").textContent = `继续第 ${resume.chapter_number} 章`;
    $("continue-detail").textContent = resume.source === "candidate" ? "这一章有候选等待你确认。读一读，再决定是否采用。" : resume.source === "draft" ? "工作稿已经保留。打开章节，接着打磨这一段故事。" : "正式稿已经归档。打开章节，阅读或继续修改。";
    button.href = writerLink(resume.chapter_number, resume.source);
    button.textContent = resume.source === "candidate" ? "查看待确认候选" : "继续创作";
  } else {
    $("continue-title").textContent = value.status === "partial" ? "先打开你的创作空间" : "从一个念头，写到第一章";
    $("continue-detail").textContent = value.status === "partial" ? "部分稿件暂时无法读取。你仍可打开章节，或继续讨论故事设定。" : "把灵感说出来，和创作助手一起理清人物、世界与开篇。";
    button.href = scopedPath("/story");
    button.textContent = "继续故事设定";
  }
  const recent = $("recent-manuscripts");
  recent.replaceChildren();
  value.chapters.slice(0, 4).forEach(item => recent.append(manuscriptRow(item)));
  if (!value.chapters.length) recent.textContent = value.status === "partial" ? "暂时无法确认稿件列表，请重新读取或打开运行诊断。" : "还没有稿件。每一次保存的工作稿，都会出现在这里。";
  renderChapterMatrix();
  renderAttention();
  renderWorkspaceState(value.status, value.status === "partial" ? "部分稿件需要核对" : "稿件已同步", value.status === "partial" ? "可继续打开章节，下方保留需要处理的事项。" : "正式稿、工作稿与候选分别统计。数量可同时包含同一章节。");
}

async function readJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("read_failed");
  return response.json();
}

async function loadWorkspace() {
  const token = ++readEpoch;
  $("refresh-workspace").disabled = true;
  renderWorkspaceState("loading", "正在读取稿件", "正在确认正式稿、工作稿与待确认候选。");
  // 两条查询独立完成，诊断不可用时不阻塞稿件和写作入口。
  const manuscriptRead = readJson("/api/author-home").then(value => {
    if (token !== readEpoch) return;
    if (!value || !Array.isArray(value.chapters) || !value.counts || !value.project_id) throw new Error("invalid_summary");
    if (projectPrefix && decodeURIComponent(projectPrefix.slice(3)) !== value.project_id) throw new Error("scope_mismatch");
    renderHome(value);
  }).catch(() => {
    if (token !== readEpoch) return;
    home = null;
    ["formal", "draft", "candidate"].forEach(kind => { $(kind + "-count").textContent = "—"; });
    $("recent-manuscripts").textContent = "稿件读取失败，请重试。";
    $("continue-title").textContent = "稿件暂时无法读取";
    $("continue-detail").textContent = "仍可输入章节编号打开，或继续讨论故事设定。";
    $("continue-writing").href = scopedPath("/writer");
    $("continue-writing").textContent = "打开写作工作台";
    $("continue-writing").removeAttribute("aria-disabled");
    renderChapterMatrix();
    renderAttention();
    renderWorkspaceState("error", "读取失败", "无法确认当前稿件数量，请重新读取。仍可直接打开章节。");
  }).finally(() => { if (token === readEpoch) $("refresh-workspace").disabled = false; });
  const projectionRead = readJson("/api/workspace").then(value => {
    if (token !== readEpoch) return;
    if (home && value.project_id !== home.project_id) return;
    if (projectPrefix && decodeURIComponent(projectPrefix.slice(3)) !== value.project_id) return;
    projectAttentionId = value.project_id;
    const snapshot = value.snapshot;
    const hasBlocker = (snapshot?.overview?.blockers || []).length > 0 || (snapshot?.quality?.issues || []).some(item => item.blocking) || Number(snapshot?.overview?.blocked_chapter_count) > 0;
    projectAttention = hasBlocker ? [{ kind: "projection", message: "项目检查记录了阻塞事项，请查看诊断核对。" }] : [];
    renderAttention();
  }).catch(() => {
    if (token !== readEpoch) return;
    projectAttentionId = "";
    projectAttention = [{ kind: "notice", message: "项目检查暂时无法读取。稿件仍可继续编辑，可打开诊断核对检查状态。" }];
    renderAttention();
  });
  await Promise.allSettled([manuscriptRead, projectionRead]);
}

$("story-link").href = scopedPath("/story");
$("diagnostic-link").href = scopedPath("/inspector");
$("footer-diagnostics").href = scopedPath("/inspector");
$("continue-writing").href = scopedPath("/writer");
renderWorkspaceNavigation();
window.addEventListener("hashchange", updateWorkspaceNavigation);
$("chapter-filter").addEventListener("input", renderChapterMatrix);
$("refresh-workspace").addEventListener("click", loadWorkspace);
$("workspace-state-action").addEventListener("click", loadWorkspace);
$("open-chapter-form").addEventListener("submit", event => {
  event.preventDefault();
  const number = Number($("chapter-number").value);
  if (!Number.isSafeInteger(number) || number < 1) { $("chapter-open-status").textContent = "请输入有效的正整章节编号。"; return; }
  window.location.assign(writerLink(number));
});
loadWorkspace();
