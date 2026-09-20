const $ = (id) => document.getElementById(id);
let currentProjectId = "";
let chapterRows = [];
let reviewIssue = null;

function text(value, fallback = "未提供") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function setStatus(element, status) {
  element.textContent = text(status);
  element.className = `status-badge status-${status || "unavailable"}`;
}

function setSectionStatus(element, status) {
  element.textContent = text(status);
  element.className = `tag tag-${status || "unknown"}`;
}

function tag(status) {
  const span = document.createElement("span");
  span.className = `tag tag-${status || "unknown"}`;
  span.textContent = text(status, "unknown");
  return span;
}

function sourceLabel(ref) {
  return `${text(ref.source_kind)} / ${text(ref.source_id)} / ${text(ref.locator)} · ${text(ref.content_hash, "无 hash")}`;
}

function renderSources(container, refs) {
  container.replaceChildren();
  if (!refs || refs.length === 0) { container.textContent = "未提供来源引用"; return; }
  refs.forEach((ref) => { const item = document.createElement("div"); item.className = "source-item"; item.textContent = sourceLabel(ref); container.append(item); });
}

function renderStack(container, items, empty) {
  container.replaceChildren();
  if (!items || items.length === 0) { container.textContent = empty; return; }
  items.forEach((item) => {
    const block = document.createElement("div"); block.className = "stack-item";
    const title = document.createElement("strong"); title.textContent = text(item.code || item.gate_id || item.message); block.append(title);
    const detail = document.createElement("small"); detail.textContent = text(item.message || item.status || item.scope); block.append(detail);
    if (item.source_refs?.length) { const refs = document.createElement("small"); refs.textContent = item.source_refs.map(sourceLabel).join("\n"); block.append(refs); }
    if (container.id === "quality-issues") {
      const state = item.disposition_status || (item.blocking ? "blocking" : "open");
      const stateLine = document.createElement("small"); stateLine.className = "review-state"; stateLine.textContent = `状态：${state}`; block.append(stateLine);
      if (!item.blocking && state !== "accepted") {
        const button = document.createElement("button"); button.type = "button"; button.className = "review-accept"; button.textContent = "接受问题";
        button.addEventListener("click", () => openReviewForm(item)); block.append(button);
      }
    }
    container.append(block);
  });
}

function openReviewForm(issue) {
  reviewIssue = issue;
  $("review-accept-form").hidden = false;
  $("review-accept-issue").textContent = `${text(issue.code)} · ${text(issue.issue_id)}`;
  $("review-result-id").value = text(issue.reviewer_result_id, "");
  $("review-result-hash").value = text(issue.reviewer_result_hash, "");
  $("review-version").value = text(issue.expected_version, "1");
  $("review-command-status").textContent = issue.reviewer_result_id ? "请核对审阅凭证后提交。" : "当前投影未提供审阅凭证，无法安全提交。";
}

function closeReviewForm() { reviewIssue = null; $("review-accept-form").hidden = true; }

function renderRuntimeDetails(operations) {
  const tasks = operations ? operations.tasks || [] : [];
  const errors = operations ? operations.errors || [] : [];
  const retries = operations ? operations.retries || [] : [];
  renderStack($("runtime-tasks"), tasks.map((item) => ({
    code: item.task_id,
    message: `${text(item.status)} · attempts ${text(item.attempts)} · elapsed ${item.elapsed_seconds == null ? "未提供" : `${item.elapsed_seconds}s`}`,
    source_refs: item.source_refs,
  })), "暂无任务记录");
  renderStack($("runtime-errors"), errors.map((item) => ({
    code: item.code,
    message: `${text(item.message)} · ${item.retryable === true ? "可重试" : item.retryable === false ? "不可重试" : "重试性未提供"}`,
    source_refs: item.source_refs,
  })), "暂无错误记录");
  const recovery = operations ? operations.recovery : null;
  renderStack($("runtime-recovery"), recovery ? [{ code: "recovery", message: text(recovery.state), source_refs: recovery.source_refs }] : [], "未提供恢复状态");
  renderStack($("runtime-retries"), retries.map((item) => ({ code: "retry", message: `attempts ${text(item.attempts)}`, source_refs: item.source_refs })), "未提供重试状态");
}

async function acceptReviewIssue(event) {
  event.preventDefault();
  if (!reviewIssue) return;
  const status = $("review-command-status");
  const reason = $("review-reason").value.trim();
  const reviewerResultId = $("review-result-id").value.trim();
  const reviewerResultHash = $("review-result-hash").value.trim();
  if (!reason || !reviewerResultId || !/^[0-9a-f]{64}$/.test(reviewerResultHash)) { status.textContent = "请填写完整且有效的审阅凭证。"; return; }
  const identity = commandIdentity();
  status.textContent = "提交中…";
  try {
    const reviewEndpoint = "/api/commands/" + "accept-review-issue";
    const response = await fetch(reviewEndpoint, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({
      command_id: "accept_review_issue", request_id: identity.request_id, actor: "local-user",
      target: { project_id: currentProjectId, issue_id: reviewIssue.issue_id }, payload: { reason, reviewer_result_id: reviewerResultId, reviewer_result_hash: reviewerResultHash, expected_version: Number($("review-version").value) }, expected_version: null, idempotency_key: identity.idempotency_key,
    }) });
    const result = await response.json();
    status.textContent = result.status === "accepted" ? "已接受，正在刷新投影…" : `${result.status || "失败"}${result.error?.code ? ` · ${result.error.code}` : ""}: ${result.error?.message || ""}`;
    if (result.status === "accepted") { closeReviewForm(); await loadWorkspace(); }
  } catch (error) { status.textContent = `请求失败：${error.message}`; }
}

