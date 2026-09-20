# Creative OS Web Workspace Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不绕过 Query Adapter/Command Boundary 的前提下，建立可扩展的 Creative OS Workspace Shell，并将 Overview 与 Chapters 迁移到分层、可滚动、可追溯的正式工作台。

**Architecture:** 保留当前高密度页面作为 Projection Inspector，新增正式 Workspace 入口。后端继续以 Projection 为事实投影，新增页面级 ViewModel Adapter 将数据整理为 Domain-neutral 的摘要、列表和详情模型；Novel 只作为第一个 Domain Plugin。正式 Workspace 不直接读取文件、Projection 内部对象或领域模块。

**Tech Stack:** 现有 Python `WorkspaceQueryAdapter`/HTTP Adapter；原生 HTML、CSS、JavaScript；pytest；Node `--check`；浏览器真实页面验收。

## Global Constraints

- Domain / Knowledge / Runtime 继续作为唯一真实数据源。
- Projection 只读；ViewModel 只做派生、排序、分组和展示优先级，不创造领域事实。
- UI 不直接读取 Domain、Knowledge、Runtime、Projection 实现或项目文件。
- 所有写操作继续走 `Web → Command Boundary → Domain → Event/Checkpoint → Projection Refresh`。
- 不引入跨项目 Portfolio，不新增大规模领域模型，不复制命令业务逻辑。
- 正式 Workspace 默认隐藏完整 Source Ref、哈希和 Trace；Inspector 保留完整审计信息。
- 页面使用 `100vh`；导航、顶栏、主工作区、列表和详情区按职责独立滚动。
- 所有界面状态必须覆盖 loading、empty、unavailable、stale、partial、success、warning、blocked 和 error。
- 中文产品文案、英文代码标识；保留可访问名称、键盘焦点、对比度和 reduced-motion 支持。

---

### Task 1: 建立 Domain-neutral Workspace ViewModel 契约

**Files:**
- Create: `creative_os/workspace_view_models.py`
- Modify: `creative_os/workspace_query.py`
- Test: `tests/test_workspace_view_models.py`

**Interfaces:**
- Consumes: `WorkspaceQueryAdapter.get_workspace(project_id)` and existing `ProjectionEnvelope`.
- Produces: `WorkspaceOverviewVM`, `WorkspaceListItemVM`, `WorkspaceDetailVM`, `WorkspaceModuleVM`, `WorkspaceViewModelAdapter.to_overview(envelope)`, `to_chapter_list(envelope, query)`, `to_chapter_detail(envelope, chapter_number)`.

- [ ] **Step 1: Write failing tests for domain-neutral summaries and chapter list filtering**

```python
def test_overview_vm_exposes_priority_metrics_without_raw_projection_fields(envelope):
    view = WorkspaceViewModelAdapter().to_overview(envelope)
    assert view.project_id == "book-a"
    assert view.chapter_summary.total >= 0
    assert not hasattr(view, "source_heads")


def test_chapter_list_vm_filters_and_preserves_detail_key(envelope):
    view = WorkspaceViewModelAdapter().to_chapter_list(envelope, query="review")
    assert all("review" in item.status_label.lower() for item in view.items)
    assert all(item.detail_key.startswith("chapter:") for item in view.items)
```

- [ ] **Step 2: Run the focused tests and verify they fail because the adapter and VM types do not exist**

Run: `python -m pytest tests/test_workspace_view_models.py -q`

Expected: collection failure for the missing module/types.

- [ ] **Step 3: Implement immutable ViewModel dataclasses and adapter methods**

The adapter must map only from the supplied `ProjectionEnvelope`, return explicit freshness and diagnostics, sort chapters by `chapter_number`, and use `detail_key` as the stable UI identity. It must never import `FilesystemProjectSource`, a Domain command handler, or a checkpoint store.

- [ ] **Step 4: Run focused tests and the existing Workspace query tests**

