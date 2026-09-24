# Workspace V0.1 浅色 Creative Workspace 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留 Query Adapter、Projection 和 Command Boundary 的前提下，将单小说 Workspace 重构为可供创作者使用的浅色、分区滚动、List + Detail 工作台。

**Architecture:** 后端继续提供稳定的 Workspace ViewModel 和状态契约，前端原生 HTML/CSS/JS 只消费 Query Adapter 输出。通过共享设计 token、布局组件和页面 renderer 重组现有 Shell；原始 trace 与完整 Projection 仅保留在独立 Inspector。Novel 页面通过 Domain Registry 的最小描述接入，Core 页面不读取小说内部领域对象。

**Tech Stack:** Python 现有 Workspace Query/DTO/HTTP 路由；原生 HTML、CSS、JavaScript；pytest；Playwright/CUA 真实浏览器验收。

**Spec:** `docs/superpowers/specs/2026-09-24-workspace-v01-light-design.md`

## Global Constraints

- 只支持单个小说项目，不开发跨项目 Portfolio。
- Domain、Knowledge、Runtime 是唯一事实来源；Projection 只读，不创造领域事实。
- Web 层只能依赖统一 Query Adapter，不直接读取 Domain、Knowledge、Runtime 或 Projection 文件。
- 任何修改必须经过 `Web → Command Boundary → Application/Domain → Event → Projection Refresh → Query Adapter`。
- 普通创作者界面隐藏原始 trace、哈希、完整错误堆栈和大段 Projection JSON；完整诊断只在 Inspector 中提供。
- 不引入 React/Vue 或新的大型领域模型；保持现有原生 HTML/CSS/JS 运行方式。
- 状态必须显式表达 `fresh | stale | unavailable | partial`，且不能只用颜色传达。

## Review Focus

- 真实项目数据缺失或只有部分章节时，Overview/Chapters 必须显示 `partial`，不能伪装完整：由 Task 2 的状态测试覆盖。
- 刷新失败时，Workspace 必须保留旧快照并显示可重试的 `stale`/`unavailable`：由 Task 2 和 Task 6 覆盖。
- 空任务、空质量问题、无最近活动时，页面必须有明确空状态而非空白或异常：由 Task 3 的 ViewModel/renderer 测试覆盖。
- 长 trace、长章节列表和窄屏布局不得造成整页无限增长或不可滚动：由 Task 4 的 DOM/CSS 断言和 Task 6 的浏览器验收覆盖。
- Core 与 Novel 数据不能互相泄漏，未来未注册 Domain 不得自动生成伪导航：由 Task 1 的 Registry 契约测试覆盖。

### Task 1: 固化 Domain Registry 与 Core/Novel ViewModel 边界

**Files:**
- Modify: `creative_os/workspace_view_models.py`
- Modify: `creative_os/workspace_query.py`
- Modify: `creative_os/workspace_dto.py`
- Test: `tests/test_workspace_view_models.py`
- Test: `tests/test_workspace_boundary.py`

**Interfaces:**
- Produces `DomainDescriptor`（包含 `id`, `label`, `navigation`, `capabilities`, `snapshot_keys`）。
- Produces只读 `WorkspaceViewModel` 的 Core 摘要与 Novel 摘要分区。
- 保留现有 Query Adapter 公共入口和兼容字段，新增字段不得要求调用方读取内部 Projection。

- [ ] **Step 1: 写失败测试**：验证仅注册 `novel` 时生成小说导航；未注册 Domain 不产生导航；Core 摘要不包含章节内部对象；Novel 摘要保留 `source_refs` 与 freshness。
- [ ] **Step 2: 运行边界测试确认失败**：运行 `pwsh -NoProfile -Command "pytest tests/test_workspace_view_models.py tests/test_workspace_boundary.py -q"`，预期新增断言失败。
- [ ] **Step 3: 实现最小 Registry/DTO 分区**：在现有 ViewModel 结构上增加 descriptor 和明确的 `core`/`novel` 投影字段，避免复制原始 Projection。
- [ ] **Step 4: 运行测试确认通过**：同一命令应通过，且原有 Workspace 测试保持通过。
- [ ] **Step 5: 提交**：`git commit -m "固化 Workspace Domain Registry 与视图边界"`。

### Task 2: 完善状态、质量和运行摘要 ViewModel

