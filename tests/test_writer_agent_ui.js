const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

test("显著字数偏离诚实提示且保留候选供作者决定，不自动发起调整", async () => {
  const env = setup(); const session = env.session(1, "completed");
  const report = { severity: "significant", message: "整章总量 10638 字，冻结输入 6045 字，净变化 +4593 字，显著偏离目标", adjustment_options: ["可保留当前候选", "可在继续修改中明确压缩至4200–4800字，确认后执行"] };
  Object.assign(session.jobs[0], { mode: "act", proposal_id: "proposal-budget", word_assessment: report });
  session.proposals = [{ proposal_id: "proposal-budget", status: "pending", result: { content: "完整保留的超长候选" }, word_assessment: report }];
  env.setAnswer(session); await env.controller.open("p");
  assert.match(env.nodes.get("agent-state-text").textContent, /显著偏离/);
  assert.match(env.nodes.get("agent-proposal-summary").textContent, /10638.*继续修改/);
  assert.equal(env.nodes.get("agent-review-actions").hidden, false);
  assert.equal(env.requests.length, 0);
  assert.equal(session.proposals[0].result.content, "完整保留的超长候选");
});

function setup() {
  const nodes = new Map();
  const node = () => ({ dataset: {}, children: [], events: {}, disabled: false, textContent: "", value: "", focus() {}, insertAdjacentElement(position, element) { this.next = element; }, setAttribute(name, value) { this[name] = value; }, replaceChildren(...items) { this.children = items; }, append(item) { this.children.push(item); }, querySelectorAll() { return this.children; }, addEventListener(event, callback) { this.events[event] = callback; } });
  const document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); }, createElement: node };
  let selected = 1;
  let answer;
  let pending;
  let handler;
  const timers = [];
  const requests = [];
  let now = Date.parse("2026-10-18T00:05:00Z");
  const context = vm.createContext({ document, URLSearchParams, Date: class extends Date { static now() { return now; } }, window: { confirm: () => true, clearTimeout() {}, setTimeout(fn) { timers.push(fn); } }, fetch: async (url, options) => {
    if (options?.method === "POST") requests.push({ url, body: JSON.parse(options.body) });
    if (handler) { const value = handler(url, options); if (value) return value; }
    if (pending) return pending;
    return { ok: true, json: async () => answer };
  } });
  vm.runInContext(fs.readFileSync("creative_os/web/writer-agent-progress.js", "utf8") + "\n" + fs.readFileSync("creative_os/web/writer-agent.js", "utf8") + "\nglobalThis.Controller = WriterAgentConversation;", context);
  const drafts = [];
  const proposals = [];
  const controller = new context.Controller({ chapter: () => selected, wordTarget: () => ({}), onDraft: async job => drafts.push(job), onProposal: async value => proposals.push(value) });
  const session = (chapter = 1, status = "thinking") => ({ project_id: "p", chapter_number: chapter, session_id: `s-${chapter}`, messages: [{ task_id: "t1", message_id: "m1", role: "user", content: "保留开头" }], jobs: [{ job_id: "t1", status, message: "当前状态" }] });
  return { controller, nodes, drafts, proposals, timers, requests, session, setNow(value) { now = Date.parse(value); }, setHandler(value) { handler = value; }, setAnswer(value) { answer = value; }, setChapter(value) { selected = value; }, setPending(value) { pending = value; } };
}

test("运行计时来自持久开始时间，计时不查询网络且刷新不归零", async () => {
  const env = setup(); const session = env.session();
  Object.assign(session.jobs[0], { mode: "act", started_at: "2026-10-18T00:00:00Z", status_updated_at: "2026-10-18T00:01:00Z" });
  env.setAnswer(session); await env.controller.open("p");
  assert.match(env.nodes.get("agent-state-text").textContent, /生成候选/);
  assert.match(env.nodes.get("agent-progress-time").textContent, /5分00秒/);
  assert.match(env.nodes.get("agent-progress-note").textContent, /等待.*响应/);
  assert.match(env.nodes.get("agent-action-reason").textContent, /本章任务.*暂不支持中断/);
  assert.match(env.nodes.get("agent-send").title, /本章任务/);
  env.setNow("2026-10-18T00:05:12Z");
  env.controller.progress.tick(env.controller.scope);
  assert.match(env.nodes.get("agent-progress-time").textContent, /5分12秒/);
  assert.equal(env.requests.length, 0);
  await env.controller.open("p");
  assert.match(env.nodes.get("agent-progress-time").textContent, /5分12秒/);
});

