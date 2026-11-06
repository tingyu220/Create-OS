const { test } = require("node:test");
const assert = require("node:assert/strict");
const { BookshelfIssues } = require("../creative_os/web/bookshelf-issues.js");
const OP = "11111111-1111-4111-8111-111111111111";
const preview = { operation_id: OP, project_id: "book", available: true, plan_fingerprint: "a".repeat(64), preview_token: "signed",
  source_directory: "old", target_directory: "中文书", backup_directory: ".backup/op/project", file_count: 3, directory_count: 2 };
const state = (stage, extra = {}) => ({ ...preview, stage, reason: null, continuation_no: 0, needs_reconciliation: stage === "needs_reconciliation",
  actions: stage === "verified" ? ["open"] : ["reconcile"], ...extra });
const issue = (directory = "old", extra = {}) => ({ issue_id: directory, directory, project_id: "book", title: "中文书", code: "directory_name_mismatch",
  message: "可预览目录整理", impact: "目录名将变化", actions: ["preview_migration"], known_counts: { formal: 2, draft: 1, candidate: null }, ...extra });
const page = (items, extra = {}) => ({ items, checked_projects: 1, total_projects: 1, next_offset: 1, catalog_revision: "r1", ...extra });

function setup(handler, values = new Map()) {
  const nodes = new Map(), requests = [];
  const doc = { activeElement: null };
  function node(tag = "div") {
    return { tag, children: [], events: {}, hidden: false, disabled: false, checked: false, dataset: {}, isConnected: true,
      get textContent() { return (this._text || "") + this.children.map(child => child.textContent).join(""); },
      set textContent(value) { this._text = String(value); this.children = []; },
      set innerHTML(_value) { throw new Error("禁止innerHTML"); },
      append(...children) { this.children.push(...children); }, replaceChildren(...children) { this._text = ""; this.children = children; },
      setAttribute(key, value) { this[key] = value; }, addEventListener(key, value) { this.events[key] = value; },
      focus() { doc.activeElement = this; }, showModal() { this.open = true; }, close() { this.open = false; } };
  }
  doc.createElement = node;
  doc.getElementById = id => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
  const storage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
  let sequence = 0;
  const controller = new BookshelfIssues({ document: doc, storage, autoPoll: false, requestId: () => "request-" + (++sequence),
    fetch: async (url, options = {}) => {
      requests.push({ url, options });
      const answer = await handler(url, options);
      if (answer?.malformed) return { ok: false, status: 500, json: async () => { throw new Error("Not found"); } };
      const status = typeof answer?.status === "number" ? answer.status : 200;
      return { ok: status < 400, status, json: async () => answer?.body || answer };
    } });
  return { controller, doc, get: doc.getElementById, requests, values, posts: () => requests.filter(row => row.options.method === "POST") };
}

test("逐本保留重复ID的异常，未知数量不报零，简称没有整理按钮", async () => {
  const env = setup(() => page([issue("a"), issue("b", { code: "candidate_unavailable", actions: ["recheck", "open"] }),
    issue("简称", { actions: ["recheck", "open"], code: "session_unavailable" })], { checked_projects: 3, total_projects: 3, next_offset: 3 }));
  await env.controller.check();
  assert.equal(env.get("issues-list").children.length, 3);
  assert.match(env.get("issues-list").textContent, /未知/);
  assert.equal(env.controller.previewButtons.length, 1);
  assert.equal(env.posts().length, 0);
});

test("重新检查失败保留旧详情并标过期，分页合并且目录版本变化不冒充全部检查完", async () => {
  let count = 0;
  const env = setup(() => {
    count++;
    if (count === 1) return page([issue("a")], { total_projects: 3, next_offset: 1 });
    if (count === 2) return page([issue("b")], { total_projects: 3, next_offset: 2 });
    if (count === 3) throw new Error("network");
    return page([], { total_projects: 3, next_offset: 3, catalog_revision: "changed" });
  });
  await env.controller.check(); await env.controller.more();
  assert.equal(env.get("issues-list").children.length, 2);
  assert.match(env.get("issues-summary").textContent, /2.*3/);
  await env.controller.check();
  assert.equal(env.get("issues-list").children.length, 2);
  assert.match(env.get("issues-summary").textContent, /过期/);
  await env.controller.more();
  assert.equal(env.get("issues-list").children.length, 2);
  assert.doesNotMatch(env.get("issues-summary").textContent, /全部无异常/);
});

