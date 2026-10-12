# Writer Workspace 三栏创作工作台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有写作页改造成左侧章节导航、中间 Agent 会话、右侧章节工作区的可用三栏创作工作台。

**Architecture:** 继续复用现有 WriterWebAdapter、Command Boundary、Agent Runtime 和草稿版本存储，只扩充只读上下文 DTO 并重组前端。页面采用原生 HTML/CSS/JavaScript，三个面板各自滚动；窄屏切换面板，不复制业务逻辑。

**Tech Stack:** Python 3、原生 HTML/CSS/JavaScript、pytest

**Spec:** `docs/superpowers/specs/2026-10-12-writer-workspace-three-pane-design.md`

## Global Constraints

- UI 不直接修改 Projection、Domain 或文件系统，只调用现有查询与命令边界。
- Agent 输出先进入工作稿，正式稿只允许作者主动发布。
- 普通界面使用中文创作语言，原始 Trace 与路径留在 Inspector。
- 不引入 React、Vue、新构建链、跨项目管理或第二套 Writer/Command/Runtime。
- 保留当前未提交的 Agent 工作稿审阅功能，不覆盖用户已有修改。
- Commit 与 Push 必须另行取得用户确认；Commit Message 使用中文，Push 使用 Git Bash。

## Review Focus

- 正式稿编号不连续时，左栏只显示真实存在章节，点击仍打开正确章节。
- 同一章节同时有正式稿和工作稿时，两种来源分组清晰且可分别打开。
- 长正文、长 Agent 回答、长差异和大量版本只在所属面板滚动，不撑高整页。
- 请求失败、章节不存在或 Projection 部分不可用时，保留用户输入并在原面板显示中文错误。
- 920px 以下只显示当前选中面板，切换后正文和未提交输入不丢失且无横向溢出。

---

### Task 1: 扩充 Writer 章节导航查询

**Files:**
- Modify: `creative_os/web_workspace.py:92-99`
- Modify: `tests/test_writer_context_summary.py`

**Interfaces:**
- Consumes: `WriterDraftStore.root`、`production/final_chapters/chapter_NNN.md`
- Produces: `WriterWebAdapter.read_context_summary() -> bytes`，新增 `formal_chapters: list[int]`，保留现有计数字段和 `working_draft_chapters`

- [ ] **Step 1: 写失败测试**

在 `test_writer_context_separates_formal_chapters_drafts_and_projection` 中创建不连续正式章节 1、3，并断言 `formal_chapters == [1, 3]`、`working_draft_chapters == [2]`，同时保留原计数断言。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_writer_context_summary.py -q`
Expected: FAIL，返回数据缺少 `formal_chapters`。

- [ ] **Step 3: 最小实现章节编号解析**

在 `read_context_summary()` 中只解析匹配 `chapter_*.md` 的数字编号，排序后写入 `formal_chapters`；计数由列表长度产生。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_writer_context_summary.py -q`
Expected: PASS。

### Task 2: 建立三栏语义结构与独立样式

**Files:**
- Modify: `creative_os/web/writer.html`
- Create: `creative_os/web/writer.css`
- Modify: `creative_os/web_workspace.py:157-164`
- Modify: `tests/test_writer_shell_assets.py`

**Interfaces:**
- Consumes: 现有所有 Writer/Agent 控件 ID，Task 1 的章节数组
- Produces: `#project-sidebar`、`#agent-workspace`、`#chapter-workspace`、`[data-workspace-panel]`、`[data-chapter-tab]`；静态路由 `/writer.css`

- [ ] **Step 1: 写失败的结构与资源测试**

新增测试断言三个主面板、正式稿/工作稿列表、正文/预览/差异/版本/详情标签、移动端面板切换按钮以及 `/writer.css` 引用存在；路由测试断言 `writer.css` 可被静态映射。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_writer_shell_assets.py -q`
Expected: FAIL，缺少三栏结构或样式资源。

- [ ] **Step 3: 重排 HTML，保留既有控件 ID**

左栏放项目名、正式稿列表和工作稿列表；中栏迁移 Agent 状态、快捷操作、会话、补充要求与字数设置；右栏放章节标题、来源/保存/字数状态、五个标签面板及既有编辑器、预览、差异、版本和发布操作。

- [ ] **Step 4: 创建独立 CSS 并注册静态资源**

定义 `260px minmax(320px, .85fr) minmax(480px, 1.35fr)` 三栏网格、面板高度 `calc(100vh - 32px)`、面板内部滚动、中文浅色视觉和 920px 窄屏单面板规则；在 `WorkspaceRequestHandler` 增加 `/writer.css`。

- [ ] **Step 5: 运行结构测试确认通过**

Run: `python -m pytest tests/test_writer_shell_assets.py -q`
Expected: PASS。

### Task 3: 接通章节导航、右栏标签和状态保持

**Files:**
- Modify: `creative_os/web/writer.js`
- Modify: `tests/test_writer_shell_assets.py`

**Interfaces:**
- Consumes: `GET /api/writer/context` 的 `formal_chapters`、`working_draft_chapters`，以及 Task 2 的 DOM 接口
- Produces: `renderChapterNavigation(context)`、`selectChapter(chapterNumber, source)`、`activateChapterTab(tabName)`、`activateWorkspacePanel(panelName)`

- [ ] **Step 1: 写失败的前端行为契约测试**

断言脚本包含四个接口函数；章节按钮携带 `data-chapter-number` 和 `data-source`；标签切换使用 `hidden` 与 `aria-selected`；移动端切换使用 `data-workspace-panel`。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_writer_shell_assets.py -q`
Expected: FAIL，导航与切换接口不存在。