test("旧任务缺少开始时间诚实降级，完成计时停止且动作解禁", async () => {
  const env = setup(); env.setAnswer(env.session()); await env.controller.open("p");
  assert.match(env.nodes.get("agent-progress-time").textContent, /未记录开始时间/);
  const done = env.session(1, "completed");
  Object.assign(done.jobs[0], { started_at: "2026-10-18T00:00:00Z", updated_at: "2026-10-18T00:02:10Z" });
  env.setAnswer(done); await env.controller.refresh(env.controller.scope);
  assert.equal(env.nodes.get("agent-send").disabled, false);
  assert.equal(env.nodes.get("agent-action-reason").textContent, "");
  assert.match(env.nodes.get("agent-progress-time").textContent, /用时 2分10秒/);
  env.setNow("2026-10-18T01:00:00Z"); env.controller.progress.tick(env.controller.scope);
  assert.match(env.nodes.get("agent-progress-time").textContent, /用时 2分10秒/);
});

test("轮询失败保持任务与计时，不伪报失败或重复提交，恢复后打开候选", async () => {
  const env = setup(); const session = env.session();
  Object.assign(session.jobs[0], { mode: "act", started_at: "2026-10-18T00:00:00Z", status_updated_at: "2026-10-18T00:01:00Z" });
  env.setAnswer(session); await env.controller.open("p");
  env.setHandler(() => { throw new Error("网络暂断"); });
  await env.controller.refresh(env.controller.scope);
  assert.equal(env.controller.session.jobs[0].status, "thinking");
  assert.match(env.nodes.get("agent-state-text").textContent, /查询.*暂不可用/);
  env.controller.progress.tick(env.controller.scope);
  assert.match(env.nodes.get("agent-progress-note").textContent, /尚未确认.*失败/);
  assert.equal(env.nodes.get("agent-send").disabled, true);
  assert.equal(env.requests.length, 0);
  const proposal = { project_id: "p", chapter_number: 1, session_id: "s-1", proposal_id: "proposal-new", status: "pending", result: { content: "候选" } };
  session.jobs[0] = { ...session.jobs[0], status: "completed", proposal_id: proposal.proposal_id, updated_at: "2026-10-18T00:05:00Z" };
  session.proposals = [proposal];
  env.setHandler(url => url.startsWith("/api/agent/proposals/") ? { ok: true, json: async () => proposal } : null);
  await env.controller.refresh(env.controller.scope);
  assert.equal(env.nodes.get("agent-send").disabled, false);
  assert.equal(env.proposals.length, 1);
  assert.equal(env.requests.length, 0);
});

test("切章后旧计时回调不能污染新章，分析与生成阶段明确区分", async () => {
  const env = setup(); const first = env.session(); first.jobs[0].mode = "act";
  env.setAnswer(first); await env.controller.open("p"); const oldScope = env.controller.scope;
  const next = env.session(2); next.jobs[0].mode = "analyze";
  env.setChapter(2); env.setAnswer(next); await env.controller.open("p");
  assert.match(env.nodes.get("agent-state-text").textContent, /分析本章/);
  const text = env.nodes.get("agent-progress-time").textContent;
  env.controller.progress.tick(oldScope);
  assert.equal(env.nodes.get("agent-progress-time").textContent, text);
});

test("同章并发状态查询的迟到响应不覆盖完成状态", async () => {
  const env = setup(); env.setAnswer(env.session()); await env.controller.open("p");
  let resolve; env.setPending(new Promise(done => { resolve = done; }));
  const old = env.controller.refresh(env.controller.scope);
  env.setPending(null); env.setAnswer(env.session(1, "completed")); await env.controller.refresh(env.controller.scope);
  resolve({ ok: true, json: async () => env.session() }); await old;
  assert.equal(env.controller.session.jobs[0].status, "completed");
  assert.equal(env.nodes.get("agent-send").disabled, false);
});

