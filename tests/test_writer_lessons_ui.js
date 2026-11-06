const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup() {
  const nodes = new Map();
  const node = () => ({ value: "", textContent: "", children: [], events: {}, focus() {},
    replaceChildren(...items) { this.children = items; }, append(...items) { this.children.push(...items); },
    addEventListener(event, callback) { this.events[event] = callback; } });
  const document = { createElement: node, getElementById(id) { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); } };
  let scope = { projectId: "p", chapter: 1, epoch: 1 };
  const requests = [];
  let response = async () => ({ ok: true, json: async () => ({ status: "accepted" }) });
  let refreshes = 0;
  const conversation = { $: id => document.getElementById(id), scopeValid: value => value === scope,
    refresh: async () => { refreshes++; } };
  const context = vm.createContext({ document, fetch: async (url, options) => {
    requests.push({ url, body: JSON.parse(options.body) }); return response();
  } });
  vm.runInContext(fs.readFileSync("creative_os/web/writer-lessons.js", "utf8") + "\nglobalThis.Controller = WriterLessonReview;", context);
  const controller = new context.Controller(conversation);
  const feedback = { id: "f", project_id: "p", chapter_number: 1, session_id: "s", reason: "动机不足", outcome: "rejected" };
  const item = { id: "lesson", title: "动机", status: "candidate", version: 1,
    detail: { content: "用动作承载动机", chapter_number: 1, range: "chapter", feedback, proposal_id: "proposal",
      base: { ref: "base", hash: "base-hash", version: 1 }, result: { ref: "result", hash: "result-hash" } } };
  const data = { feedback: [feedback], lessons: [item] };
  controller.render(data, scope);
  return { nodes, controller, requests, data, item, get refreshes() { return refreshes; },
    setScope(value) { scope = value; controller.render(data, scope); }, setResponse(value) { response = value; } };
}

test("无具体内容不创建经验，原反馈与证据可以阅读", async () => {
  const env = setup();
  env.nodes.get("lesson-feedback").value = "f";
  await env.controller.create();
  assert.equal(env.requests.length, 0);
  assert.match(env.nodes.get("lesson-status").textContent, /具体经验/);
  const evidence = env.nodes.get("lesson-list").children[0].children[2].children[1].textContent;
  assert.match(evidence, /动机不足/);
  assert.match(evidence, /base-hash/);
});

test("创建仅生成候选，原请求重放沿用幂等编号", async () => {
  const env = setup();
  env.nodes.get("lesson-feedback").value = "f";
  env.nodes.get("lesson-title").value = "动机";
  env.nodes.get("lesson-content").value = "用动作承载动机";
  await env.controller.create();
  await env.controller.create();
  assert.equal(env.requests[0].body.payload.action, "create");
  assert.deepEqual(env.requests[0].body, env.requests[1].body);
  assert.equal(env.requests[0].body.target.session_id, "s");
  assert.match(env.nodes.get("lesson-status").textContent, /明确批准后/);
});

test("批准需要明确审阅说明，刷新恢复中文状态", async () => {
  const env = setup();
  await env.controller.review(env.item, "approve");
  assert.equal(env.requests.length, 0);
  env.nodes.get("lesson-note").value = "本章适用";
  await env.controller.review(env.item, "approve");
  assert.equal(env.requests[0].body.payload.version, 1);
  assert.equal(env.requests[0].body.payload.note, "本章适用");
  env.item.status = "active";
  env.controller.render(env.data, env.controller.scope);
  assert.match(env.nodes.get("lesson-list").children[0].children[0].textContent, /已批准/);
  assert.equal(env.nodes.get("lesson-list").children[0].children[3].children[0].textContent, "归档经验");
});

test("切章时迟到的经验操作响应不刷新新章或覆盖状态", async () => {
  const env = setup();
  let resolve;
  env.setResponse(() => new Promise(done => { resolve = done; }));
  env.nodes.get("lesson-note").value = "确认";
  const pending = env.controller.review(env.item, "approve");
  env.setScope({ projectId: "p", chapter: 2, epoch: 2 });
  env.nodes.get("lesson-status").textContent = "新章";
  resolve({ ok: true, json: async () => ({ status: "accepted" }) });
  await pending;
  assert.equal(env.refreshes, 0);
  assert.equal(env.nodes.get("lesson-status").textContent, "新章");
});
