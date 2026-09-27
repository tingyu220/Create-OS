(() => {
  const $ = (id) => document.getElementById(id);
  const editor = $("editor");
  let currentVersion = null;
  let projectId = null;
  let saveTimer = null;
  const chapter = () => Number($("chapter-number").value);
  const initialChapter = new URLSearchParams(window.location.search).get("chapter");
  if (initialChapter && Number.isInteger(Number(initialChapter))) $("chapter-number").value = initialChapter;

  async function refreshProjectContext() {
    const response = await fetch("/api/workspace");
    if (!response.ok) return;
    const data = await response.json(); projectId = data.project_id;
    const writerResponse = await fetch("/api/writer/context");
    const writerContext = writerResponse.ok ? await writerResponse.json() : null;
    const snapshot = data.snapshot; const operations = data.operations;
    const items = [
      `项目：${projectId}`,
      `正式章节正文：${writerContext?.formal_chapter_count ?? "暂不可用"} 章`,
      `当前工作稿：${writerContext?.working_draft_count ?? "暂不可用"} 章`,
      `工作稿章节：${writerContext?.working_draft_chapters?.join("、") || "暂无"}`,
      `运行状态投影：${snapshot?.chapters?.length ?? "暂不可用"} 条${data.overall === "partial" ? "（数据不完整）" : ""}`,
      `当前阶段：${snapshot?.overview?.current_stage && snapshot.overview.current_stage !== "unknown" ? snapshot.overview.current_stage : "暂未提供"}`,
      `运行记录：${operations?.execution_count ?? "暂不可用"} 条`,
    ];
    $("agent-context").replaceChildren(...items.map(value => { const node=document.createElement("div"); node.className="context-item"; node.textContent=value; return node; }));
  }

  async function openChapter(source = "auto") {
    $("source-status").textContent = "正在读取…";
    const response = await fetch(`/api/writer/chapters/${chapter()}?source=${source}`);
    const data = await response.json();
    if (!data.chapter) { $("source-status").textContent = "章节内容暂不可用"; editor.value = ""; return; }
    projectId = data.chapter.project_id;
    $("chapter-title").textContent = data.chapter.title;
    editor.value = data.chapter.content;
    updateWordCount();
    currentVersion = data.chapter.version ? data.chapter.version.version : null;
    $("source-status").textContent = `${data.chapter.source.label} · ${data.chapter.source.editable ? "可编辑" : "首次编辑将创建工作稿"}`;
  }

  function updateWordCount() { $("word-count").textContent = `${editor.value.replace(/\s/g, "").length} 字`; }

  async function submitAgentIntent(instruction) {
    if (!instruction.trim()) { $("agent-thread").textContent = "请直接告诉 Agent 你的目标。"; return; }
    $("agent-state-text").textContent = "正在读取上下文并建立任务…";
    $("agent-thread").textContent = `你：${instruction}\n\nAgent：正在读取项目状态、当前章节与相关上下文。`;
    const response = await fetch("/api/agent/intents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: projectId, chapter_number: chapter(), actor: "作者", instruction }) });
    const data = await response.json();
    if (data.job_id) {
      $("agent-state-text").textContent = "任务已排队";
      $("agent-thread").textContent += `\n\nAgent：${data.message}\n任务编号：${data.job_id}`;
      const labels = { queued: "等待执行", reading_context: "正在读取上下文", thinking: "正在生成正文", saving: "正在保存工作稿", completed: "已完成", failed: "运行失败" };
      const poll = async () => {
        const result = await fetch(`/api/agent/jobs/${data.job_id}`);
        if (!result.ok) { $("agent-state-text").textContent = "状态读取失败，正在重试"; window.setTimeout(poll, 2500); return; }
        const job = await result.json();
        $("agent-state-text").textContent = labels[job.status] || job.status;
        $("agent-thread").textContent = `你：${instruction}\n\nAgent：${job.message}\n\n最近更新：${job.updated_at || "—"}`;
        await refreshProjectContext();
        if (job.status === "completed") { $("chapter-number").value = job.chapter_number; await openChapter(); await loadVersions(); }
        else if (job.status !== "failed") window.setTimeout(poll, 1500);
      };
      window.setTimeout(poll, 800);
    } else { $("agent-state-text").textContent = "任务未能受理"; $("agent-thread").textContent += `\n\nAgent：${data.error?.message || "请求未完成"}`; }
  }

  async function saveDraft() {
    $("save-status").textContent = "正在保存…";
    const response = await fetch("/api/commands/save-writer-draft", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      command_id: "save_writer_draft", request_id: `writer-${Date.now()}`, actor: "作者", target: { project_id: projectId, chapter_number: chapter() }, payload: { content: editor.value }, expected_version: currentVersion, idempotency_key: `writer-${chapter()}-${Date.now()}`
    }) });
    const data = await response.json();
    if (data.status === "accepted") { currentVersion = (currentVersion || 0) + 1; $("save-status").textContent = `已保存第 ${currentVersion} 个版本`; }
    else { $("save-status").textContent = data.error?.message || "保存失败"; }
  }

  async function loadVersions() {
    const response = await fetch(`/api/writer/chapters/${chapter()}/versions`);
    const data = await response.json();
    $("versions").innerHTML = data.versions.length ? data.versions.map(v => `<button data-version="${v.version}">版本 ${v.version} · ${v.actor}</button>`).join(" ") : "暂无工作稿版本";
    $("versions").querySelectorAll("button").forEach(button => button.addEventListener("click", () => restoreVersion(Number(button.dataset.version))));
  }

  async function restoreVersion(version) {
    const response = await fetch("/api/commands/restore-writer-version", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      command_id: "restore_writer_version", request_id: `restore-${Date.now()}`, actor: "作者", target: { project_id: projectId, chapter_number: chapter() }, payload: { version }, expected_version: currentVersion, idempotency_key: `restore-${chapter()}-${version}-${Date.now()}`
    }) });
    const data = await response.json();
    if (data.status === "accepted") { currentVersion = (currentVersion || 0) + 1; await openChapter(); $("save-status").textContent = "已恢复并创建新版本"; await loadVersions(); }
    else $("save-status").textContent = data.error?.message || "恢复失败";
  }

  async function publishDraft() {
    if (!currentVersion) { $("save-status").textContent = "当前没有可发布的工作稿版本"; return; }
    if (!window.confirm(`确认将第 ${chapter()} 章当前工作稿发布为正式稿？`)) return;
    const response = await fetch("/api/commands/publish-writer-draft", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      command_id: "publish_writer_draft", request_id: `publish-${Date.now()}`, actor: "作者", target: { project_id: projectId, chapter_number: chapter() }, payload: { version: currentVersion }, expected_version: currentVersion, idempotency_key: `publish-${chapter()}-${currentVersion}-${Date.now()}`
    }) });
    const data = await response.json();
    if (data.status === "accepted") { $("save-status").textContent = "已发布为正式稿"; await refreshProjectContext(); await openChapter(); }
    else $("save-status").textContent = data.error?.message || "发布失败";
  }

  $("open-chapter").addEventListener("click", () => openChapter());
  $("view-formal").addEventListener("click", () => openChapter("formal"));
  $("view-draft").addEventListener("click", () => openChapter("draft"));
  $("save-draft").addEventListener("click", saveDraft);
  $("publish-draft").addEventListener("click", publishDraft);
  $("load-versions").addEventListener("click", loadVersions);
  $("agent-check").addEventListener("click", () => submitAgentIntent("这一章目前写得不对，你自己检查一下。"));
  $("agent-continue").addEventListener("click", () => submitAgentIntent(`读取项目已有数据和前文，继续写第 ${chapter()} 章。`));
  $("agent-send").addEventListener("click", () => submitAgentIntent($("agent-instruction").value));
  editor.addEventListener("input", () => { updateWordCount(); window.clearTimeout(saveTimer); $("save-status").textContent = "有未保存修改"; saveTimer = window.setTimeout(saveDraft, 1200); });
  refreshProjectContext();
  window.setInterval(refreshProjectContext, 5000);
  $("toggle-preview").addEventListener("click", () => { $("preview").hidden = !$("preview").hidden; $("preview").textContent = editor.value; editor.hidden = !editor.hidden; });
})();