test("查看状态不会解禁仍在提交的命令，忙碌时不能重复提交", async () => {
  const env = setup(); env.setAnswer(env.session(1, "completed")); await env.controller.open("p");
  let resolve;
  env.setHandler((url, options) => options?.method === "POST" ? new Promise(done => { resolve = done; }) : null);
  const submitting = env.controller.submit("只分析");
  await env.controller.$("agent-refresh-status").events.click();
  assert.equal(env.nodes.get("agent-send").disabled, true);
  await env.controller.submit("重复指令");
  assert.equal(env.requests.length, 1);
  resolve({ ok: true, json: async () => ({}) }); await submitting;
  assert.equal(env.nodes.get("agent-send").disabled, false);
});

test("失败后只由作者点击安全重试，携带原任务与会话作用域", async () => {
  const env = setup(); const failed = env.session(1, "failed");
  Object.assign(failed.jobs[0], { retryable: true, error: "测试模型限流" });
  env.setAnswer(failed); await env.controller.open("p");
  assert.equal(env.requests.length, 0);
  const retry = env.session(); retry.jobs[0].job_id = "retry-one";
  env.setHandler((url, options) => {
    if (options?.method === "POST") { env.setAnswer(retry); return { ok: true, json: async () => ({ job_id: "retry-one" }) }; }
  });
  await env.nodes.get("agent-session-actions").children[0].events.click();
  assert.equal(env.requests[0].url, "/api/agent/jobs/t1/retry");
  assert.deepEqual(env.requests[0].body, { project_id: "p", chapter_number: 1, session_id: "s-1" });
  assert.equal(env.nodes.get("agent-send").disabled, true);
});

test("审阅中断显式核对原身份，不重新接受或覆盖编辑器", async () => {
  const env = setup(), session = env.session(1, "completed");
  const proposal = { proposal_id: "proposal-one", status: "reviewing", result: { content: "候选" },
    review_recovery: { required: true, actor: "原审阅作者", action: "accept", payload: { feedback_id: "feedback-one", review_hash: "original-hash" } } };
  session.proposals = [proposal]; env.setAnswer(session); await env.controller.open("p");
  assert.equal(env.controller.reconcileButton.hidden, false);
  assert.equal(env.nodes.get("agent-review-actions").hidden, true);
  assert.equal(env.requests.length, 0);
  await env.controller.review("accept"); assert.equal(env.requests.length, 0);
  env.controller.$("decision-feedback").value = "不能取代原审阅的新要求";
  env.setHandler((url, options) => {
    if (options?.method === "POST") { proposal.status = "accepted"; delete proposal.review_recovery; return { ok: true, json: async () => ({ status: "accepted" }) }; }
  });
  await env.controller.reconcileButton.events.click();
  assert.equal(env.requests[0].url, "/api/commands/reconcile-writer-proposal");
  assert.equal(env.requests[0].body.actor, "原审阅作者");
  assert.equal(env.requests[0].body.target.session_id, "s-1");
  assert.deepEqual(env.requests[0].body.payload, { feedback_id: "feedback-one", review_hash: "original-hash" });
  assert.equal(env.drafts.length, 0);
  assert.equal(env.controller.reconcileButton.hidden, true);
});

test("核对响应丢失复用编号，切章后迟到响应不刷新新会话", async () => {
  const env = setup(), session = env.session(1, "completed");
  session.proposals = [{ proposal_id: "proposal-one", status: "accepted", review_recovery: { required: true, actor: "作者", action: "accept", payload: { feedback_id: "f", review_hash: "h" } } }];
  env.setAnswer(session); await env.controller.open("p");
  env.setHandler((url, options) => { if (options?.method === "POST") throw new Error("响应丢失"); });
  await env.controller.reconcileReview(); await env.controller.reconcileReview();
  assert.equal(env.requests.length, 2); assert.deepEqual(env.requests[0].body, env.requests[1].body);
  let release;
  env.setHandler((url, options) => { if (options?.method === "POST") return new Promise(resolve => { release = resolve; }); });
  const pending = env.controller.reconcileReview();
  env.setChapter(2); env.setAnswer(env.session(2, "completed")); await env.controller.open("p");
  release({ ok: true, json: async () => ({ status: "accepted" }) }); await pending;
  assert.equal(env.controller.session.chapter_number, 2); assert.equal(env.drafts.length, 0);
});