function render(data) {
  currentProjectId = text(data.project_id, "");
  $("project-name").textContent = text(data.project_id);
  setStatus($("overall-status"), data.overall);
  setSectionStatus($("overview-section-status"), data.sections?.project?.status);
  setSectionStatus($("chapters-section-status"), data.sections?.project?.status);
  setSectionStatus($("quality-section-status"), data.sections?.project?.status);
  setSectionStatus($("runtime-section-status"), data.sections?.operations?.status);
  $("refresh-meta").textContent = `refresh ${text(data.refresh_id, "未提供")} · snapshot ${text(data.snapshot?.snapshot_id, "未提供")}`;
  const diagnostics = Object.entries(data.sections || {}).flatMap(([section, value]) => (value.diagnostics || []).map((item) => `${section}: ${item.code} · ${item.message}`));
  const uniqueDiagnostics = [...new Set(diagnostics)];
  $("notice").hidden = uniqueDiagnostics.length === 0;
  if (uniqueDiagnostics.length) $("notice").textContent = `投影诊断（${uniqueDiagnostics.length}）：${uniqueDiagnostics.slice(0, 3).join(" ｜ ")}${uniqueDiagnostics.length > 3 ? " ｜ …" : ""}`;
  const snapshot = data.snapshot;
  if (!snapshot) {
    $("notice").hidden = false; $("notice").textContent = "当前投影不可用，工作台没有根据来源文件推断业务状态。";
    return;
  }
  const overview = snapshot.overview;
  $("current-stage").textContent = text(overview.current_stage);
  $("run-status").replaceChildren(tag(overview.run_status));
  $("chapter-count").textContent = text(overview.chapter_count, "0");
  $("blocked-count").textContent = text(overview.blocked_chapter_count, "0");
  renderStack($("blockers"), overview.blockers, "暂无阻塞摘要");
  renderSources($("overview-sources"), overview.source_refs);

  chapterRows = snapshot.chapters || [];
  renderChapterMatrix();

  const quality = snapshot.quality;
  $("quality-summary").textContent = `${quality.issues.length} issues · ${quality.gate_results.length} gates · ${quality.issues.filter((item) => item.blocking).length} blocking`;
  renderStack($("quality-issues"), quality.issues, "暂无质量问题");
  renderStack($("gate-results"), quality.gate_results, "暂无 Gate 结果");
  const operations = data.operations;
  if (operations) {
    $("execution-count").textContent = text(operations.execution_count, "未提供");
    $("attempt-count").textContent = text(operations.attempts, "未提供");
    $("usage").textContent = operations.usage ? text(operations.usage.total_tokens) : "未提供";
    $("runtime-summary").textContent = `${text(operations.diagnostics?.length, "0")} diagnostics · ${text(operations.errors?.length, "0")} errors`;
    renderRuntimeDetails(operations);
  } else {
    renderRuntimeDetails(null);
  }
  const trace = $("trace-list"); trace.replaceChildren();
  const entries = (snapshot.trace?.entries || []).slice(-100);
  if (!entries.length) { trace.textContent = "暂无运行轨迹"; }
  entries.forEach((entry) => {
    const item = document.createElement("div"); item.className = "trace-entry";
    const seq = document.createElement("div"); seq.className = "trace-seq"; seq.textContent = entry.sequence == null ? "REPORT" : `#${entry.sequence}`; item.append(seq);
    const summary = document.createElement("div"); summary.className = "trace-summary"; summary.textContent = entry.summary; item.append(summary);
    const meta = document.createElement("div"); meta.className = "trace-meta"; meta.textContent = `${entry.event_type} · ${entry.occurred_at}${entry.source_refs?.length ? `\n${entry.source_refs.map(sourceLabel).join("\n")}` : ""}`; item.append(meta);
    trace.append(item);
  });
}

