const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const settle = async () => { for (let index = 0; index < 30; index++) await Promise.resolve(); };

function setup(version = 1) {
  const nodes = new Map();
  const node = () => ({ dataset: {}, children: [], events: {}, value: "", disabled: false,
    textContent: "", innerHTML: "", setAttribute() {}, focus() {},
    replaceChildren(...children) { this.children = children; }, append(child) { this.children.push(child); },
    querySelectorAll() { return []; }, addEventListener(event, callback) { this.events[event] = callback; } });
  const get = id => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
  get("chapter-number").value = "1";
  get("agent-target-words").value = "4500";
  get("agent-tolerance-words").value = "300";
  const timers = new Map(); let timerId = 0;
  const saves = [];
  const receipts = new Map();
  const saved = { 1: { content: "第一章原稿", version }, 2: { content: "第二章原稿", version }, 3: { content: "第三章原稿", version } };
  const delays = { conversation: new Map(), chapter: new Map(), save: null, dropResponses: 0 };
  const response = data => ({ ok: true, json: async () => data });
  const deliverSave = data => {
    if (delays.dropResponses > 0) { delays.dropResponses--; throw new Error("测试：保存响应丢失"); }
    return response(data);
  };
  const submissions = [];
  class FakeConversation {
    constructor(options) { this.options = options; this.epoch = 0; }
    async open() { this.epoch++; const delay = delays.conversation.get(Number(get("chapter-number").value)); if (delay) await delay.promise; }
    async submit(...args) { submissions.push(args); }
    async revise() {}
  }
  const context = vm.createContext({ document: { getElementById: get, createElement: node, querySelectorAll: () => [], querySelector: () => get("grid") },
    URL, URLSearchParams, console, crypto: require("node:crypto"), WriterAgentConversation: FakeConversation,
    window: { location: { href: "http://localhost/writer?chapter=1", search: "?chapter=1" }, history: { replaceState() {} }, confirm: () => true,
      setTimeout(callback) { const id = ++timerId; timers.set(id, callback); return id; }, clearTimeout(id) { timers.delete(id); }, setInterval() {} },
    fetch: async (url, options) => {
      if (url === "/api/workspace") return response({ project_id: "p" });
      if (url === "/api/writer/context") return response({ formal_chapters: [], working_draft_chapters: [] });
      if (url === "/api/commands/save-writer-draft") {
        const body = JSON.parse(options.body); saves.push(body);
        if (receipts.has(body.idempotency_key)) return deliverSave(receipts.get(body.idempotency_key));
        if (delays.save) await delays.save.promise;
        const target = saved[body.target.chapter_number];
        let result;
        if (target.version !== body.expected_version) result = { status: "rejected", error: { message: "version_conflict" } };
        else {
          target.content = body.payload.content; target.version = (target.version || 0) + 1;
          result = { status: "accepted", emitted_event_refs: [`writer-draft:${body.target.chapter_number}:${target.version}`] };
        }
        receipts.set(body.idempotency_key, result);
        return deliverSave(result);
      }
      const match = url.match(/chapters\/(\d+)(.*)/);
      if (match) {
        const number = Number(match[1]);
        if (match[2] === "/versions") return response({ versions: saved[number].version ? [{ version: saved[number].version }] : [] });
        const captured = { ...saved[number] };
        const delay = delays.chapter.get(number); if (delay) await delay.promise;
        return response({ chapter: { project_id: "p", chapter_number: number, title: `第${number}章`, content: captured.content,
          version: captured.version ? { version: captured.version } : null, source: { editable: !!captured.version, label: "正文" } } });
      }
      throw new Error(`未模拟：${url}`);
    } });
  vm.runInContext(fs.readFileSync("creative_os/web/writer.js", "utf8"), context);
  return { get, saved, saves, delays, timers, submissions,
    async ready() { await settle(); assert.equal(get("editor").value, "第一章原稿"); },
    edit(content) { get("editor").value = content; get("editor").events.input(); },
    select(number) { get("chapter-number").value = String(number); return get("open-chapter").events.click(); },
    fireTimers() { const callbacks = [...timers.values()]; timers.clear(); callbacks.forEach(callback => callback()); } };
}

for (const version of [1, null]) {
  test(`切章等待期间旧定时保存始终绑定第一章（初始版本 ${version}）`, async () => {
    const env = setup(version); await env.ready();
    env.edit("第一章编辑内容");
    const delay = deferred(); env.delays.conversation.set(2, delay);
    const switching = env.select(2); await settle();
    env.fireTimers(); await settle();
    delay.resolve(); await switching; await settle();
    assert.equal(env.saved[2].content, "第二章原稿");
    assert.equal(env.saved[1].content, "第一章编辑内容");
    assert.equal(env.saves[0].target.chapter_number, 1);
    assert.equal(env.saves[0].expected_version, version);
    assert.equal(env.get("editor").value, "第二章原稿");
  });
}

