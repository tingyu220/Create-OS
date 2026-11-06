const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function node() {
  return { value: "", textContent: "", hidden: false, disabled: false, dataset: {}, children: [], events: {},
    setAttribute() {}, addEventListener(name, fn) { this.events[name] = fn; },
    append(...items) { this.children.push(...items); }, replaceChildren(...items) { this.children = items; },
    querySelector(selector) { return this.children[selector === "input" ? 0 : 1]; },
    querySelectorAll() { return this.children.flatMap(item => item.children || []); } };
}
function candidate(revision) {
  return { revision, hash: `hash-${revision}`, content: { blocks: [{ key: "core", title: "核心", text: `候选${revision}` }], open_questions: [] } };
}
function view(revision) {
  return { project_id: "p", scope: "story", session_id: "s", messages: [], jobs: [], candidate: candidate(revision), confirmed: null };
}
const flush = async () => { for (let i = 0; i < 4; i++) await new Promise(resolve => setImmediate(resolve)); };
function setup() {
  const nodes = new Map();
  const get = id => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
  const requests = [];
  let read = async () => view(1);
  let post = async () => ({ status: "accepted" });
  const response = value => ({ ok: true, json: async () => value });
  const context = vm.createContext({ document: { getElementById: get, createElement: node }, URLSearchParams,
    crypto: { randomUUID: () => `key-${requests.length}` }, clearTimeout() {}, setTimeout() {},
    window: { location: { pathname: "/p/p/story", assign() {} } },
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (url.startsWith("/api/story/session")) return response({ project_id: "p", session_id: "s" });
      return response(options ? await post(url, JSON.parse(options.body)) : await read());
    } });
  vm.runInContext(fs.readFileSync("creative_os/web/story.js", "utf8"), context);
  return { get, requests, setRead(fn) { read = fn; }, setPost(fn) { post = fn; } };
}

test("迟到的故事 Query 不能覆盖更新版本", async () => {
  const env = setup(); await flush();
  let release;
  env.setRead(() => new Promise(resolve => { release = resolve; }));
  const old = env.get("story-refresh").events.click(); await flush();
  env.setRead(async () => view(3));
  await env.get("story-refresh").events.click();
  assert.equal(env.get("candidate-version").textContent, "候选 v3");
  release(view(2)); await old;
  assert.equal(env.get("candidate-version").textContent, "候选 v3");
});

test("作者编辑绑定原 revision，外部新候选不能让旧编辑静默覆盖", async () => {
  const env = setup(); await flush();
  const text = env.get("candidate-blocks").children[0].children[1];
  text.value = "作者尚未保存的编辑"; text.events.input();
  assert.equal(env.get("confirm-candidate").disabled, true);
  env.setRead(async () => view(2)); await env.get("story-refresh").events.click();
  assert.equal(text.value, "作者尚未保存的编辑");
  assert.match(env.get("candidate-version").textContent, /编辑基于 v1/);
  let payload;
  env.setPost(async (url, body) => { payload = body; return { status: "rejected", error: { message: "candidate_conflict" } }; });
  await env.get("save-candidate").events.click();
  assert.equal(payload.payload.expected_revision, 1);
  assert.match(env.get("story-status").textContent, /candidate_conflict/);
});

test("确认必须发送明确 revision/hash/expected confirmed version", async () => {
  const env = setup(); await flush();
  let body;
  env.setPost(async (url, value) => { body = value; return { status: "accepted" }; });
  await env.get("confirm-candidate").events.click();
  assert.equal(body.command_id, "confirm_story_candidate");
  assert.equal(body.target.project_id, "p"); assert.equal(body.target.scope, "story"); assert.equal(body.target.session_id, "s");
  assert.deepEqual(JSON.parse(JSON.stringify(body.payload)), { revision: 1, hash: "hash-1", expected_confirmed_version: 0 });
});

test("页面所有模块请求固定绑定项目路径，切页后的旧实例不会改绑新项目", async () => {
  const calls = [];
  const window = { location: { pathname: "/p/book-a/writer" }, fetch: async url => calls.push(url) };
  const context = vm.createContext({ window });
  vm.runInContext(fs.readFileSync("creative_os/web/project-scope.js", "utf8"), context);
  await window.fetch("/api/agent/jobs/a?project_id=book-a");
  window.location.pathname = "/p/book-b/story";
  await window.fetch("/api/story");
  assert.deepEqual(calls, ["/p/book-a/api/agent/jobs/a?project_id=book-a", "/p/book-a/api/story"]);
});

test("查看状态不能解禁仍在提交的故事命令", async () => {
  const env = setup(); await flush();
  let release;
  env.setPost(() => new Promise(resolve => { release = resolve; }));
  const posting = env.get("story-composer").events.submit({ preventDefault() {} }); await flush();
  assert.equal(env.get("story-send").disabled, true);
  await env.get("story-refresh").events.click();
  assert.equal(env.get("story-send").disabled, true);
  release({ status: "accepted" }); await posting;
  assert.equal(env.get("story-send").disabled, false);
});