test("分页目录版本变化保留旧详情且要求重新检查", async () => {
  let count = 0;
  const env = setup(() => ++count === 1 ? page([issue("a")], { total_projects: 2, next_offset: 1 }) :
    page([issue("b")], { total_projects: 2, next_offset: 2, catalog_revision: "new-revision" }));
  await env.controller.check(); await env.controller.more();
  assert.equal(env.get("issues-list").children.length, 1);
  assert.match(env.get("issues-summary").textContent, /过期.*重新检查/);
  assert.equal(env.get("more-issues").disabled, true);
});

test("迟到列表响应不覆盖新检查，取消晚到预览不产生POST", async () => {
  let release, previewRelease;
  let count = 0;
  const env = setup(url => url.includes("migration-preview") ? new Promise(resolve => { previewRelease = resolve; }) :
    (++count === 1 ? new Promise(resolve => { release = resolve; }) : page([issue("new")])));
  const old = env.controller.check(); await env.controller.check();
  release(page([issue("old")])); await old;
  assert.equal(env.get("issues-list").children.length, 1);
  assert.match(env.get("issues-list").textContent, /new/);
  const pending = env.controller.preview("book"); env.controller.cancelPreview();
  previewRelease(preview); await pending;
  assert.equal(env.get("migration-preview").hidden, true);
  assert.equal(env.posts().length, 0);
});

test("预览取消零POST；确认文字勾选后单POST，双击不重复", async () => {
  let release;
  const env = setup((url, options) => {
    if (options.method === "POST") return new Promise(resolve => { release = resolve; });
    return url.includes("migration-preview") ? preview : state("verified");
  });
  await env.controller.preview("book"); env.controller.cancelPreview();
  assert.equal(env.posts().length, 0);
  await env.controller.preview("book"); await env.controller.confirm();
  assert.equal(env.posts().length, 0);
  env.get("migration-confirm-check").checked = true;
  const first = env.controller.confirm(); const second = env.controller.confirm();
  assert.equal(env.posts().length, 1);
  release({ status: "accepted" }); await first; await second;
  const body = JSON.parse(env.posts()[0].options.body);
  assert.equal(body.command_id, "migrate_project_directory");
  assert.equal(body.idempotency_key, "directory-migrate:" + OP);
  assert.equal(body.payload.confirmed, true);
  assert.equal(env.get("migration-status").dataset.stage, "verified");
  assert.equal(env.get("migration-open").href, "/p/book/");
});

test("丢响应只查原operation；sessionStorage恢复只GET，不保存token或确认", async () => {
  const env = setup((url, options) => {
    if (options.method === "POST") throw new Error("lost response");
    return url.includes("migration-preview") ? preview : state("needs_reconciliation");
  });
  await env.controller.preview("book"); env.get("migration-confirm-check").checked = true;
  await env.controller.confirm();
  assert.equal(env.posts().length, 1);
  assert.ok(env.requests.at(-1).url.endsWith("/migrations/" + OP));
  assert.deepEqual([...env.values.values()], [OP]);
  const restored = setup(() => state("needs_reconciliation"), env.values);
  await restored.controller.restore();
  assert.equal(restored.requests.length, 1);
  assert.equal(restored.posts().length, 0);
  assert.match(restored.get("migration-status").textContent, /核对/);
});

test("明确拒绝且未建操作可以重预览，重载不会恢复已拒绝操作", async () => {
  const env = setup((url, options) => options.method === "POST" ? { status: 409, body: { error: {
    code: "preview_stale", message: "预览已过期", operation_id: OP, project_id: "book", operation_created: false
  } } } : url.includes("/migrations/") ? { status: 404, body: { error: { code: "migration_operation_not_found" } } } :
    url.includes("migration-preview") ? preview : page([issue()]));
  await env.controller.check(); await env.controller.preview("book");
  env.get("migration-confirm-check").checked = true; await env.controller.confirm();
  assert.equal(env.posts().length, 1);
  assert.equal(env.controller.operation, null);
  assert.equal(env.values.size, 0);
  assert.match(env.get("migration-note").textContent, /尚未开始.*重新预览/);
  await env.controller.check(); await env.controller.preview("book");
  assert.equal(env.get("migration-preview").hidden, false);
  const restored = setup(() => page([issue()]), env.values);
  await restored.controller.restore();
  assert.equal(restored.requests.length, 0);
});