function renderChapterMatrix() {
  const query = $("chapter-filter").value.trim().toLocaleLowerCase();
  const visible = chapterRows.filter((chapter) => `${chapter.title || ""} ${chapter.chapter_id || ""}`.toLocaleLowerCase().includes(query));
  const tbody = $("chapters-table"); tbody.replaceChildren();
  $("chapter-filter-count").textContent = query ? `${visible.length}/${chapterRows.length} 章` : `${chapterRows.length} 章`;
  if (!visible.length) { const row = document.createElement("tr"); const cell = document.createElement("td"); cell.colSpan = 7; cell.className = "empty-row"; cell.textContent = "没有匹配的章节"; row.append(cell); tbody.append(row); return; }
  visible.forEach((chapter) => {
    const row = document.createElement("tr");
    const name = document.createElement("td"); name.innerHTML = `<div class="chapter-title"></div><div class="chapter-id"></div>`; name.firstChild.textContent = chapter.title; name.lastChild.textContent = chapter.chapter_id; row.append(name);
    const status = document.createElement("td"); status.append(tag(chapter.status));
    if (chapter.checkpoint_state) { const checkpoint = document.createElement("div"); checkpoint.className = "chapter-id"; checkpoint.textContent = `checkpoint: ${chapter.checkpoint_state}`; status.append(checkpoint); }
    row.append(status);
    const attempts = document.createElement("td"); attempts.textContent = text(chapter.attempts, "未提供"); row.append(attempts);
    const elapsed = document.createElement("td"); elapsed.textContent = chapter.elapsed_seconds == null ? "未提供" : `${chapter.elapsed_seconds}s`; row.append(elapsed);
    const stages = document.createElement("td"); stages.className = "stage-list"; (chapter.stages || []).forEach((stage) => { const item = document.createElement("span"); item.className = "tag tag-unknown"; item.textContent = `${stage.stage}:${stage.status}`; stages.append(item); }); row.append(stages);
    const refs = document.createElement("td"); refs.className = "provenance"; refs.textContent = chapter.source_refs?.map(sourceLabel).join("\n") || "未提供来源引用"; row.append(refs);
    const action = document.createElement("td");
    const run = document.createElement("button"); run.type = "button"; run.className = "chapter-run"; run.textContent = "启动运行";
    run.addEventListener("click", () => startChapterRun(chapter)); action.append(run); row.append(action);
    tbody.append(row);
  });
}

async function startChapterRun(chapter) {
  const status = $("chapter-command-status");
  const chapterNumber = Number(chapter.chapter_number);
  if (!Number.isInteger(chapterNumber) || chapterNumber <= 0) { status.textContent = "章节编号不可用，已拒绝命令。"; return; }
  const identity = commandIdentity();
  status.textContent = `第 ${chapterNumber} 章启动中…`;
  try {
    const response = await fetch("/api/commands/start-chapter-run", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({
      command_id: "start_chapter_run", request_id: identity.request_id, actor: "local-user",
      target: { project_id: currentProjectId, chapter_number: chapterNumber }, payload: {}, expected_version: null, idempotency_key: identity.idempotency_key,
    }) });
    const result = await response.json();
    status.textContent = result.status === "accepted" ? `第 ${chapterNumber} 章运行已接受` : `${result.status || "失败"}${result.error?.code ? ` · ${result.error.code}` : ""}`;
    if (result.status === "accepted") await loadWorkspace();
  } catch (error) { status.textContent = `章节运行失败：${error.message}`; }
}

function commandIdentity() {
  const id = crypto.randomUUID();
  return { request_id: id, idempotency_key: id };
}

function renderCommandResult(result) {
  const status = $("command-status");
  const diagnostics = $("command-diagnostics");
  const error = result.error;
  const code = error?.code ? ` · ${error.code}` : "";
  status.textContent = result.status === "accepted" ? "刷新已接受" : `${result.status || "失败"}${code}`;
  diagnostics.hidden = false;
  diagnostics.textContent = [
    error?.message,
    result.trace_id ? `trace_id: ${result.trace_id}` : "",
    result.projection_refresh_id ? `projection_refresh_id: ${result.projection_refresh_id}` : "",
  ].filter(Boolean).join(" · ") || "未提供诊断信息";
}

async function refreshWorkspace() {
  const button = $("refresh-workspace");
  const status = $("command-status");
  const diagnostics = $("command-diagnostics");
  button.disabled = true;
  status.textContent = "刷新中…";
  diagnostics.hidden = true;
  try {
    const identity = commandIdentity();
    const response = await fetch("/api/commands/refresh-workspace", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        command_id: "refresh_workspace_projection",
        request_id: identity.request_id,
        actor: "local-user",
        target: currentProjectId,
        payload: { sections: ["project", "operations"] },
        expected_version: null,
        idempotency_key: identity.idempotency_key,
      }),
    });
    const result = await response.json();
    renderCommandResult(result);
    if (result.status === "accepted") await loadWorkspace();
  } catch (error) {
    status.textContent = "刷新失败";
    diagnostics.hidden = false;
    diagnostics.textContent = `请求失败 · ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

async function loadWorkspace() {
  try {
    const response = await fetch("/api/workspace", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    $("overall-status").textContent = "读取失败";
    $("notice").hidden = false; $("notice").textContent = `只读投影 API 暂时不可用：${error.message}`;
  }
}

loadWorkspace();
$("refresh-workspace").addEventListener("click", refreshWorkspace);
$("chapter-filter").addEventListener("input", renderChapterMatrix);
$("review-accept-form").addEventListener("submit", acceptReviewIssue);
$("review-cancel").addEventListener("click", closeReviewForm);
