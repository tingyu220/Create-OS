(() => {
  const $ = (id) => document.getElementById(id);
  const editor = $("editor");
  let currentVersion = null;
  let projectId = "civilization-ascension";
  const chapter = () => Number($("chapter-number").value);

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

  $("open-chapter").addEventListener("click", openChapter);
  $("save-draft").addEventListener("click", saveDraft);
  $("toggle-preview").addEventListener("click", () => { $("preview").hidden = !$("preview").hidden; $("preview").textContent = editor.value; editor.hidden = !editor.hidden; });
})();