test("丢响应或5xx即使状态404也保留原操作，未绑定证据的409同样不能解锁", async () => {
  for (const failure of ["lost", "5xx", "409-without-proof", "foreign-proof"]) {
    const env = setup((url, options) => {
      if (options.method === "POST") {
        if (failure === "lost") throw new Error("lost response");
        return { status: failure === "5xx" ? 503 : 409, body: { error: { code: "preview_stale", operation_created: false,
          operation_id: failure === "foreign-proof" ? "foreign" : OP, ...(failure === "409-without-proof" ? {} : {project_id:"book"}) } } };
      }
      return url.includes("/migrations/") ? { status:404, body:{error:{code:"migration_operation_not_found"}} } :
        url.includes("migration-preview") ? preview : page([issue()]);
    });
    await env.controller.check(); await env.controller.preview("book");
    env.get("migration-confirm-check").checked = true; await env.controller.confirm();
    assert.equal(env.posts().length, 1, failure);
    assert.equal(env.controller.operation.operation_id, OP, failure);
    assert.deepEqual([...env.values.values()], [OP], failure);
    assert.equal(env.controller.previewButtons[0].disabled, true, failure);
    const restored = setup(() => ({status:404, body:{error:{code:"migration_operation_not_found"}}}), env.values);
    await restored.controller.restore(); await restored.controller.preview("book");
    assert.equal(restored.requests.length, 1, failure);
    assert.equal(restored.posts().length, 0, failure);
  }
});

test("核对与再次确认继续是两个独立操作，不自动连做", async () => {
  let status = state("needs_reconciliation");
  const env = setup((url, options) => {
    if (options.method === "POST") {
      const body = JSON.parse(options.body);
      status = body.command_id === "reconcile_project_directory" ? state("backup_verified", { continuation_no: 4, actions: ["reconcile", "continue"] }) : state("verified");
      return { status: "accepted" };
    }
    return status;
  }, new Map([["creative-os-directory-operation", OP]]));
  await env.controller.restore(); await env.controller.reconcile();
  assert.equal(env.posts().length, 1);
  assert.match(env.posts()[0].url, /reconcile-project-directory$/);
  env.controller.beginContinue(); await env.controller.confirm();
  assert.equal(env.posts().length, 1);
  env.get("migration-confirm-check").checked = true; await env.controller.confirm();
  assert.equal(env.posts().length, 2);
  const body = JSON.parse(env.posts()[1].options.body);
  assert.equal(body.payload.continuation_no, 4);
  assert.equal(body.idempotency_key, "directory-continue:" + OP + ":4");
});

test("早期状态404后成功读回verified必须清除过期失败提示", async () => {
  let release, reads = 0;
  const env = setup((url, options) => {
    if (options.method === "POST") return new Promise(resolve => { release = resolve; });
    if (url.includes("migration-preview")) return preview;
    return ++reads === 1 ? {status:404, body:{error:{code:"migration_operation_not_found"}}} : state("verified");
  });
  await env.controller.preview("book"); env.get("migration-confirm-check").checked = true;
  const submitted = env.controller.confirm();
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  release({status:"accepted"}); await submitted;
  assert.equal(env.get("migration-status").dataset.stage, "verified");
  assert.doesNotMatch(env.get("migration-note").textContent, /读取失败|详情可能过期|响应尚未确认/);
});

test("只有已完成迁移才提示旧默认入口重载，失败和待核对不提示重启", async () => {
  for (const stage of ["failed", "moving", "verified"]) {
    const env = setup(() => state(stage, {reload_required:true}), new Map([["creative-os-directory-operation", OP]]));
    await env.controller.restore();
    if (stage === "verified") assert.match(env.get("migration-reload").textContent, /重载/);
    else assert.equal(env.get("migration-reload").textContent, "", stage);
  }
});

test("非JSON错误显示中文，Escape关闭返回入口焦点", async () => {
  const env = setup(() => ({ malformed: true }));
  env.controller.open(); await env.controller.check();
  assert.match(env.get("issues-summary").textContent, /读取|失败|过期/);
  assert.doesNotMatch(env.get("issues-summary").textContent, /Not found/);
  env.get("issues-panel").events.cancel({ preventDefault() {} });
  assert.equal(env.doc.activeElement, env.get("view-issues"));
  assert.equal(env.posts().length, 0);
});
