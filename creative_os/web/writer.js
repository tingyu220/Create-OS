(() => {
  const $ = (id) => document.getElementById(id);
  if (window.writerProjectPrefix) {
    const homeLink = document.querySelector(".writer-home");
    if (homeLink) { homeLink.href = window.writerProjectPrefix + "/story"; homeLink.textContent = "故事设定与讨论"; }
  }
  const editor = $("editor");
  let currentVersion = null;
  let projectId = null;
  let saveTimer = null;
  let editorScope = null;
  let pendingSave = null;
  let unconfirmedSave = null;
  let inFlightSave = null;
  let selectionEpoch = 0;
  let versionHistory = [];
  let currentSource = "auto";
  const publicationChecks = () => {
    const publicationPlatform = window.publicationPlatform || "tomato";
    const contentReady = Boolean(editor.value.trim());
    const titleReady = Boolean($("chapter-title").textContent && !$("chapter-title").textContent.includes("请选择"));
    const checks = {};
    ["source_revision_continuous", "chapter_title", "word_count", "structure_ok", "characters_consistent", "settings_consistent", "combat_ok", "sensitive_ok", "format_ok", "platform_match", "unpublished", "hash_unchanged"].forEach(name => { checks[name] = contentReady; });
    checks.source_revision_continuous = Number.isInteger(Number(currentVersion)) && Number(currentVersion) > 0;
    checks.chapter_title = titleReady;
    checks.platform_match = publicationPlatform === "tomato";
    checks.unpublished = true;
    checks.hash_unchanged = contentReady;
    return checks;
  };
  const publicationPanel = typeof PublicationPanel === "undefined" ? null : new PublicationPanel({ getScope: () => ({ projectId, chapter: chapter(), epoch: selectionEpoch }), getSnapshot: () => { const publicationPlatform = window.publicationPlatform || "tomato"; return ({ snapshot: { book_id: projectId, chapter_number: chapter(), source_revision: String(currentVersion || "draft"), content: editor.value }, target: { work_id: projectId, platform: publicationPlatform, title: $("project-name").textContent || projectId, chapter_number: chapter(), chapter_title: $("chapter-title").textContent || `第${chapter()}章` }, platform_name: publicationPlatform, work_id: projectId, checks: publicationChecks() }); } });
  const publicationOperation = new URLSearchParams(window.location.search).get("publication_operation_id");
  if (publicationPanel && publicationOperation) publicationPanel.operationId = publicationOperation;
  const chapter = () => Number($("chapter-number").value);
  const initialChapter = new URLSearchParams(window.location.search).get("chapter");
  const requestedSource = new URLSearchParams(window.location.search).get("source");
  const initialSource = ["formal", "draft", "auto"].includes(requestedSource) ? requestedSource : "auto";
  if (initialChapter && Number.isInteger(Number(initialChapter))) $("chapter-number").value = initialChapter;
  const navigation = typeof WorkspaceNavigation === "undefined" ? null : new WorkspaceNavigation({ page: "writer",
    isDirty: () => !!(pendingSave || unconfirmedSave || inFlightSave || editorScope && editor.value !== editorScope.savedContent),
    beforeLeave: () => window.clearTimeout(saveTimer) });
  const directory = typeof ChapterDirectory === "undefined" ? null : new ChapterDirectory(async (number, source, candidate) => {
    try {
      await selectChapter(number, source);
      if (candidate && chapter() === number) {
        const proposal = [...(agentConversation.session?.proposals || [])].reverse().find(item => item.chapter_number === number && item.result
          && (["pending", "reviewing"].includes(item.status) || item.review_recovery?.required));
        if (proposal) { await agentConversation.viewProposal(proposal.proposal_id); activateChapterTab("candidate"); }
      }
    } catch (error) { $("agent-state-text").textContent = error.message; }
  });

  function renderChapterNavigation(context) {
    const renderList = (targetId, chapters, source, emptyText) => {
      const target = $(targetId);
      target.replaceChildren();
      if (!chapters.length) {
        const empty = document.createElement("p");
        empty.className = "empty-state";
        empty.textContent = emptyText;
        target.append(empty);
        return;
      }
      chapters.forEach(chapterNumber => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.chapterNumber = String(chapterNumber);
        button.dataset.source = source;
        button.textContent = `第 ${chapterNumber} 章`;
        button.setAttribute("aria-current", chapterNumber === chapter() && source === currentSource ? "true" : "false");
        button.addEventListener("click", () => selectChapter(chapterNumber, source));
        target.append(button);
      });
    };
    const formalChapters = context?.formal_chapters || [];
    const draftChapters = context?.working_draft_chapters || [];
    const items = context?.chapters || [...new Set([...formalChapters, ...draftChapters])].map(number => ({ chapter_number: number, title: `第 ${number} 章`, has_formal: formalChapters.includes(number), has_draft: draftChapters.includes(number), pending_candidates: 0 }));
    directory?.update(items);
    $("formal-chapter-count").textContent = String(formalChapters.length);
    $("draft-chapter-count").textContent = String(draftChapters.length);
    renderList("formal-chapter-list", formalChapters, "formal", "暂无正式稿");
    renderList("draft-chapter-list", draftChapters, "draft", "暂无工作稿");
  }

  async function selectChapter(chapterNumber, source) {
    if (!Number.isInteger(chapterNumber) || chapterNumber <= 0) {
      $("agent-state-text").textContent = "请输入有效章节编号";
      return;
    }
    const epoch = ++selectionEpoch;
    editor.disabled = true;
    // 先完成绑定旧编辑会话的保存，再读取新章节；切章请求按代次取最后一次。
    if (!await flushSaves()) {
      if (epoch === selectionEpoch) {
        $("chapter-number").value = editorScope?.chapterNumber || chapterNumber;
        editor.disabled = false;
      }
      return;
    }
    if (epoch !== selectionEpoch) return;
    $("chapter-number").value = chapterNumber;
    const url = new URL(window.location.href);
    url.searchParams.set("chapter", chapterNumber);
    url.searchParams.set("source", source);
    window.history.replaceState(null, "", url);
    currentSource = source;
    editorScope = null;
    currentVersion = null;
    publicationPanel?.setScope({ projectId, chapter: chapterNumber, epoch });
    $("agent-candidate").textContent = "请选择候选提案阅读";
    $("agent-diff").textContent = "暂无冻结差异";
    document.querySelectorAll("[data-chapter-number]").forEach(button => {
      const selected = Number(button.dataset.chapterNumber) === chapterNumber && button.dataset.source === source;
      button.setAttribute("aria-current", selected ? "true" : "false");
    });
    await agentConversation.open(projectId);
    if (epoch !== selectionEpoch) return;
    try { await openChapter(source); }
    catch (error) {
      if (epoch === selectionEpoch) $("source-status").textContent = "章节读取失败，请重新打开章节；现有稿件未修改。";
      throw error;
    }
    if (epoch !== selectionEpoch) return;
    activateChapterTab("editor");
    activateWorkspacePanel("chapter");
    directory?.select(chapterNumber);
    await loadVersions();
    publicationPanel?.setScope({ projectId, chapter: chapterNumber, epoch });
    publicationPanel?.refresh();
  }

  function activateChapterTab(tabName) {
    document.querySelectorAll("[data-chapter-tab]").forEach(button => {
      button.setAttribute("aria-selected", button.dataset.chapterTab === tabName ? "true" : "false");
      if (button.dataset.chapterTab === tabName) button.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    });
    document.querySelectorAll("[data-chapter-panel]").forEach(panel => {
      panel.hidden = panel.dataset.chapterPanel !== tabName;
    });
    if (tabName === "preview") $("preview").textContent = editor.value;
  }

  function activateWorkspacePanel(panelName) {
    document.querySelector(".writer-grid").dataset.activePanel = panelName;
  }

  async function refreshProjectContext() {
    const response = await fetch("/api/workspace");
    if (!response.ok) { $("agent-state-text").textContent = "作品身份暂不可用，请刷新后重试。"; return false; }
    const data = await response.json(); projectId = data.project_id;
    const writerResponse = await fetch("/api/writer/context");
    const writerContext = writerResponse.ok ? await writerResponse.json() : null;
    if (writerContext?.project_id && writerContext.project_id !== projectId) throw new Error("作品目录身份不匹配");
    if (writerContext) renderChapterNavigation(writerContext);
    const title = writerContext?.title || projectId || "创作项目";
    $("project-name").textContent = title;
    navigation?.ready(projectId, title);
    const items = [
      `作品：${title}`,
      `正式章节正文：${writerContext?.formal_chapter_count ?? "暂不可用"} 章`,
      `当前工作稿：${writerContext?.working_draft_count ?? "暂不可用"} 章`,
      `工作稿章节：${writerContext?.working_draft_chapters?.join("、") || "暂无"}`,
      `待确认候选：${writerContext?.candidate_count ?? "暂不可用"} 份`,
    ];
    $("agent-context").replaceChildren(...items.map(value => { const node=document.createElement("div"); node.className="context-item"; node.textContent=value; return node; }));
    return true;
  }

  async function openChapter(source = "auto") {
    const selectedChapter = chapter();
    const selectedEpoch = selectionEpoch;
    editor.disabled = true;
    $("source-status").textContent = "正在读取…";
    const response = await fetch(`/api/writer/chapters/${selectedChapter}?source=${source}`);
    const data = await response.json();
    if (chapter() !== selectedChapter || selectionEpoch !== selectedEpoch) return;
    if (!response.ok || data.chapter && (data.chapter.project_id !== projectId || data.chapter.chapter_number != null && data.chapter.chapter_number !== selectedChapter)) throw new Error("章节读取失败或作品身份不匹配");
    if (!data.chapter) {
      editor.value = "";
      currentVersion = null;
      editorScope = { projectId, chapterNumber: selectedChapter, expectedVersion: null, savedContent: "", epoch: selectedEpoch };
      editor.disabled = false;
      $("source-status").textContent = "暂无章节正文，可以创建工作稿";
      updateWordCount();
      navigation?.opened({ page: "writer", chapter_number: selectedChapter, source: ["draft", "formal"].includes(source) ? source : "auto" });
      return;
    }
    projectId = data.chapter.project_id;
    $("chapter-title").textContent = data.chapter.title;
    const item = directory?.items.find(item => item.chapter_number === selectedChapter);
    if (item) $("chapter-title").textContent = item.title;
    editor.value = data.chapter.content;
    updateWordCount();
    currentVersion = data.chapter.version ? data.chapter.version.version : null;
    editorScope = { projectId, chapterNumber: selectedChapter, expectedVersion: currentVersion, savedContent: editor.value, epoch: selectedEpoch };
    editor.disabled = false;
    $("save-status").textContent = "";
    currentSource = data.chapter.source.editable ? "draft" : "formal";
    $("source-status").textContent = `${data.chapter.source.label} · ${data.chapter.source.editable ? "可编辑" : "首次编辑将创建工作稿"}`;
    navigation?.opened({ page: "writer", chapter_number: selectedChapter, source: currentSource });
  }

  function updateWordCount() { $("word-count").textContent = `${editor.value.replace(/\s/g, "").length} 字`; }
  function wordTarget() {
    const target = Math.max(1, Number($("agent-target-words").value) || 4500);
    const tolerance = Math.max(0, Number($("agent-tolerance-words").value) || 0);
    $("agent-word-range").textContent = `范围：${Math.max(1, target - tolerance)}–${target + tolerance} 字`;
    return { target_words: target, tolerance_words: tolerance };
  }

  const agentConversation = new WriterAgentConversation({
    onSource: () => { activateWorkspacePanel("chapter"); activateChapterTab("details"); },
    chapter, wordTarget,
    beforeExecute: () => flushSaves(),
    onDraft: async (job, isCurrent) => {
      if (!isCurrent() || editor.disabled || pendingSave || unconfirmedSave || inFlightSave) return;
      await openChapter("draft");
      if (!isCurrent()) return;
      await loadVersions();
      activateChapterTab("editor");
      await refreshProjectContext();
    },
    onProposal: async (proposal, isCurrent) => {
      if (!isCurrent()) return;
      $("agent-candidate").textContent = proposal.result?.content || "候选正在生成";
      $("agent-diff").textContent = `冻结原稿 → 本候选\n${proposal.diff || "没有检测到差异"}`;
      activateChapterTab("candidate");
      activateWorkspacePanel("chapter");
    }
  });

  async function submitAgentIntent(instruction, mode = "analyze") {
    const scope = editorScope;
    if (scope && !await flushSaves()) return;
    if (scope !== editorScope || editor.disabled) return;
    await agentConversation.submit(instruction, mode);
  }

  async function saveDraft() {
    if (!editor.disabled && editorScope && !pendingSave && editor.value !== editorScope.savedContent &&
        (!unconfirmedSave || unconfirmedSave.scope !== editorScope || unconfirmedSave.content !== editor.value)) captureSave();
    return flushSaves();
  }

  function captureSave() {
    if (!editorScope || editor.disabled) return;
    // 编辑时冻结全部目标字段；回调不再从章节输入框读取保存目标。
    pendingSave = { scope: editorScope, projectId: editorScope.projectId, chapterNumber: editorScope.chapterNumber,
      content: editor.value, expectedVersion: editorScope.expectedVersion, requestId: `writer-${crypto.randomUUID()}` };
  }

  async function flushSaves() {
    window.clearTimeout(saveTimer);
    while (inFlightSave || unconfirmedSave || pendingSave) {
      if (!inFlightSave) {
        // 未确认的原请求优先复查；后续编辑独立保留，不能替换原幂等编号。
        if (!unconfirmedSave) {
          unconfirmedSave = pendingSave;
          pendingSave = null;
        }
        const snapshot = unconfirmedSave;
        inFlightSave = persistSave(snapshot).finally(() => { inFlightSave = null; });
      }
      if (!await inFlightSave) return false;
    }
    return true;
  }

  async function persistSave(snapshot) {
    const visible = () => editorScope === snapshot.scope;
    if (visible()) $("save-status").textContent = "正在保存…";
    try {
      const response = await fetch("/api/commands/save-writer-draft", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        command_id: "save_writer_draft", request_id: snapshot.requestId, actor: "作者",
        target: { project_id: snapshot.projectId, chapter_number: snapshot.chapterNumber }, payload: { content: snapshot.content },
        expected_version: snapshot.expectedVersion, idempotency_key: snapshot.requestId
      }) });
      const data = await response.json();
      if (data.status !== "accepted") throw new Error(data.error?.message || "保存失败");
      const reference = (data.emitted_event_refs || []).find(ref => ref.startsWith(`writer-draft:${snapshot.chapterNumber}:`));
      const savedVersion = Number(reference?.split(":").at(-1));
      if (!Number.isInteger(savedVersion) || savedVersion <= 0) throw new Error("保存结果版本未知，请核对后重试");
      snapshot.scope.expectedVersion = savedVersion;
      snapshot.scope.savedContent = snapshot.content;
      unconfirmedSave = null;
      // 同一编辑会话的后续输入只承接本次已确认保存的版本。
      if (pendingSave?.scope === snapshot.scope && pendingSave.expectedVersion === snapshot.expectedVersion) pendingSave.expectedVersion = savedVersion;
      if (visible()) {
        currentVersion = savedVersion;
        $("save-status").textContent = pendingSave ? "有未保存修改" : `已保存第 ${savedVersion} 个版本`;
      }
      return true;
    } catch (error) {
      // 原快照仍在 unconfirmedSave；后续输入仍在 pendingSave，各自保留。
      if (visible()) $("save-status").textContent = error.message;
      return false;
    }
  }

  async function loadVersions() {
    const selectedChapter = chapter();
    const selectedEpoch = agentConversation.epoch;
    const response = await fetch(`/api/writer/chapters/${selectedChapter}/versions`);
    const data = await response.json();
    if (chapter() !== selectedChapter || agentConversation.epoch !== selectedEpoch) return null;
    versionHistory = data.versions;
    $("versions").innerHTML = data.versions.length ? data.versions.map(v => `<button data-version="${v.version}">版本 ${v.version} · ${v.actor}</button>`).join(" ") : "暂无工作稿版本";
    $("versions").querySelectorAll("button").forEach(button => button.addEventListener("click", () => restoreVersion(Number(button.dataset.version))));
    return data.versions.length ? Math.max(...data.versions.map(v => v.version)) : null;
  }

  async function restoreVersion(version) {
    const response = await fetch("/api/commands/restore-writer-version", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      command_id: "restore_writer_version", request_id: `restore-${Date.now()}`, actor: "作者", target: { project_id: projectId, chapter_number: chapter() }, payload: { version }, expected_version: currentVersion, idempotency_key: `restore-${chapter()}-${version}-${Date.now()}`
    }) });
    const data = await response.json();
    if (data.status === "accepted") { const before = currentVersion; await openChapter("draft"); const latest = await loadVersions(); currentVersion = latest ?? currentVersion; $("save-status").textContent = currentVersion === before ? "内容未变化，未创建新版本" : "已恢复并创建新版本"; await refreshProjectContext(); }
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

  $("open-chapter").addEventListener("click", () => selectChapter(chapter(), "auto").catch(error => { $("agent-state-text").textContent = error.message; }));
  $("view-formal").addEventListener("click", () => selectChapter(chapter(), "formal").catch(error => { $("agent-state-text").textContent = error.message; }));
  $("view-draft").addEventListener("click", () => selectChapter(chapter(), "draft").catch(error => { $("agent-state-text").textContent = error.message; }));
  $("save-draft").addEventListener("click", saveDraft);
  $("publish-draft").addEventListener("click", publishDraft);
  const browserConnect = $("publication-browser-connect");
  const browserReconnect = $("publication-browser-reconnect");
  const browserStatus = $("publication-browser-session-status");
  const browserState = $("publication-browser-session-state");
  function renderBrowserSession(data) {
    if (!data) return;
    const pending = data.status === "awaiting_reconcile";
    browserStatus.textContent = pending ? "待核对" : (data.connected ? "已连接" : "未连接");
    const platformChapter = Number(data.platform_chapter_number);
    const localChapter = Number(chapter());
    if (Number.isInteger(platformChapter) && platformChapter > 0) {
      const next = platformChapter + 1;
      $("publication-meta").textContent = `番茄已发布第 ${platformChapter} 章；本地当前第 ${localChapter || "?"} 章；下一章从第 ${next} 章开始`;
    }
    browserState.textContent = pending
      ? "正式浏览器已登记。请确认Edge中的番茄登录状态，再点击“重新核对并接入”；核对通过后才允许继续发布。"
      : (data.status || "尚未建立持久化会话");
    browserConnect.hidden = pending || Boolean(data.connected);
    browserReconnect.hidden = !pending && !data.connected;
  }
  async function persistBrowserHandoff(action) {
    const key = `creative-os-browser-session-${projectId || "current"}`;
    const sessionId = sessionStorage.getItem(key) || (crypto.randomUUID ? crypto.randomUUID() : `browser-${Date.now()}`);
    sessionStorage.setItem(key, sessionId);
    const pageId = `fanqie-writer-${encodeURIComponent(projectId || "unknown")}`;
    const response = await fetch("/api/publication/browser", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      action, platform: "tomato", session_id: sessionId, page_id: pageId,
      page_url: "https://fanqienovel.com/main/writer/", work_id: projectId,
      work_title: $("project-name").textContent || projectId, chapter_number: null,
      platform_work_title: null, platform_chapter_number: null, login_state: "unknown"
    }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.code || "browser_handoff_failed");
    renderBrowserSession(data);
  }
  async function refreshBrowserSession() {
    try {
      const response = await fetch("/api/publication/browser");
      if (response.ok) {
        const data = await response.json();
        if (data.session_id && projectId) sessionStorage.setItem(`creative-os-browser-session-${projectId}`, data.session_id);
        renderBrowserSession(data);
      }
    } catch (_) { /* 浏览器连接状态不可用时保持当前页面 */ }
  }
  function requestFormalBrowserTakeover() {
    const action = browserReconnect.hidden ? "connect" : "reconnect";
    browserStatus.textContent = "待接管";
    browserState.textContent = "已打开番茄正式浏览器入口。请确认Edge中的登录状态，确认后再由连接桥核对作品、章节和正文哈希。";
    browserConnect.hidden = true;
    browserReconnect.hidden = false;
    window.open("https://fanqienovel.com/main/writer/", "creative-os-formal-browser");
    persistBrowserHandoff(action).catch(error => { browserState.textContent = `浏览器会话登记失败：${error.message}`; });
  }
  browserConnect?.addEventListener("click", requestFormalBrowserTakeover);
  browserReconnect?.addEventListener("click", requestFormalBrowserTakeover);
  $("load-versions").addEventListener("click", loadVersions);
  $("agent-check").addEventListener("click", () => submitAgentIntent("这一章目前写得不对，你自己检查一下。"));
  $("agent-continue").addEventListener("click", () => submitAgentIntent(`读取项目已有数据和前文，继续写第 ${chapter()} 章。`, "act"));
  $("agent-send").addEventListener("click", () => submitAgentIntent($("agent-instruction").value));
  $("agent-target-words").addEventListener("input", wordTarget);
  $("agent-tolerance-words").addEventListener("input", wordTarget);
  $("accept-agent-draft").addEventListener("click", () => agentConversation.review("accept"));
  $("reject-agent-draft").addEventListener("click", () => agentConversation.review("reject"));
  $("cancel-agent-proposal").addEventListener("click", () => agentConversation.review("cancel"));
  $("revise-agent-draft").addEventListener("click", () => agentConversation.revise());
  document.querySelectorAll("[data-chapter-tab]").forEach(button => button.addEventListener("click", () => activateChapterTab(button.dataset.chapterTab)));
  document.querySelectorAll("[data-workspace-panel]").forEach(button => button.addEventListener("click", () => activateWorkspacePanel(button.dataset.workspacePanel)));
  wordTarget();
  editor.addEventListener("input", () => { updateWordCount(); captureSave(); window.clearTimeout(saveTimer); $("save-status").textContent = "有未保存修改"; saveTimer = window.setTimeout(flushSaves, 1200); });
  (async () => {
    if (!await refreshProjectContext()) return;
    await refreshBrowserSession();
    if (initialChapter) await selectChapter(Number(initialChapter), initialSource);
    else await selectChapter(1, initialSource);
  })().catch(error => { $("agent-state-text").textContent = error.message; });
  window.setInterval(() => {
    refreshProjectContext().catch(error => { $("agent-state-text").textContent = error.message; });
    refreshBrowserSession();
  }, 5000);
})();