**Files:**
- Modify: `creative_os/workspace_view_models.py`
- Modify: `creative_os/workspace_query.py`
- Modify: `creative_os/workspace_dto.py`
- Test: `tests/test_workspace_states.py`
- Test: `tests/test_workspace_integration.py`

**Interfaces:**
- Overview 输出 `progress`, `current_task`, `next_action`, `attention_queue`, `recent_activity`, `summary_cards`。
- Runtime 输出 `current_task`, `recent_runs`, `attempts`, `usage`, `recovery`, `error_summary`, `trace_summary`。
- 每个区域输出 `status`, `generated_at`, `source_refs`；列表摘要数量受限，完整内容仍由 Inspector 提供。

- [ ] **Step 1: 写失败测试**：覆盖 fresh/stale/partial/unavailable 四种状态；覆盖空队列、刷新失败保留旧快照、usage/retry 缺失时的明确空值。
- [ ] **Step 2: 运行测试确认失败**：运行 `pwsh -NoProfile -Command "pytest tests/test_workspace_states.py tests/test_workspace_integration.py -q"`。
- [ ] **Step 3: 实现 Adapter 组合逻辑**：只组合已有 Overview、Chapter、Quality、Trace、Runtime Projection，并生成面向 Web 的摘要字段；不产生新领域事实。
- [ ] **Step 4: 运行回归**：运行 `pwsh -NoProfile -Command "pytest tests/test_workspace_states.py tests/test_workspace_integration.py tests/projection -q"`。
- [ ] **Step 5: 提交**：`git commit -m "完善 Workspace 状态质量与运行摘要"`。

### Task 3: 重组浅色 Workspace Shell 与设计 Token

**Files:**
- Modify: `creative_os/web/index.html`
- Modify: `creative_os/web/styles.css`
- Modify: `creative_os/web/app.js`
- Test: `tests/test_workspace_shell_assets.py`

**Interfaces:**
- DOM 必须包含 `workspace-sidebar`, `workspace-topbar`, `workspace-main`, `overview-view`, `chapters-view`, `quality-view`, `runtime-view`。
- CSS 提供浅色 token、Sidebar、Topbar、独立滚动容器、状态徽章、卡片、空状态和响应式断点。
- JS 只消费 Adapter DTO，不直接拼接 Domain/Projection 业务逻辑。

- [ ] **Step 1: 写失败资产测试**：断言浅色 token、导航分组、主区域滚动容器、Inspector 入口和语义状态文案存在；断言旧的原始 trace 默认容器不在普通页面。
- [ ] **Step 2: 运行测试确认失败**：运行 `pwsh -NoProfile -Command "pytest tests/test_workspace_shell_assets.py -q"`。
- [ ] **Step 3: 实现 Shell**：用暖白画布、浅灰 Sidebar、白色内容卡片和单一 teal 强调色重写 HTML/CSS；保留现有路由和刷新入口。
- [ ] **Step 4: 运行静态资产测试**：同一命令应通过，并检查没有整页 `overflow` 依赖。
- [ ] **Step 5: 提交**：`git commit -m "重构 Workspace 浅色 Shell 与设计令牌"`。

### Task 4: 实现 Overview、Quality、Runtime 的创作者摘要页面

**Files:**
- Modify: `creative_os/web/app.js`
- Modify: `creative_os/web/index.html`
- Modify: `creative_os/web/styles.css`
- Test: `tests/test_workspace_interactions.py`
- Test: `tests/test_web_workspace_routes.py`

**Interfaces:**
- `renderOverview(viewModel)`, `renderQuality(viewModel)`, `renderRuntime(viewModel)` 只接收统一 DTO。
- 主界面显示进度、当前任务、下一步建议、Blocking/Warning、最近活动和运行摘要。
- Runtime 的“打开 Inspector”链接指向既有 Inspector 页面或独立面板，不在普通页面展开原始 trace。

- [ ] **Step 1: 写失败交互测试**：验证导航切换、刷新、状态徽章、下一步建议、空状态和 Inspector 入口的 DOM 行为。
- [ ] **Step 2: 运行测试确认失败**：运行 `pwsh -NoProfile -Command "pytest tests/test_workspace_interactions.py tests/test_web_workspace_routes.py -q"`。
- [ ] **Step 3: 实现三个 renderer**：将长数据收敛为摘要卡与有限列表，提供“查看全部”入口；错误和状态使用文字、图标和颜色共同表达。
- [ ] **Step 4: 运行交互回归**：同一命令应通过，并追加 `pytest tests/test_workspace_boundary.py -q`。
- [ ] **Step 5: 提交**：`git commit -m "实现 Workspace 总览质量与运行摘要"`。

