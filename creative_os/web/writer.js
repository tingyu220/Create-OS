(() => {
  const $ = (id) => document.getElementById(id);
  const editor = $("editor");
  let currentVersion = null;
  let projectId = null;
  let saveTimer = null;
  const chapter = () => Number($("chapter-number").value);

  async function loadProjectId() {
    const response = await fetch("/api/workspace");
    if (response.ok) projectId = (await response.json()).project_id;
  }

  async function openChapter() {
    $("source-status").textContent = "正在读取…";
    const response = await fetch(`/api/writer/chapters/${chapter()}`);
    const data = await response.json();
    if (!data.chapter) { $("source-status").textContent = "章节内容暂不可用"; editor.value = ""; return; }
    projectId = data.chapter.project_id;
    $("chapter-title").textContent = data.chapter.title;
    editor.value = data.chapter.content;
    currentVersion = data.chapter.version ? data.chapter.version.version : null;
    $("source-status").textContent = `${data.chapter.source.label} · ${data.chapter.source.editable ? "可编辑" : "首次编辑将创建工作稿"}`;
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

  $("open-chapter").addEventListener("click", openChapter);
  $("save-draft").addEventListener("click", saveDraft);
  $("load-versions").addEventListener("click", loadVersions);
  $("agent-check").addEventListener("click", async () => {
    const response = await fetch("/api/agent/intents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: projectId, chapter_number: chapter(), actor: "作者", instruction: "这一章目前写得不对，你自己检查一下。" }) });
    const data = await response.json();
    $("agent-status").textContent = data.message || data.error?.message || "Agent 请求未完成";
  });
  editor.addEventListener("input", () => { window.clearTimeout(saveTimer); $("save-status").textContent = "有未保存修改"; saveTimer = window.setTimeout(saveDraft, 1200); });
  loadProjectId();
  $("toggle-preview").addEventListener("click", () => { $("preview").hidden = !$("preview").hidden; $("preview").textContent = editor.value; editor.hidden = !editor.hidden; });
})();