test("飞行中的旧章保存与迟到加载不能改变新章正文或版本", async () => {
  const env = setup(); await env.ready();
  const saveDelay = deferred(); env.delays.save = saveDelay;
  env.edit("第一章在途修改"); env.fireTimers(); await settle();
  const switching = env.select(2); await settle();
  assert.notEqual(env.get("editor").value, "第二章原稿");
  saveDelay.resolve(); await switching; await settle();
  const loadDelay = deferred(); env.delays.chapter.set(2, loadDelay);
  const oldLoad = env.select(2); await settle();
  await env.select(3); loadDelay.resolve(); await oldLoad; await settle();
  assert.equal(env.get("editor").value, "第三章原稿");
  env.delays.save = null; env.edit("第三章编辑内容"); env.fireTimers(); await settle();
  assert.equal(env.saved[2].content, "第二章原稿");
  assert.equal(env.saves.at(-1).target.chapter_number, 3);
  assert.equal(env.saves.at(-1).expected_version, 1);
});

test("同章连续编辑按已确认版本串行保存后才切章", async () => {
  const env = setup(); await env.ready();
  const saveDelay = deferred(); env.delays.save = saveDelay;
  env.edit("第一次修改"); env.fireTimers(); await settle();
  env.edit("第二次修改");
  const switching = env.select(2); await settle();
  saveDelay.resolve(); await switching; await settle();
  assert.deepEqual(env.saves.map(body => body.target.chapter_number), [1, 1]);
  assert.deepEqual(env.saves.map(body => body.expected_version), [1, 2]);
  assert.equal(env.saved[1].content, "第二次修改");
  assert.equal(env.saved[2].content, "第二章原稿");
});

test("Agent提交先保存当前正文，写作按钮显式传递Act", async () => {
  const env = setup(); await env.ready();
  env.edit("提交前的最新正文");
  env.get("agent-instruction").value = "为什么这样写？";
  await env.get("agent-send").events.click();
  assert.equal(env.saved[1].content, "提交前的最新正文");
  assert.equal(env.submissions[0][1], "analyze");
  await env.get("agent-continue").events.click();
  assert.equal(env.submissions[1][1], "act");
});

test("旧章保存冲突阻止切章并保留编辑内容", async () => {
  const env = setup(); await env.ready();
  env.edit("尚未保存的第一章修改");
  env.saved[1].version = 2;
  await env.select(2);
  assert.equal(env.get("chapter-number").value, 1);
  assert.equal(env.get("editor").value, "尚未保存的第一章修改");
  assert.equal(env.saved[2].content, "第二章原稿");
  assert.equal(env.get("editor").disabled, false);
  assert.match(env.get("save-status").textContent, /version_conflict/);
});

for (const editBeforeLoss of [true, false]) {
  test(`A已落稿但响应丢失，保留原幂等请求并接续B（B在丢失${editBeforeLoss ? "前" : "后"}输入）`, async () => {
    const env = setup(); await env.ready();
    const delay = deferred(); env.delays.save = delay; env.delays.dropResponses = 1;
    env.edit("edit-A"); env.fireTimers(); await settle();
    if (editBeforeLoss) env.edit("edit-B");
    delay.resolve(); await settle(); env.delays.save = null;
    assert.equal(env.saved[1].content, "edit-A");
    assert.equal(env.saved[1].version, 2);
    if (!editBeforeLoss) env.edit("edit-B");
    if (editBeforeLoss) await env.select(2);
    else await env.get("save-draft").events.click();
    assert.deepEqual(env.saves.map(body => body.payload.content), ["edit-A", "edit-A", "edit-B"]);
    assert.deepEqual(env.saves[0], env.saves[1]);
    assert.notEqual(env.saves[1].request_id, env.saves[2].request_id);
    assert.deepEqual(env.saves.map(body => body.expected_version), [1, 1, 2]);
    assert.equal(env.saved[1].content, "edit-B");
    assert.equal(env.saved[1].version, 3);
    if (!editBeforeLoss) await env.select(2);
    assert.equal(env.get("editor").value, "第二章原稿");
    assert.equal(env.saved[2].content, "第二章原稿");
  });
}

test("确认A丢失响应后，B仍不能覆盖真正外部的新版本", async () => {
  const env = setup(); await env.ready();
  const delay = deferred(); env.delays.save = delay; env.delays.dropResponses = 1;
  env.edit("edit-A"); env.fireTimers(); await settle(); env.edit("edit-B");
  delay.resolve(); await settle(); env.delays.save = null;
  env.saved[1].content = "外部作者修改"; env.saved[1].version = 3;
  await env.get("save-draft").events.click();
  assert.deepEqual(env.saves.map(body => body.payload.content), ["edit-A", "edit-A", "edit-B"]);
  assert.deepEqual(env.saves[0], env.saves[1]);
  assert.equal(env.saves[2].expected_version, 2);
  assert.equal(env.saved[1].content, "外部作者修改");
  assert.equal(env.saved[1].version, 3);
  assert.equal(env.get("editor").value, "edit-B");
  assert.match(env.get("save-status").textContent, /version_conflict/);
  await env.select(2);
  assert.equal(env.get("chapter-number").value, 1);
  assert.equal(env.get("editor").value, "edit-B");
  assert.equal(env.saved[2].content, "第二章原稿");
});
