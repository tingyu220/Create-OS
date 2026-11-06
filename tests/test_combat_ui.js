const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

test("战斗专家入口显式发送 requested_expert 且不把跨书迟到结果渲染到当前章节", async () => {
  const nodes = new Map();
  const node = () => ({ children: [], textContent: "", dataset: {}, hidden: false, replaceChildren(...items) { this.children = items; }, append(item) { this.children.push(item); }, addEventListener() {} });
  const document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); }, createElement: node };
  const context = vm.createContext({ document, window: {}, fetch: async () => ({ ok: true, json: async () => ({}) }) });
  vm.runInContext(fs.readFileSync("creative_os/web/combat-panel.js", "utf8"), context);
  assert.equal(typeof context.CombatPanel, "function");
  const panel = new context.CombatPanel({ projectId: "book-a", chapter: () => 2 });
  panel.render([{ result_id: "r1", project_id: "book-b", scope: { chapter_numbers: [2] }, reply: "迟到" }]);
  assert.equal(nodes.get("combat-results").children.length, 0);
});

test("结果卡片清晰展示建议、来源和未知范围", () => {
  const nodes = new Map();
  const node = () => ({ children: [], textContent: "", dataset: {}, replaceChildren(...items) { this.children = items; }, append(item) { this.children.push(item); }, addEventListener() {} });
  const document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); }, createElement: node };
  const context = vm.createContext({ document, window: {} });
  vm.runInContext(fs.readFileSync("creative_os/web/combat-panel.js", "utf8"), context);
  const panel = new context.CombatPanel({ projectId: "book-a", chapter: () => 2 });
  panel.render([{ result_id: "r1", project_id: "book-a", scope: { chapter_numbers: [2] }, reply: "建议主角撤退", alternatives: ["正面迎战"], foreshadowing: ["留下伤痕"], evidence_refs: ["chapter-2#scene-1"], unknowns: ["敌方人数"] }]);
  const text = nodes.get("combat-results").children[0].children.map(item => item.textContent).join(" ");
  assert.match(text, /建议主角撤退/); assert.match(text, /正面迎战/); assert.match(text, /chapter-2#scene-1/); assert.match(text, /敌方人数/);
});

test("采用前置读取失败可见且不会提交命令", async () => {
  const nodes = new Map(); const status = [];
  const node = () => ({ children: [], textContent: "", dataset: {}, replaceChildren(...items) { this.children = items; }, append(item) { this.children.push(item); }, addEventListener() {} });
  const document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); }, createElement: node };
  const requests = [];
  const context = vm.createContext({ document, window: {}, fetch: async (url, options) => { requests.push({ url, options }); throw new Error("故事状态暂不可用"); } });
  vm.runInContext(fs.readFileSync("creative_os/web/combat-panel.js", "utf8"), context);
  const panel = new context.CombatPanel({ projectId: "book-a", chapter: () => 2, onStatus: value => status.push(value) });
  await panel.adopt({ result_id: "r1" });
  assert.deepEqual(status, ["故事状态暂不可用"]); assert.equal(requests.some(item => item.options?.method === "POST"), false);
});

test("首次故事没有候选时仍按 revision 0 发送采用命令", async () => {
  const nodes = new Map(); const requests = [];
  const node = () => ({ children: [], textContent: "", dataset: {}, replaceChildren(...items) { this.children = items; }, append(item) { this.children.push(item); }, addEventListener() {} });
  const document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); }, createElement: node };
  const context = vm.createContext({ document, window: {}, fetch: async (url, options) => {
    requests.push({ url, options });
    if (url.includes("/story/session")) return { ok: true, json: async () => ({ session_id: "story-session" }) };
    if (url.startsWith("/api/story?")) return { ok: true, json: async () => ({ candidate: null }) };
    return { ok: true, json: async () => ({ status: "accepted" }) };
  } });
  vm.runInContext(fs.readFileSync("creative_os/web/combat-panel.js", "utf8"), context);
  const panel = new context.CombatPanel({ projectId: "book-a", chapter: () => 2 });
  await panel.adopt({ result_id: "r1" });
  const posted = requests.find(item => item.options?.method === "POST");
  assert.ok(posted); assert.equal(JSON.parse(posted.options.body).payload.expected_revision, 0);
});