### Task 5: 实现 Chapters 的 List + Detail 与 Novel 插槽

**Files:**
- Modify: `creative_os/web/app.js`
- Modify: `creative_os/web/index.html`
- Modify: `creative_os/web/styles.css`
- Test: `tests/test_workspace_interactions.py`
- Test: `tests/test_workspace_view_models.py`

**Interfaces:**
- `renderChapterList(chapters)` 与 `renderChapterDetail(chapter)` 使用 Novel ViewModel，不读取原始章节文件。
- 列表显示编号、标题、阶段、质量状态和问题数；详情显示来源、阶段、质量、任务和折叠证据。
- Domain Registry 只提供 Novel 导航；故事、角色页面使用相同插槽，不扩展为万能动态 UI。

- [ ] **Step 1: 写失败测试**：验证章节列表独立滚动、选中项详情更新、无章节/部分章节状态、窄屏详情抽屉和来源引用展示。
- [ ] **Step 2: 运行测试确认失败**：运行 `pwsh -NoProfile -Command "pytest tests/test_workspace_interactions.py tests/test_workspace_view_models.py -q"`。
- [ ] **Step 3: 实现 List + Detail**：桌面双栏，窄屏单栏抽屉；证据默认折叠；分页/限制显示避免一次渲染全部长内容。
- [ ] **Step 4: 运行交互测试**：同一命令应通过。
- [ ] **Step 5: 提交**：`git commit -m "实现章节列表与详情工作区"`。

### Task 6: 真实浏览器验收与视觉修正

**Files:**
- Modify: `creative_os/web/styles.css`（仅针对验收发现的问题）
- Modify: `creative_os/web/app.js`（仅针对验收发现的问题）
- Test: `tests/test_web_workspace.py`
- Evidence: 浏览器桌面与窄屏截图、验收记录

**Interfaces:**
- 使用真实《文明升阶》项目启动现有 Workspace 服务；不替换为 mock。
- 验收桌面宽度和窄屏宽度，检查滚动边界、导航、状态语义、Inspector 独立性和 30 秒理解标准。

- [ ] **Step 1: 运行完整自动化回归**：`pwsh -NoProfile -Command "pytest tests/test_workspace* tests/test_web_workspace.py tests/projection -q"`。
- [ ] **Step 2: 启动服务并进行桌面验收**：启动 `scripts/novel_web_workspace.py` 指向《文明升阶》，检查 Overview、Chapters、Quality、Runtime 四页和刷新/Inspector。
- [ ] **Step 3: 进行窄屏验收**：用浏览器窄视口检查 Sidebar 收缩、章节详情抽屉和内容滚动；记录截图与问题。
- [ ] **Step 4: 只修复阻塞问题**：针对真实证据做最小 CSS/JS 修改，每次修改后重跑相关测试。
- [ ] **Step 5: 提交验收修正**：`git commit -m "完成 Workspace V0.1 浏览器验收修正"`。

### Task 7: 分支审查、PR、合并与基线冻结

**Files:**
- Review: Workspace 全部变更与测试
- Add/Modify: `docs/superpowers/plans/2026-09-24-workspace-v01-light.md`（仅记录执行结果，不改设计目标）

- [ ] **Step 1: 运行全量回归**：`pwsh -NoProfile -Command "pytest -q"`，记录失败并修复后再继续。
- [ ] **Step 2: 检查边界**：确认没有修改用户未提交文件，没有直接读取 Domain 的 Web 代码，没有把原始 trace 放回普通界面。
- [ ] **Step 3: 创建中文提交和 PR**：先在本地完成审查；远程推送和 PR 需要用户确认后执行。
- [ ] **Step 4: 合并后同步 main**：确认 PR 合并、main 与远程一致，保留可回滚基线标签或提交记录。
- [ ] **Step 5: 冻结 V0.1**：输出实现现状、测试结果、浏览器证据和下一阶段 Feedback → Lesson → Knowledge → Future Context 计划。
