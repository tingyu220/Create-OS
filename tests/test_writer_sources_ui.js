const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup() {
  const nodes = new Map();
  const node = () => ({ dataset: {}, children: [], events: {}, attributes: {}, textContent: "",
    replaceChildren(...items) { this.children = items; this.textContent = ""; },
    append(...items) { this.children.push(...items); },
    querySelectorAll() { return this.children.filter(child => child.dataset.sourceId); },
    setAttribute(key, value) { this.attributes[key] = value; },
    addEventListener(key, fn) { this.events[key] = fn; } });
  const document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); }, createElement: node };
  const scope = { projectId: "p", chapter: 1, epoch: 1 };
  const owner = { scope, session: { session_id: "s1", jobs: [{ job_id: "a" }, { job_id: "b" }] }, scopeValid(value) { return value === this.scope; } };
  let handler;
  let opened = 0;
  const requests = [];
  const answer = (jobId, sourceId) => ({ project_id: "p", chapter_number: 1, session_id: "s1", job_id: jobId, delivery: "adapter_call_started",
    ...(sourceId ? { source: { source_id: sourceId, label: `${jobId}-${sourceId}`, usage: "included", content_snapshot: `<script>${jobId}-${sourceId}</script>` } } :
      { sources: [{ source_id: "source-0001", label: "当次稿件", usage: "included" }, { source_id: "source-0002", label: "投影", usage: "not_in_model" }] }) });
  const context = vm.createContext({ document, URLSearchParams, fetch: async url => {
    requests.push(url);
    const parsed = new URL(url, "http://localhost");
    const jobId = parsed.pathname.split("/")[4];
    const sourceId = parsed.searchParams.get("source_id");
    return handler?.(jobId, sourceId) || { ok: true, json: async () => answer(jobId, sourceId) };
  } });
  vm.runInContext(fs.readFileSync("creative_os/web/writer-sources.js", "utf8") + "\nglobalThis.Controller = WriterContextSources;", context);
  const controller = new context.Controller(owner, () => opened++);
  controller.reset();
  return { controller, owner, scope, nodes, requests, answer, get opened() { return opened; }, setHandler(fn) { handler = fn; } };
}

test("通过完整作用域 Query 阅读片段，保留未入模状态，正文按纯文本显示", async () => {
  const env = setup();
  await env.controller.selectJob("a");
  assert.equal(env.opened, 1);
  assert.match(env.requests[0], /project_id=p&chapter_number=1&session_id=s1/);
  const list = env.nodes.get("agent-source-list").children;
  assert.match(list[2].textContent, /未入模/);
  assert.equal(env.nodes.get("source-detail").children.find(child => child.className === "source-content").textContent, "<script>a-source-0001</script>");
  assert.equal(list[1].attributes["aria-pressed"], "true");
  await env.controller.selectJob("unknown");
  assert.equal(env.requests.length, 2);
});

test("切任务后迟到的旧来源列表不覆盖新任务", async () => {
  const env = setup(); let resolve;
  env.setHandler((job, source) => job === "a" && !source ? new Promise(done => { resolve = done; }) : null);
  const pending = env.controller.selectJob("a");
  await env.controller.selectJob("b");
  resolve({ ok: true, json: async () => env.answer("a") });
  await pending;
  assert.match(env.nodes.get("source-detail").children[0].textContent, /^b-/);
  assert.match(env.nodes.get("agent-source-list").children[0].textContent, /b/);
});

test("切来源与切章均隔离迟到的详情响应", async () => {
  const env = setup();
  await env.controller.selectJob("a"); let resolve;
  env.setHandler((job, source) => source === "source-0001" ? new Promise(done => { resolve = done; }) : null);
  const pending = env.controller.selectSource("a", "source-0001");
  await env.controller.selectSource("a", "source-0002");
  resolve({ ok: true, json: async () => env.answer("a", "source-0001") }); await pending;
  assert.match(env.nodes.get("source-detail").children[0].textContent, /source-0002/);
  const old = env.controller.selectSource("a", "source-0001");
  env.owner.scope = { projectId: "p", chapter: 2, epoch: 2 };
  env.controller.reset();
  resolve({ ok: true, json: async () => env.answer("a", "source-0001") }); await old;
  assert.equal(env.nodes.get("source-detail").children.length, 0);
  assert.match(env.nodes.get("source-detail-status").textContent, /选择当次来源/);
});

test("归属不符与请求失败不展示正文，未入模和旧快照不补读文件", async () => {
  const env = setup();
  env.setHandler((job, source) => ({ ok: true, json: async () => ({ ...env.answer(job, source), project_id: "foreign" }) }));
  await env.controller.selectJob("a");
  assert.match(env.nodes.get("source-detail-status").textContent, /归属不匹配/);
  assert.equal(env.nodes.get("source-detail").children.length, 0);
  env.setHandler((job, source) => ({ ok: true, json: async () => source ? { ...env.answer(job, source), source: { source_id: source, usage: "not_in_model", reason: "budget_exceeded", label: "经验" } } : env.answer(job) }));
  await env.controller.selectJob("a");
  const root = env.nodes.get("source-detail");
  assert.match(root.children.find(child => child.className === "source-content").textContent, /没有可展示/);
  assert.match(root.children.map(child => child.textContent).join(""), /整条排除/);
  assert.ok(env.requests.every(url => url.includes("/context-sources?")));
});
