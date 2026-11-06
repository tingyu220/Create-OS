const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup(handler) {
  const nodes = new Map();
  const node = () => ({ children: [], events: {}, value: "", textContent: "", hidden: false, disabled: false, dataset: {},
    append(...values) { this.children.push(...values); }, replaceChildren(...values) { this.children = values; },
    setAttribute(key, value) { this[key] = value; }, addEventListener(key, fn) { this.events[key] = fn; } });
  const get = id => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
  const requests = [];
  const window = { location: { hash: "" }, addEventListener() {} };
  const context = vm.createContext({ document: { getElementById: id => id === "bookshelf-page" ? null : get(id), createElement: node },
    window, URLSearchParams, Date, Intl, fetch: async (url, options) => { requests.push({ url, options }); return { ok: true, json: async () => handler(url) }; } });
  vm.runInContext(fs.readFileSync("creative_os/web/app.js", "utf8") + "\nglobalThis.Controller = Bookshelf;", context);
  return { get, requests, controller: new context.Controller() };
}

const book = id => ({ project_id: id, title: id, counts: { formal: 1, draft: 1, candidate: 0 }, notices: [] });

test("全部作品与真实最近记录分开显示，所有操作链接绑定作品", async () => {
  const env = setup(url => url.includes("recent") ? { items: [{ project_id: "旧书", title: "旧书", page: "writer", chapter_number: 3, source: "draft", opened_at: "2026-10-19T02:00:00Z" }], positions: {} } : { items: [book("旧书"), book("新书")], total: 2, warnings: [] });
  await env.controller.load();
  assert.equal(env.get("book-list").children.length, 2);
  assert.equal(env.get("recent-books").children.length, 1);
  const row = env.get("book-list").children[0];
  assert.equal(row.children.at(-1).href, "/p/%E6%97%A7%E4%B9%A6/");
  assert.equal(env.requests.filter(request => request.options?.method === "POST").length, 0);
});

test("没有最近记录用空态，不根据稿件更新时间伪造继续位置", async () => {
  const env = setup(url => url.includes("recent") ? { items: [], positions: {} } : { items: [book("旧书")], total: 1, warnings: [] });
  await env.controller.load();
  assert.match(env.get("recent-empty").textContent, /还没有最近打开/);
  assert.equal(env.get("recent-empty").hidden, false);
});

test("列表错误与空书架不同，部分损坏条目不隐藏有效作品", async () => {
  const env = setup(url => {
    if (url.includes("recent")) return { items: [], positions: {} };
    return { items: [book("有效作品")], total: 1, warnings: [{ project_id: "坏目录", message: "无法读取" }] };
  });
  await env.controller.load();
  assert.equal(env.get("book-list").children.length, 1);
  assert.match(env.get("catalog-warning").textContent, /1/);
  const failed = setup(url => { if (!url.includes("recent")) throw new Error("读取失败"); return { items: [] }; });
  await failed.controller.load();
  assert.match(failed.get("catalog-status").textContent, /读取失败/);
  assert.equal(failed.get("books-empty").hidden, true);
});

test("搜索乱序响应不覆盖新结果，空结果保留新建入口", async () => {
  let release;
  const env = setup(url => {
    if (url.includes("recent")) return { items: [] };
    if (url.includes("query=old")) return new Promise(resolve => { release = resolve; });
    return { items: [], total: 0, warnings: [] };
  });
  env.get("book-search").value = "old"; const older = env.controller.load();
  env.get("book-search").value = "new"; await env.controller.load();
  release({ items: [book("旧响应")], total: 1, warnings: [] }); await older;
  assert.equal(env.get("book-list").children.length, 0);
  assert.equal(env.get("books-empty").hidden, false);
  assert.ok(env.requests.at(-2).url.includes("query=new"));
});