Run: `python -m pytest tests/test_workspace_view_models.py tests/test_workspace_integration.py tests/test_web_workspace.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the isolated ViewModel contract**

```bash
git add creative_os/workspace_view_models.py creative_os/workspace_query.py tests/test_workspace_view_models.py
git commit -m "建立 Workspace 页面级 ViewModel 契约"
```

### Task 2: 分离 Projection Inspector 与正式 Workspace 路由

**Files:**
- Modify: `creative_os/web_workspace.py`
- Modify: `scripts/novel_web_workspace.py`
- Create: `creative_os/web/inspector.html`
- Create: `creative_os/web/inspector.js`
- Test: `tests/test_web_workspace_routes.py`

**Interfaces:**
- Consumes: existing `WorkspaceWebAdapter`, `WorkspaceViewModelAdapter`, and command adapters.
- Produces: `/` for the formal Workspace and `/inspector` for the full Projection Inspector. Both use the same read and command boundaries; only presentation and ViewModel selection differ.

- [ ] **Step 1: Add failing route tests**

```python
def test_root_serves_workspace_and_inspector_serves_debug_surface(http_server):
    assert get(http_server, "/").status == 200
    assert "Workspace" in get(http_server, "/").text
    assert get(http_server, "/inspector").status == 200
    assert "Projection" in get(http_server, "/inspector").text
```

- [ ] **Step 2: Run the route tests and verify the inspector route is missing**

Run: `python -m pytest tests/test_web_workspace_routes.py -q`

Expected: failure for `/inspector`.

- [ ] **Step 3: Add explicit static asset routing and keep command routes unchanged**

`WorkspaceRequestHandler` must map `/` to the formal Workspace assets and `/inspector` to dedicated Inspector assets. The Inspector may call the existing full `/api/workspace` envelope; no new write endpoint is introduced.

- [ ] **Step 4: Run route, command, and existing Web tests**

Run: `python -m pytest tests/test_web_workspace_routes.py tests/test_web_workspace.py tests/test_workspace_command_adapter.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the route separation**

```bash
git add creative_os/web_workspace.py scripts/novel_web_workspace.py creative_os/web/inspector.html creative_os/web/inspector.js tests/test_web_workspace_routes.py
git commit -m "分离 Workspace 与 Projection Inspector"
```

### Task 3: 实现 Workspace Shell 与语义设计令牌

**Files:**
- Modify: `creative_os/web/index.html`
- Modify: `creative_os/web/styles.css`
- Modify: `creative_os/web/app.js`
- Test: `tests/test_workspace_shell_assets.py`

**Interfaces:**
- Consumes: ViewModel JSON returned by the Workspace Web Adapter and the existing command result contract.
- Produces: fixed-height Shell with Sidebar, Topbar, module navigation, status banner, main scroll region, accessible focus states, and responsive narrow layout.

- [ ] **Step 1: Add failing asset contract tests**

```python
def test_workspace_shell_has_fixed_regions_and_domain_neutral_navigation():
    html = Path("creative_os/web/index.html").read_text(encoding="utf-8")
    css = Path("creative_os/web/styles.css").read_text(encoding="utf-8")
    assert 'id="workspace-sidebar"' in html
    assert 'id="workspace-main"' in html
    assert "--surface" in css
    assert "100vh" in css
```

- [ ] **Step 2: Run the asset test and verify the current long-page layout fails the contract**

Run: `python -m pytest tests/test_workspace_shell_assets.py -q`

Expected: failure until the new regions and tokens are present.

- [ ] **Step 3: Implement the Shell without adding domain-specific business logic**

Use semantic tokens for surface, text, muted text, border, accent, success, warning, danger, spacing, radius and focus ring. Keep navigation labels supplied by a small `WorkspaceNavigation` configuration so future Domain Plugins can add modules without rewriting the Shell. Put the primary action and freshness indicator in the Topbar.

- [ ] **Step 4: Run asset tests, Node syntax check, and existing frontend tests**

Run: `python -m pytest tests/test_workspace_shell_assets.py tests/test_web_workspace.py -q; node --check creative_os/web/app.js`

Expected: all pass.

- [ ] **Step 5: Commit the Shell**

```bash
git add creative_os/web/index.html creative_os/web/styles.css creative_os/web/app.js tests/test_workspace_shell_assets.py
git commit -m "建立 Workspace 固定布局与设计令牌"
```

### Task 4: 迁移 Overview 与 Chapters 到列表/详情信息层

**Files:**
- Modify: `creative_os/web/index.html`
- Modify: `creative_os/web/app.js`
- Modify: `creative_os/web/styles.css`
- Test: `tests/test_workspace_interactions.py`

**Interfaces:**
- Consumes: `WorkspaceOverviewVM`, `WorkspaceListItemVM`, `WorkspaceDetailVM` and existing `start_chapter_run` command result.
- Produces: compact Overview summary, filterable Chapter list, selected chapter detail drawer, and safe existing chapter command action.

- [ ] **Step 1: Add failing interaction tests**