- [ ] **Step 3: 渲染真实章节导航**

`renderChapterNavigation(context)` 分别渲染正式稿和工作稿按钮，不用计数推测连续编号；点击调用 `selectChapter(number, source)`。

- [ ] **Step 4: 统一章节选择入口**

`selectChapter()` 更新章节号、选中状态并调用既有 `openChapter(source)`、`loadVersions()`；正式稿与工作稿保持来源标签，章节不存在时在右栏显示错误且不清空 Agent 输入。

- [ ] **Step 5: 实现右栏和窄屏标签切换**

`activateChapterTab()` 只切换右栏内容；`activateWorkspacePanel()` 只在窄屏改变可见主面板。Agent 完成修改后自动打开“差异”，普通打开章节默认进入“正文”。

- [ ] **Step 6: 运行前端契约测试确认通过**

Run: `python -m pytest tests/test_writer_shell_assets.py -q`
Expected: PASS。

### Task 4: 保持 Agent、版本、差异与发布完整闭环

**Files:**
- Modify: `creative_os/web/writer.js`
- Modify: `tests/test_writer_shell_assets.py`
- Modify: `tests/test_writer_context_summary.py`

**Interfaces:**
- Consumes: 既有 `submitAgentIntent()`、`saveDraft()`、`restoreVersion()`、`publishDraft()`、Task 3 标签接口
- Produces: 在新布局中可完成分析/生成、差异查看、保留、退回、补充要求再修改、保存与发布

- [ ] **Step 1: 补充闭环契约测试**

断言 Agent 完成后调用 `activateChapterTab("diff")`；保留不调用保存命令；退回复用 `restoreVersion(previousVersion)`；发布仍使用 `publish_writer_draft`；错误状态写入对应状态区域。

- [ ] **Step 2: 运行测试确认现有迁移缺口**

Run: `python -m pytest tests/test_writer_shell_assets.py tests/test_writer_context_summary.py -q`
Expected: 至少一个新增断言 FAIL。

- [ ] **Step 3: 迁移并收紧状态更新**

修正所有旧 DOM 引用；Agent 长内容留在中栏滚动区，差异与版本只进入右栏；保存、版本恢复和发布后刷新导航摘要，但不重置正文、输入或当前标签。

- [ ] **Step 4: 运行目标测试确认通过**

Run: `python -m pytest tests/test_writer_shell_assets.py tests/test_writer_context_summary.py tests/test_writer_workspace_api.py tests/test_writer_commands.py -q`
Expected: PASS；若文件名不存在，使用 `rg --files tests | rg "writer"` 选择实际 Writer API/Command 测试。

### Task 5: 响应式与完整回归验收

**Files:**
- Modify if needed: `creative_os/web/writer.css`
- Modify if needed: `creative_os/web/writer.js`
- Modify if needed: `tests/test_writer_shell_assets.py`

**Interfaces:**
- Consumes: Tasks 1-4 完整工作台
- Produces: 通过桌面、窄屏和回归验收的 Writer Workspace

- [ ] **Step 1: 运行静态与 Writer 回归**

Run: `python -m pytest tests/test_writer_shell_assets.py tests/test_writer_context_summary.py -q`
Expected: PASS。

- [ ] **Step 2: 启动真实《文明升阶》工作台做桌面验收**

验证 79/80/81 章的正式稿/工作稿导航、三栏同时可见、各栏独立滚动、正文编辑、Agent 输入和右栏五标签；不得产生正式稿写入。

- [ ] **Step 3: 做 920px 与手机宽度验收**

验证目录/Agent/正文三面板切换、无页面横向滚动、长正文与长差异不撑开页面、切换后输入不丢失。

- [ ] **Step 4: 运行全量测试**

Run: `python -m pytest -q`
Expected: 全部通过，仅允许仓库已有 skip。

- [ ] **Step 5: 检查提交边界**

Run: `git status --short` 与 `git diff --check`
Expected: 只纳入本计划代码、测试、规格和计划；排除运行数据、工作稿、备份、日志、截图和 `.superpowers/sdd`。

- [ ] **Step 6: 等待用户确认后提交**

仅在用户明确确认后暂存目标文件并使用中文 Commit Message；Push 仍需再次确认并通过 Git Bash 执行。