test("章节重启只读投影显示显式重试，saving 核对状态不提供重试", async () => {
  const env = setup(); const interrupted = env.session(1, "failed");
  Object.assign(interrupted.jobs[0], { observed_status: "queued", recovery_required: true, retryable: true, error: "task_recovery_required" });
  env.setAnswer(interrupted); await env.controller.open("p");
  assert.equal(env.nodes.get("agent-session-actions").children[0].textContent, "重试失败任务");
  assert.equal(env.nodes.get("agent-session-actions").children[0].disabled, false);
  assert.equal(env.requests.length, 0);
  const saving = env.session(1, "failed");
  Object.assign(saving.jobs[0], { observed_status: "saving", recovery_required: true, retryable: false, error: "saving_reconciliation_required" });
  env.setAnswer(saving); await env.controller.refresh(env.controller.scope);
  assert.equal(env.nodes.get("agent-session-actions").children.length, 0);
  assert.equal(env.requests.length, 0);
});

test("继续修改POST已受理但GET持续失败时保持禁用，查询恢复后才解禁", async () => {
  const env = setup(); const session = env.session(1, "completed");
  session.proposals = [{ proposal_id: "proposal-one", status: "pending", result: { content: "待修改候选" } }];
  env.setAnswer(session); await env.controller.open("p");
  env.nodes.get("agent-review-actions").append(env.controller.$("accept-agent-draft"));
  env.nodes.get("agent-review-actions").append(env.controller.$("revise-agent-draft"));
  env.controller.$("decision-feedback").value = "增加人物动作";
  let resolvePost, notifyPost;
  const postStarted = new Promise(done => { notifyPost = done; });
  const postPending = new Promise(done => { resolvePost = done; });
  let failReads = true;
  env.setHandler((url, options) => {
    if (options?.method === "POST") { notifyPost(); return postPending; }
    if (failReads) throw new Error("状态查询持续断网");
  });
  const reviewing = env.controller.review("revise");
  await postStarted;
  await env.controller.refresh(env.controller.scope);
  assert.equal(env.controller.progress.queryError, true);
  resolvePost({ ok: true, json: async () => ({ status: "accepted" }) });
  await reviewing;
  assert.equal(env.controller.reviewing, false);
  assert.equal(env.controller.session.jobs[0].status, "completed");
  for (const id of ["agent-send", "agent-continue", "agent-check"]) assert.equal(env.nodes.get(id).disabled, true);
  assert.match(env.nodes.get("agent-action-reason").textContent, /状态尚未确认/);
  assert.equal(env.nodes.get("agent-review-actions").children.length, 2);
  assert.ok(env.nodes.get("agent-review-actions").children.every(button => button.disabled));
  await env.controller.submit("不应受理的新指令");
  await env.controller.submit("继续写这一章", "act");
  await env.controller.request("/api/agent/jobs/t1/retry", {});
  await env.controller.review("revise");
  assert.equal(env.requests.length, 1);
  failReads = false;
  await env.controller.refresh(env.controller.scope);
  assert.equal(env.controller.progress.queryError, false);
  assert.equal(env.nodes.get("agent-send").disabled, false);
  assert.equal(env.nodes.get("agent-continue").disabled, false);
  assert.equal(env.nodes.get("agent-action-reason").textContent, "");
});

test("切章清除当前查询错误，旧章迟到查询失败不能再次禁用新章", async () => {
  const env = setup(); env.setAnswer(env.session(1, "completed")); await env.controller.open("p");
  const oldScope = env.controller.scope;
  env.setHandler(() => { throw new Error("旧章查询失败"); });
  await env.controller.refresh(oldScope);
  assert.equal(env.controller.progress.queryError, true);
  let rejectOld;
  env.setHandler(() => new Promise((resolve, reject) => { rejectOld = reject; }));
  const oldRequest = env.controller.refresh(oldScope);
  env.setHandler(null); env.setChapter(2); env.setAnswer(env.session(2, "completed"));
  await env.controller.open("p");
  assert.equal(env.controller.progress.queryError, false);
  assert.equal(env.nodes.get("agent-send").disabled, false);
  rejectOld(new Error("旧章迟到错误")); await oldRequest;
  assert.equal(env.controller.progress.queryError, false);
  assert.equal(env.nodes.get("agent-send").disabled, false);
  assert.equal(env.nodes.get("agent-action-reason").textContent, "");
});