```python
def test_chapter_workspace_has_list_detail_and_command_hooks():
    html = Path("creative_os/web/index.html").read_text(encoding="utf-8")
    script = Path("creative_os/web/app.js").read_text(encoding="utf-8")
    assert 'id="chapter-list"' in html
    assert 'id="chapter-detail-drawer"' in html
    assert "data-chapter-key" in script
    assert "/api/commands/start-chapter-run" in script
```

- [ ] **Step 2: Run the interaction tests and verify the long-page implementation fails**

Run: `python -m pytest tests/test_workspace_interactions.py -q`

Expected: failure until list/detail regions and the command hook exist.

- [ ] **Step 3: Implement the compact Overview and Chapters interaction**

Overview displays only current stage, chapter progress, blocking count, current task, recent activity and top attention items. Chapters uses a fixed-height scrollable list with search and status filters; clicking a row opens the detail drawer. Source references and derivations are collapsed under an “证据” section. The start command remains the only existing mutation and continues to POST through the current Command Boundary.

- [ ] **Step 4: Run frontend, command, and query regression tests**

Run: `python -m pytest tests/test_workspace_interactions.py tests/test_web_workspace.py tests/test_workspace_chapter_command.py tests/test_workspace_view_models.py -q; node --check creative_os/web/app.js`

Expected: all pass.

- [ ] **Step 5: Commit the Overview/Chapters migration**

```bash
git add creative_os/web/index.html creative_os/web/app.js creative_os/web/styles.css tests/test_workspace_interactions.py
git commit -m "重构 Overview 与 Chapters 工作区"
```

### Task 5: 浏览器视觉验收与状态补齐

**Files:**
- Modify: `creative_os/web/styles.css`
- Modify: `creative_os/web/app.js`
- Test: `tests/test_workspace_states.py`

**Interfaces:**
- Consumes: formal Workspace ViewModels and freshness/diagnostic fields.
- Produces: verified desktop and narrow layouts with loading, empty, unavailable, stale, partial, success, warning, blocked and error states.

- [ ] **Step 1: Add state contract tests**

```python
def test_workspace_state_labels_are_semantic_and_not_color_only():
    html = render_workspace_state("stale")
    assert "数据已过期" in html
    assert "status-label" in html
```

- [ ] **Step 2: Run state tests and fix missing state copy**

Run: `python -m pytest tests/test_workspace_states.py -q`

Expected: failures identify each missing state.

- [ ] **Step 3: Implement state rendering, focus styles, reduced motion and narrow layout rules**

The UI must explain what is unavailable and what action is valid. It must not fabricate counts or silently downgrade stale/partial data to fresh. Use `prefers-reduced-motion: reduce` to disable nonessential transitions.

- [ ] **Step 4: Run the live server and inspect two viewports**

Run: `python scripts/novel_web_workspace.py --project-root projects/文明升阶 --host 127.0.0.1 --port 8765`

Inspect `http://127.0.0.1:8765/` at one desktop viewport and one narrow viewport. Verify fixed navigation, independent main/list scrolling, chapter detail opening, freshness labels, empty/error states and no console errors.

- [ ] **Step 5: Run the full relevant regression suite**

Run: `python -m pytest tests/projection tests/test_workspace_integration.py tests/test_web_workspace.py tests/test_web_workspace_routes.py tests/test_workspace_view_models.py tests/test_workspace_interactions.py tests/test_workspace_states.py -q; node --check creative_os/web/app.js; git diff --check`

Expected: all pass.

- [ ] **Step 6: Commit the visual acceptance fixes**

```bash
git add creative_os/web/index.html creative_os/web/app.js creative_os/web/styles.css tests/test_workspace_states.py
git commit -m "完成 Workspace 视觉状态验收"
```

## Self-review checklist

- Spec coverage: Shell, Domain-neutral ViewModel, Inspector separation, Overview/Chapters migration, scrolling, responsive behavior, state handling, accessibility and visual verification are covered by Tasks 1–5.
- Placeholder scan: no TODO/TBD or unspecified implementation step is used.
- Type consistency: Tasks 1–4 share `WorkspaceViewModelAdapter`, `WorkspaceOverviewVM`, `WorkspaceListItemVM` and `WorkspaceDetailVM`; Task 5 consumes the same ViewModels and freshness fields.
- Scope: this plan deliberately excludes Story, Characters, new domain commands and Portfolio; those become separate plans after this shell is accepted.
