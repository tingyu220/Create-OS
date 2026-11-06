const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

// 同章有正式稿与工作稿时，入口参数必须决定首次打开来源，且不能触发保存。
async function open(source, failedChapter = false, delayedVersions = false, proposals = null) {
  const nodes = new Map();
  const node = () => ({ dataset: {}, value: "", textContent: "", children: [],
    setAttribute() {}, replaceChildren(...children) { this.children = children; },
    append(child) { this.children.push(child); }, addEventListener() {}, querySelectorAll() { return []; } });
  const get = id => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
  get("chapter-number").value = "1";
  const search = "?chapter=1" + (source === undefined ? "" : `&source=${source}`);
  const requests = [];
  let finishVersions;
  let chooseCandidate, selectedProposal;
  const versionsReady = new Promise(resolve => { finishVersions = resolve; });
  const response = data => ({ ok: true, json: async () => data });
  const context = vm.createContext({
    document: { getElementById: get, createElement: node, querySelectorAll: () => [], querySelector: () => get("grid") },
    URL, URLSearchParams, crypto: require("node:crypto"),
    WriterAgentConversation: class {
      constructor() { this.session = { proposals: proposals || [] }; }
      async open() {}
      async viewProposal(id) { selectedProposal = id; }
    },
    ...(proposals ? { ChapterDirectory: class {
      constructor(callback) { chooseCandidate = callback; this.items = []; }
      update(items) { this.items = items; } select() {}
    } } : {}),
    window: { location: { search, href: "http://localhost/writer" + search },
      history: { replaceState() {} }, setInterval() {}, clearTimeout() {}, setTimeout() {} },
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (url === "/api/workspace") return response({ project_id: "book" });
      if (url === "/api/writer/context") return response({ formal_chapters: [1], working_draft_chapters: [1] });
      if (url.endsWith("/versions")) { if (delayedVersions) await versionsReady; return response({ versions: [{ version: 1 }] }); }
      if (url.startsWith("/api/writer/chapters/1?source=")) {
        if (failedChapter) return { ok: false, json: async () => ({ error: "unavailable" }) };
        const draft = url.endsWith("source=draft");
        return response({ chapter: { project_id: "book", chapter_number: 1, title: "第一章",
          content: draft ? "工作稿正文" : "正式稿正文", version: draft ? { version: 1 } : null,
          source: { editable: draft, label: draft ? "工作稿" : "正式稿" } } });
      }
      throw new Error(`未模拟：${url}`);
    },
  });
  vm.runInContext(fs.readFileSync("creative_os/web/writer.js", "utf8"), context);
  for (let index = 0; index < 40; index++) await Promise.resolve();
  return { requests, content: get("editor").value, disabled: get("editor").disabled, status: get("source-status").textContent, get, finishVersions, chooseCandidate, selectedProposal: () => selectedProposal };
}

test("章节加载失败在正文分面显示错误且不保存", async () => {
  const result = await open("draft", true);
  assert.match(result.status, /章节读取失败/);
  assert.equal(result.disabled, true);
  assert(result.requests.every(item => !item.options?.method || item.options.method === "GET"));
});

test("迟到版本列表不抢回作者已经切换的分面", async () => {
  const result = await open("draft", false, true);
  result.get("grid").dataset.activePanel = "navigation";
  result.finishVersions();
  for (let index = 0; index < 20; index++) await Promise.resolve();
  assert.equal(result.get("grid").dataset.activePanel, "navigation");
});

for (const state of ["pending", "reviewing", "accepted-recovery"]) {
  test(`待确认目录定位${state}，较新已处理历史不抢占`, async () => {
    const active = { proposal_id: "active", chapter_number: 1, status: state === "accepted-recovery" ? "accepted" : state,
      result: { content: "待处理原候选" }, ...(state === "accepted-recovery" ? { review_recovery: { required: true } } : {}) };
    const history = ["accepted", "rejected", "cancelled"].map(status => ({ proposal_id: status, chapter_number: 1, status, result: { content: "历史候选" } }));
    const result = await open("draft", false, false, [active, ...history]);
    await result.chooseCandidate(1, "draft", true);
    assert.equal(result.selectedProposal(), "active");
    assert(result.requests.every(item => !item.options?.method || item.options.method === "GET"));
  });
}

for (const [source, expectedSource, content] of [["draft", "draft", "工作稿正文"], ["formal", "formal", "正式稿正文"],
  [undefined, "auto", "正式稿正文"], ["invalid", "auto", "正式稿正文"]]) {
  test(`初始来源 ${source ?? "缺省"} 正确打开并保持只读加载`, async () => {
    const result = await open(source);
    assert.equal(result.content, content);
    assert(result.requests.some(item => item.url === `/api/writer/chapters/1?source=${expectedSource}`));
    assert(result.requests.every(item => !item.options?.method || item.options.method === "GET"));
  });
}