test("状态变化不替换历史消息节点，刷新可恢复历史", async () => {
  const env = setup();
  env.setAnswer(env.session());
  await env.controller.open("p");
  const message = env.nodes.get("agent-thread").children[0];
  env.setAnswer(env.session(1, "saving"));
  await env.controller.refresh(env.controller.scope);
  assert.equal(env.nodes.get("agent-thread").children[0], message);
  assert.equal(message.textContent, "你：保留开头");
  assert.match(env.nodes.get("agent-state-text").textContent, /保存/);
  assert.equal(env.nodes.get("agent-send").disabled, true);
});

test("切章后迟到的旧请求不覆盖新会话，也不打开旧章工作稿", async () => {
  const env = setup();
  env.setAnswer(env.session());
  await env.controller.open("p");
  let resolve;
  env.setPending(new Promise(done => { resolve = done; }));
  const old = env.controller.refresh(env.controller.scope);
  env.setPending(null);
  env.setChapter(2);
  env.setAnswer(env.session(2, "completed"));
  await env.controller.open("p");
  resolve({ ok: true, json: async () => ({ ...env.session(1, "completed"), messages: [{ message_id: "old", role: "assistant", content: "旧章结果" }] }) });
  await old;
  assert.equal(env.controller.session.chapter_number, 2);
  assert.doesNotMatch(env.nodes.get("agent-thread").children[0].textContent, /旧章结果/);
  assert.equal(env.drafts.length, 0);
});

test("失败保留真实原因和原消息，显示重试操作", async () => {
  const env = setup();
  const session = env.session(1, "failed");
  session.jobs[0].error = "服务限流：测试原因";
  session.jobs[0].retryable = true;
  env.setAnswer(session);
  await env.controller.open("p");
  assert.match(env.nodes.get("agent-task-status").children[0].textContent, /测试原因/);
  assert.equal(env.nodes.get("agent-session-actions").children[0].textContent, "重试失败任务");
  assert.equal(env.nodes.get("agent-thread").children[0].textContent, "你：保留开头");
});

test("同一历史切章再回来仍然渲染，首次恢复不自动打开旧工作稿", async () => {
  const env = setup();
  env.setAnswer(env.session(1, "completed"));
  await env.controller.open("p");
  await env.controller.open("p");
  assert.equal(env.nodes.get("agent-thread").children.length, 1);
  assert.equal(env.drafts.length, 0);
});

test("刷新恢复分析后仍可提交原决策与作者补充要求", async () => {
  const env = setup();
  const session = env.session(1, "completed");
  Object.assign(session.jobs[0], { mode: "analyze", decision_id: "decision-original" });
  env.setAnswer(session);
  await env.controller.open("p");
  assert.match(env.nodes.get("agent-session-actions").children[0].textContent, /方案/);
  env.controller.$("decision-feedback").value = "保留新结尾，增加人物动作";
  await env.controller.executeDecision("decision-original");
  assert.equal(env.requests[0].url, "/api/agent/decisions/act");
  assert.equal(env.requests[0].body.decision_id, "decision-original");
  assert.equal(env.requests[0].body.feedback, "保留新结尾，增加人物动作");
  assert.equal(env.requests[0].body.session_id, "s-1");
});

test("恢复候选可审阅但不自动打开工作稿，拒绝通过命令且不恢复版本", async () => {
  const env = setup(); const session = env.session(1, "completed");
  Object.assign(session.jobs[0], { mode: "act", proposal_id: "proposal-one" });
  session.proposals = [{ proposal_id: "proposal-one", status: "pending", chapter_number: 1,
    session_id: "s-1", base: { content: "原稿" }, result: { content: "独立候选" } }];
  env.setAnswer(session); await env.controller.open("p");
  assert.equal(env.drafts.length, 0);
  assert.equal(env.nodes.get("agent-review-actions").hidden, false);
  env.controller.$("decision-feedback").value = "人物动机不足";
  await env.controller.review("reject");
  assert.equal(env.requests[0].url, "/api/commands/review-writer-proposal");
  assert.equal(env.requests[0].body.command_id, "review_writer_proposal");
  assert.equal(env.requests[0].body.target.proposal_id, "proposal-one");
  assert.equal(env.requests[0].body.target.chapter_number, 1);
  assert.equal(env.requests[0].body.payload.reason, "人物动机不足");
  assert.equal(env.drafts.length, 0);
});

