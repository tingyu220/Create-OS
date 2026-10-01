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
  function wordTarget() {
    const target = Math.max(1, Number($("agent-target-words").value) || 4500);
    const tolerance = Math.max(0, Number($("agent-tolerance-words").value) || 0);
    $("agent-word-range").textContent = `范围：${Math.max(1, target - tolerance)}–${target + tolerance} 字`;
    return { target_words: target, tolerance_words: tolerance };
  }

  async function submitAgentIntent(instruction) {
    if (!instruction.trim()) { $("agent-thread").textContent = "请直接告诉 Agent 你的目标。"; return; }
    document.getElementById("agent-act")?.remove();
    $("agent-state-text").textContent = "正在读取上下文并建立任务…";
    $("agent-thread").textContent = `你：${instruction}\n\nAgent：正在读取项目状态、当前章节与相关上下文。`;
    const response = await fetch("/api/agent/intents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: projectId, chapter_number: chapter(), actor: "作者", instruction, ...wordTarget() }) });
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
        const range = job.min_words ? `\n字数要求：${job.target_words} ± ${job.tolerance_words}（${job.min_words}–${job.max_words}）` : "";
        const actual = job.actual_words == null ? "" : `\n实际字数：${job.actual_words}（${job.within_word_range ? "在范围内" : "超出范围"}）`;
        $("agent-thread").textContent = `你：${instruction}\n\nAgent：${job.message}${range}${actual}\n\n最近更新：${job.updated_at || "—"}`;
        if (job.decision_id) {
          const decisionResponse = await fetch(`/api/agent/decisions/${job.decision_id}`);
          if (decisionResponse.ok) {
            const decision = await decisionResponse.json();
            $("agent-thread").textContent += `\n\n创作决策：${decision.decision_id}\n分析：${decision.analysis}\n依据：${(decision.context_refs || []).join("、")}`;
            if (!document.getElementById("agent-act")) {
              const button = document.createElement("button"); button.id = "agent-act"; button.className = "primary"; button.textContent = "按此方案修改";
              button.addEventListener("click", async () => {
                if (!window.confirm("确认让 Agent 按此方案生成新的工作稿？")) return;
                const act = await fetch("/api/agent/decisions/act", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision_id: decision.decision_id, actor: "作者" }) });
                const result = await act.json(); $("agent-thread").textContent += `\n\n${result.job_id ? "已确认执行，任务已排队。" : result.error?.message || "执行失败"}`; button.disabled = true;
                if (result.job_id) {
                  const pollAct = async () => {
                    const status = await (await fetch(`/api/agent/jobs/${result.job_id}`)).json();
                    $("agent-state-text").textContent = status.status === "completed" ? "修改方案已执行" : (status.status === "failed" ? "执行失败" : "正在按方案修改");
                    if (status.status === "completed") {
                      $("chapter-number").value = status.chapter_number; await openChapter("draft"); await loadVersions();
                      const diff = await (await fetch(`/api/writer/chapters/${status.chapter_number}/diff`)).json();
                      const diffPanel = $("agent-diff"); diffPanel.hidden = false; diffPanel.textContent = `修改差异\n${diff.diff || "没有检测到差异"}`;
                    } else if (status.status !== "failed") window.setTimeout(pollAct, 1500);
                  };
                  window.setTimeout(pollAct, 800);
                }
              });
              $("agent-thread").after(button);
            }
          }
        }
        await refreshProjectContext();
        if (job.status === "completed") { $("chapter-number").value = job.chapter_number; await openChapter(); await loadVersions(); await refreshProjectContext(); }
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
    if (data.status === "accepted") { const before = currentVersion; const latest = await loadVersions(); currentVersion = latest ?? currentVersion; $("save-status").textContent = currentVersion === before ? "内容未变化，未创建新版本" : `已保存第 ${currentVersion} 个版本`; }
    else { $("save-status").textContent = data.error?.message || "保存失败"; }
  }

  async function loadVersions() {
    const response = await fetch(`/api/writer/chapters/${chapter()}/versions`);
    const data = await response.json();
    $("versions").innerHTML = data.versions.length ? data.versions.map(v => `<button data-version="${v.version}">版本 ${v.version} · ${v.actor}</button>`).join(" ") : "暂无工作稿版本";
    $("versions").querySelectorAll("button").forEach(button => button.addEventListener("click", () => restoreVersion(Number(button.dataset.version))));
    return data.versions.length ? Math.max(...data.versions.map(v => v.version)) : null;
  }

  async function restoreVersion(version) {
    const response = await fetch("/api/commands/restore-writer-version", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      command_id: "restore_writer_version", request_id: `restore-${Date.now()}`, actor: "作者", target: { project_id: projectId, chapter_number: chapter() }, payload: { version }, expected_version: currentVersion, idempotency_key: `restore-${chapter()}-${version}-${Date.now()}`
    }) });
    const data = await response.json();
    if (data.status === "accepted") { const before = currentVersion; await openChapter(); const latest = await loadVersions(); currentVersion = latest ?? currentVersion; $("save-status").textContent = currentVersion === before ? "内容未变化，未创建新版本" : "已恢复并创建新版本"; }
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
  $("agent-target-words").addEventListener("input", wordTarget);
  $("agent-tolerance-words").addEventListener("input", wordTarget);
  wordTarget();
  editor.addEventListener("input", () => { updateWordCount(); window.clearTimeout(saveTimer); $("save-status").textContent = "有未保存修改"; saveTimer = window.setTimeout(saveDraft, 1200); });
  refreshProjectContext();
  window.setInterval(refreshProjectContext, 5000);
  $("toggle-preview").addEventListener("click", () => { $("preview").hidden = !$("preview").hidden; $("preview").textContent = editor.value; editor.hidden = !editor.hidden; });
})();
