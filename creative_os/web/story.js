/* 候选、正式版和异步任务分别展示；响应检查当前项目代次。 */
(() => {
  const $ = id => document.getElementById(id);
  const match = window.location.pathname.match(/^\/p\/([^/]+)\/story$/);
  let projectId = match ? decodeURIComponent(match[1]) : null;
  let projectTitle = projectId;
  let composerBaseline = "";
  let sessionId = null, state = null, epoch = 0, readEpoch = 0, timer = null, dirty = false, busy = false, posting = 0, editorRevision = 0;
  let createOperation = crypto.randomUUID(), failedJob = null;
  const requests = new Map();
  const navigation = typeof WorkspaceNavigation === "undefined" ? null : new WorkspaceNavigation({ page: "story",
    isDirty: () => dirty || $("story-input").value !== composerBaseline || !projectId && !!($("book-title").value.trim() || $("book-idea").value.trim()) });
  if (navigation && !projectId) navigation.ready(null, "未命名新书");
  const scope = () => ({ project_id: projectId, scope: "story", session_id: sessionId });
  const status = text => { $("story-status").textContent = text; };
  async function json(path, options) {
    const response = await fetch(path, options);
    const value = await response.json();
    if (!response.ok || value.status === "rejected" || value.status === "failed") throw new Error(value.error?.message || value.error?.code || `请求失败 ${response.status}`);
    return value;
  }
  const post = (path, value) => json(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) });
  function setBusy(value) {
    value = !!(value || posting); busy = value;
    $("story-send").disabled = value;
    $("save-candidate").disabled = value || !state?.candidate;
    $("confirm-candidate").disabled = value || dirty || !state?.candidate || state.candidate.hash === state.confirmed?.hash;
    $("start-first-chapter").disabled = value || !state?.confirmed;
    $("story-retry").disabled = value;
    $("add-block").disabled = value || !state?.candidate;
    $("story-questions").disabled = value || !state?.candidate;
    $("candidate-blocks").querySelectorAll("input,textarea").forEach(element => { element.disabled = value; });
  }
  function markDirty() { dirty = true; $("discard-candidate").hidden = false; setBusy(busy); $("confirm-candidate").textContent = "请先保存编辑，再确认版本"; }
  function addBlock(block) {
    const container = document.createElement("div"); container.className = "story-block"; container.dataset.key = block.key;
    const title = document.createElement("input"); title.value = block.title; title.setAttribute("aria-label", "内容块标题");
    const text = document.createElement("textarea"); text.value = block.text; text.setAttribute("aria-label", block.title + "正文");
    title.addEventListener("input", markDirty); text.addEventListener("input", markDirty);
    container.append(title, text); $("candidate-blocks").append(container);
  }
  function render(value, force = false) {
    const changed = value.candidate?.hash !== state?.candidate?.hash;
    state = value;
    $("story-title").textContent = projectTitle || projectId;
    $("story-thread").replaceChildren();
    for (const message of value.messages) {
      const article = document.createElement("article"); article.className = "story-message";
      const label = document.createElement("strong"); label.textContent = message.role === "user" ? "你" : "故事 Agent";
      const body = document.createElement("div"); body.textContent = message.content; article.append(label, body); $("story-thread").append(article);
    }
    if ((changed && !dirty) || force) {
      dirty = false; editorRevision = value.candidate?.revision || 0; $("discard-candidate").hidden = true; $("candidate-blocks").replaceChildren();
      for (const block of value.candidate?.content.blocks || []) addBlock(block);
      $("story-questions").value = (value.candidate?.content.open_questions || []).join("\n");
    }
    $("candidate-version").textContent = value.candidate ? (dirty && editorRevision !== value.candidate.revision ? `编辑基于 v${editorRevision} · 当前候选 v${value.candidate.revision}` : `候选 v${value.candidate.revision}`) : "尚未形成候选";
    $("candidate-hash").textContent = value.candidate?.hash || "";
    $("confirm-candidate").textContent = dirty ? "请先保存编辑，再确认版本" : `明确确认候选 v${value.candidate?.revision || "—"}`;
    $("confirmed-title").textContent = value.confirmed ? `正式设定 v${value.confirmed.version} · 来自候选 v${value.confirmed.revision}` : "正式设定 · 尚未确认";
    $("confirmed-text").textContent = value.confirmed?.text || "继续讨论并确认一个候选版本后，即可开始第一章。";
    const latest = value.jobs.at(-1);
    failedJob = latest?.status === "failed" && latest.retryable ? latest.job_id : null;
    $("story-retry").hidden = !failedJob;
    const active = value.jobs.some(job => !["completed", "failed"].includes(job.status));
    setBusy(active);
    if (latest) status(latest.error || latest.message);
    clearTimeout(timer);
    if (active) timer = setTimeout(() => refresh(), 700);
  }
  async function refresh(force = false) {
    const token = epoch, readToken = ++readEpoch;
    try {
      const value = await json(`/api/story?${new URLSearchParams(scope())}`);
      if (token !== epoch || readToken !== readEpoch || value.project_id !== projectId || value.session_id !== sessionId) return;
      render(value, force);
      return true;
    } catch (error) { if (token === epoch && readToken === readEpoch) { status(error.message + "；可点击刷新重试。"); setBusy(true); } }
  }
  async function openProject() {
    const token = ++epoch;
    const bootstrap = await json(`/api/story/session?${new URLSearchParams({ project_id: projectId, scope: "story" })}`);
    if (token !== epoch || bootstrap.project_id !== projectId) return;
    sessionId = bootstrap.session_id;
    projectTitle = bootstrap.title || projectId;
    navigation?.ready(projectId, projectTitle);
    $("create-book").hidden = true; $("story-workspace").hidden = false;
    $("chapter-link").hidden = false; $("chapter-link").href = `/p/${encodeURIComponent(projectId)}/writer?chapter=1`;
    const opened = await refresh();
    if (opened && token === epoch) navigation?.opened({ page: "story", chapter_number: null, source: "auto" });
    if (bootstrap.idea && !state?.messages.length) { $("story-input").value = bootstrap.idea; composerBaseline = bootstrap.idea; }
  }
  $("create-book").addEventListener("submit", async event => {
    event.preventDefault(); const token = ++epoch; $("create-submit").disabled = true;
    try {
      const value = await post("/api/projects/create", { title: $("book-title").value, idea: $("book-idea").value, operation_id: createOperation });
      if (token !== epoch) return;
      const destination = `/p/${encodeURIComponent(value.project_id)}/story`;
      if (navigation) navigation.go(destination, true); else window.location.assign(destination);
    } catch (error) { if (token === epoch) { status(error.message); $("create-submit").disabled = false; } }
  });
  $("combat-expert-entry")?.addEventListener("click", async () => {
    const token = epoch; ++posting; ++readEpoch; setBusy(true);
    try { await post("/api/story/intents", { ...scope(), instruction: $("story-input").value.trim() || "请战斗专家分析当前故事的战斗冲突与未来计划。", requested_expert: "combat" }); --posting; if (token !== epoch) return; $("story-input").value = ""; composerBaseline = ""; await refresh(); }
    catch (error) { --posting; if (token === epoch) { status(error.message); setBusy(false); } }
  });
  $("story-composer").addEventListener("submit", async event => {
    event.preventDefault(); const token = epoch; ++posting; ++readEpoch; setBusy(true);
    try { await post("/api/story/intents", { ...scope(), instruction: $("story-input").value }); --posting; if (token !== epoch) return; $("story-input").value = ""; composerBaseline = ""; await refresh(); }
    catch (error) { --posting; if (token === epoch) { status(error.message); setBusy(false); } }
  });
  async function command(id, payload) {
    const identity = JSON.stringify({ id, target: scope(), payload });
    if (!requests.has(identity)) { const key = crypto.randomUUID(); requests.set(identity, { command_id: id, request_id: key, actor: "作者", target: scope(), payload, expected_version: null, idempotency_key: key }); }
    return post(`/api/commands/${id.replaceAll("_", "-")}`, requests.get(identity));
  }
  async function mutate(action) {
    const token = epoch; ++posting; ++readEpoch; setBusy(true);
    try { await action(); --posting; if (token === epoch) await refresh(true); }
    catch (error) { --posting; if (token === epoch) { status(error.message); setBusy(false); } }
  }
  $("add-block").addEventListener("click", () => { addBlock({ key: crypto.randomUUID(), title: "新内容", text: "" }); markDirty(); });
  $("story-questions").addEventListener("input", markDirty);
  $("save-candidate").addEventListener("click", () => mutate(() => command("edit_story_candidate", {
    expected_revision: editorRevision,
    blocks: [...$("candidate-blocks").children].map(element => ({ key: element.dataset.key, title: element.querySelector("input").value, text: element.querySelector("textarea").value })),
    open_questions: $("story-questions").value.split("\n").map(text => text.trim()).filter(Boolean)
  })));
  $("confirm-candidate").addEventListener("click", () => { if (!dirty) mutate(() => command("confirm_story_candidate", { revision: state.candidate.revision, hash: state.candidate.hash, expected_confirmed_version: state.confirmed?.version || 0 })); });
  $("story-retry").addEventListener("click", () => mutate(() => post("/api/story/retry", { ...scope(), job_id: failedJob })));
  $("story-refresh").addEventListener("click", () => refresh());
  $("discard-candidate").addEventListener("click", () => refresh(true));
  $("start-first-chapter").addEventListener("click", async () => {
    const token = epoch; ++posting; ++readEpoch; setBusy(true);
    try { await post("/api/story/start-first-chapter", { ...scope(), confirmed_version: state.confirmed.version, confirmed_hash: state.confirmed.hash, target_words: 4500, tolerance_words: 300 }); --posting; if (token === epoch) { const destination = `/p/${encodeURIComponent(projectId)}/writer?chapter=1`; if (navigation) navigation.go(destination, true); else window.location.assign(destination); } }
    catch (error) { --posting; if (token === epoch) { status(error.message); setBusy(false); } }
  });
  if (projectId) openProject().catch(error => status(error.message));
  function pane(name) {
    const frame = document.querySelector?.(".story-frame"); if (frame) frame.dataset.activePane = name;
  }
  document.querySelectorAll?.("[data-story-pane]").forEach(button => button.addEventListener("click", () => pane(button.dataset.storyPane)));
  $("show-confirmed")?.addEventListener("click", () => { pane("candidate"); $("confirmed-title").scrollIntoView?.({ block: "start" }); });
})();