test("无原因不能拒绝候选，切章后不能审阅旧候选", async () => {
  const env = setup(); const session = env.session(1, "completed");
  session.proposals = [{ proposal_id: "proposal-one", status: "pending" }];
  env.setAnswer(session); await env.controller.open("p");
  await env.controller.review("reject");
  assert.equal(env.requests.length, 0);
  assert.match(env.nodes.get("agent-state-text").textContent, /原因/);
  env.controller.$("decision-feedback").value = "不采用";
  env.setChapter(2);
  await env.controller.review("reject");
  assert.equal(env.requests.length, 0);
});

test("继续修改明确提交候选来源及原提案，不能调用旧决策执行", async () => {
  const env = setup(); const session = env.session(1, "completed");
  session.proposals = [{ proposal_id: "proposal-one", status: "pending" }];
  env.setAnswer(session); await env.controller.open("p");
  env.controller.$("decision-feedback").value = "重写结尾";
  env.controller.$("proposal-source").value = "candidate";
  await env.controller.revise();
  assert.equal(env.requests[0].url, "/api/commands/review-writer-proposal");
  assert.equal(env.requests[0].body.payload.action, "revise");
  assert.equal(env.requests[0].body.payload.source, "candidate");
});

test("接受确认后才打开工作稿，候选阅读和冻结差异不触发保存", async () => {
  const env = setup(); const session = env.session(1, "completed");
  const proposal = { project_id: "p", chapter_number: 1, session_id: "s-1", proposal_id: "proposal-one",
    status: "pending", result: { content: "独立候选" }, base: { content: "冻结原稿" }, diff: "-冻结原稿\n+独立候选" };
  session.proposals = [proposal];
  env.setAnswer(session);
  env.setHandler((url, options) => {
    if (url.startsWith("/api/agent/proposals/")) return { ok: true, json: async () => proposal };
    if (options?.method === "POST") { proposal.status = "accepted"; return { ok: true, json: async () => ({ status: "accepted" }) }; }
  });
  await env.controller.open("p");
  await env.controller.viewProposal("proposal-one");
  assert.equal(env.proposals[0].diff, proposal.diff);
  assert.equal(env.drafts.length, 0);
  assert.equal(env.requests.length, 0);
  await env.controller.review("accept");
  assert.equal(env.drafts.length, 1);
  assert.equal(env.nodes.get("agent-review-actions").hidden, true);
  assert.match(env.nodes.get("agent-proposal-summary").textContent, /已接受为工作稿/);
});

test("接受版本冲突不打开工作稿，审阅请求使用原幂等编号", async () => {
  const env = setup(); const session = env.session(1, "completed");
  session.proposals = [{ proposal_id: "proposal-one", status: "pending" }];
  env.setAnswer(session);
  env.setHandler((url, options) => options?.method === "POST" ? { ok: false, json: async () => ({ status: "rejected", error: { message: "原稿已被修改" } }) } : null);
  await env.controller.open("p");
  await env.controller.review("accept");
  await env.controller.review("accept");
  assert.equal(env.drafts.length, 0);
  assert.equal(env.requests[0].body.request_id, env.requests[1].body.request_id);
  assert.match(env.nodes.get("agent-state-text").textContent, /原稿已被修改/);
});

test("普通追问明确只读，只有显式写作入口传递Act", async () => {
  const env = setup(); env.setAnswer(env.session(1, "completed"));
  await env.controller.open("p");
  for (const question of ["为什么这样写？", "继续解释一下原因", "为什么建议修改结尾？"]) {
    await env.controller.submit(question);
    assert.equal(env.requests.at(-1).body.mode, "analyze");
  }
  await env.controller.submit("继续写这一章", "act");
  assert.equal(env.requests.at(-1).body.mode, "act");
});
