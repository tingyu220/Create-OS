const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup() {
  const nodes = new Map(), calls = [], locations = [], events = {};
  const node = () => ({ children: [], value: "", textContent: "", hidden: false, dataset: {}, events: {},
    append(...values) { this.children.push(...values); }, replaceChildren(...values) { this.children = values; },
    setAttribute(key, value) { this[key] = value; }, getAttribute(key) { return this[key]; }, addEventListener(key, value) { this.events[key] = value; } });
  const get = id => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
  let confirm = false, failRecent = false;
  const links = [get("workspace-back"), get("workspace-story-link"), get("workspace-writer-link"), get("workspace-overview-link")];
  const filters = ["all", "draft", "candidate"].map(value => { const item = node(); item.dataset.directoryFilter = value; return item; });
  const window = { location: { assign: value => locations.push(value) }, confirm: () => confirm, addEventListener: (key, fn) => { events[key] = fn; } };
  const context = vm.createContext({ window, URLSearchParams, document: { getElementById: get, createElement: node, querySelectorAll: selector => selector.includes("directory-filter") ? filters : links },
    fetch: async (url, options) => { calls.push({ url, options }); return { ok: !options || !failRecent, json: async () => options ? { record: {} } : { items: [{ project_id: "book-a", title: "甲书" }, { project_id: "book-b", title: "乙书" }], total: 2 } }; } });
  vm.runInContext(fs.readFileSync("creative_os/web/workspace-navigation.js", "utf8") + "\nglobalThis.Navigation = WorkspaceNavigation; globalThis.Directory = ChapterDirectory;", context);
  return { get, calls, locations, events, context, window, setConfirm(value) { confirm = value; }, failRecent() { failRecent = true; } };
}

test("切书保护先提示，取消不离开、不隐式保存，确认后使用完整项目URL", async () => {
  const env = setup(); let dirty = true;
  const nav = new env.context.Navigation({ page: "writer", isDirty: () => dirty });
  await nav.ready("book-a", "甲书");
  assert.equal(env.calls.filter(call => call.options?.method === "POST").length, 0);
  assert.equal(nav.go("/p/book-b/"), false); assert.deepEqual(env.locations, []);
  env.setConfirm(true); assert.equal(nav.go("/p/book-b/"), true);
  assert.deepEqual(env.locations, ["/p/book-b/"]);
  assert.equal(env.calls.filter(call => call.options?.method === "POST").length, 0);
});

test("成功打开才显式记录，记录失败非阻塞且保留真实项目和稿件来源", async () => {
  const env = setup(); const nav = new env.context.Navigation({ page: "writer" });
  await nav.ready("book-a", "甲书"); env.failRecent();
  await nav.opened({ page: "writer", chapter_number: 3, source: "draft" });
  const post = env.calls.find(call => call.options?.method === "POST");
  assert.equal(post.url, "/api/projects/recent");
  assert.deepEqual(JSON.parse(post.options.body), { project_id: "book-a", page: "writer", chapter_number: 3, source: "draft" });
  assert.match(env.get("workspace-notice").textContent, /最近位置/);
  assert.equal(nav.go("/"), true);
});

test("目录按真实标题编号及稿件类型筛选，待确认只定位候选", () => {
  const env = setup(), selected = [];
  const directory = new env.context.Directory((...args) => selected.push(args));
  directory.update([{ chapter_number: 1, title: "第1章 钟声", has_formal: true, has_draft: true, pending_candidates: 0 },
    { chapter_number: 2, title: "第2章 海风", has_formal: false, has_draft: false, pending_candidates: 1 }]);
  directory.setFilter("draft"); assert.equal(env.get("chapter-directory").children.length, 1);
  env.get("chapter-search").value = "钟声"; directory.render(); assert.equal(env.get("chapter-directory").children.length, 1);
  env.get("chapter-search").value = ""; directory.setFilter("candidate");
  const button = env.get("chapter-directory").children[0]; button.events.click();
  assert.deepEqual(selected[0], [2, "auto", true]);
});

test("浏览器离开保护不提交创作命令", async () => {
  const env = setup(); const nav = new env.context.Navigation({ page: "story", isDirty: () => true });
  await nav.ready("book-a", "甲书");
  let prevented = false; const event = { preventDefault() { prevented = true; } };
  env.events.beforeunload(event);
  assert.equal(prevented, true); assert.equal(event.returnValue, "");
  assert.equal(env.calls.filter(call => call.options?.method === "POST").length, 0);
});

test("旧作品章节锚点提供绑定本书的摘要入口并保留离开保护", async () => {
  const env = setup(); env.window.location.hash = "#chapters";
  const nav = new env.context.Navigation({ page: "writer", isDirty: () => true });
  await nav.ready("book-a", "甲书");
  const link = env.get("workspace-notice").children[0];
  assert.equal(link?.href, "/p/book-a/overview#chapters");
  link.events.click({ preventDefault() {} });
  assert.deepEqual(env.locations, []);
  env.setConfirm(true); link.events.click({ preventDefault() {} });
  assert.deepEqual(env.locations, ["/p/book-a/overview#chapters"]);
  assert.equal(env.calls.filter(call => call.options?.method === "POST").length, 0);
});
