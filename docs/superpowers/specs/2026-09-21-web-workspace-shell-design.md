# Creative OS Web Workspace Shell 设计

日期：2026-09-21  
状态：已获用户批准，待文档审阅

## 1. 背景与目标

当前页面能够展示 Projection、质量、运行和 Trace 数据，但页面定位混合了产品工作台与开发调试器：数据按 Projection 结构直接铺开，缺少信息优先级、独立滚动和对象详情层级。本阶段建立正式的 Creative OS Web Workspace Shell，并保留现有页面作为 Projection Inspector。

目标是让单小说 Workspace 具备可扩展的页面结构与 Domain-neutral ViewModel 接口。Novel 是第一种 Domain 实现；未来 Script、Video、Knowledge 等 Domain 可以复用 Shell、导航、状态组件和命令协议，而无需改写整体 UI 架构。

本阶段不引入跨项目 Portfolio，不修改 Domain Source of Truth，不让 UI 直接读取 Projection 或文件系统，也不批量新增领域命令。

## 2. 产品边界

### Projection Inspector

现有高密度页面保留为开发和审计工具，负责展示完整 Projection、Source Ref、Trace、诊断和原始字段。Inspector 不作为普通创作入口，不承担正式 Workspace 的信息架构职责。

### Creative OS Workspace

正式 Workspace 面向创作者，只读取 Query Adapter 提供的页面级 ViewModel，默认隐藏哈希、完整来源引用和原始 Trace。一级导航固定为：

- Overview
- Chapters
- Story
- Characters
- Quality
- Runtime

Story 内部承载 Timeline、Foreshadow、Expectation、Open Loop 和 Story Arc。

## 3. 架构与扩展接口

```text
Domain / Knowledge / Runtime
            ↓
      Projection
            ↓
      Query Adapter
            ↓
  Domain-neutral ViewModel
            ↓
      Workspace UI
```

Workspace Shell 依赖以下稳定概念，而不是 Novel 专属字段：

```text
WorkspaceShell
├── DomainPlugin
├── OverviewViewModel
├── WorkItemListViewModel
├── WorkItemDetailViewModel
├── QualityQueueViewModel
├── RuntimeSummaryViewModel
└── CommandRegistry
```

Novel Workspace Plugin 将章节、角色、故事、质量和运行数据映射到这些接口。ViewModel 只负责汇总、排序、分组、窗口化、状态映射和展示优先级，不创造领域事实。

未来 Domain Plugin 必须能够提供：

1. Domain 标识与显示名称；
2. 一级导航项及其权限/可用状态；
3. 页面 ViewModel 查询映射；
4. 支持的 Command 描述；
5. 状态、空数据、错误和过期数据的展示元数据。

## 4. 页面布局与交互

```text
┌──────────────┬─────────────────────────────┐
│ Sidebar      │ Topbar                      │
│              ├─────────────────────────────┤
│ Overview     │ 页面标题 / Summary / Actions│
│ Chapters     │                             │
│ Story        │ List + Detail Drawer        │
│ Characters   │                             │
│ Quality      │                             │
│ Runtime      │                             │
└──────────────┴─────────────────────────────┘
```

布局规则：

- 页面使用 `100vh`，禁止整页无限纵向堆叠；
- Sidebar 和 Topbar 固定；
- 主工作区、列表区和详情区分别滚动；
- 列表用于扫描和筛选，详情抽屉用于对象级信息；
- Source Ref、Trace 和原始诊断只在详情或高级诊断区展开；
- 窄屏下 Sidebar 折叠，详情抽屉转为全宽面板，宽表格转为对象列表；
- 所有操作必须保留键盘焦点、明确状态和可访问名称。

## 5. 信息层级

Workspace 按四层展示：

```text
L1 总览：当前进度、阻塞、待办、最近活动
L2 模块：章节、故事、角色、质量、运行摘要
L3 对象：单章、单角色、单线索、单问题详情
L4 证据：Source Ref、Event、Execution Trace、原始投影
```

首页禁止直接展开全量章节、角色、Timeline 或 Trace。列表必须支持筛选，详情必须支持来源追溯。

## 6. 状态与错误

所有页面统一支持：

- loading：显示结构占位，不伪造数据；
- empty：说明缺少什么数据及下一步可行操作；
- unavailable：说明权威来源不可用；
- stale：明确显示最后刷新时间和过期原因；
- partial：标识缺失部分，不把部分数据伪装成完整数据；
- success / warning / blocked / error：不能只依赖颜色，必须同时使用文字或图标语义。

命令反馈继续复用 Unified Command Boundary 的 accepted、rejected、failed、retryable 和 trace/audit 引用，不在 ViewModel 中实现业务命令逻辑。

## 7. 实施分期

### 阶段一：Shell 与接口

- 建立 Workspace Shell、导航和布局令牌；
- 建立 Domain-neutral 页面 ViewModel 接口；
- 将当前 Overview 和 Chapters 迁移到新布局；
- 将 Inspector 从正式 Workspace 入口中分离；
- 增加桌面/窄屏布局和滚动验收。

### 阶段二：模块页面

- Story；
- Characters；
- Quality；
- Runtime；
- 章节恢复/重试等已经存在领域能力的安全入口。

### 阶段三：产品化收口

- 视觉细节与响应式调整；
- 键盘访问和焦点管理；
- 空、错、过期、部分数据状态；
- 浏览器端桌面与窄屏验收。

## 8. 验收标准

1. 正式 Workspace 不直接读取 Projection 内部实现或文件系统；
2. Inspector 与 Workspace 入口、视觉层级和职责清晰分离；
3. 页面不再把所有数据纵向铺开；
4. Overview、Chapters 至少具备列表/详情两级信息层；
5. 桌面端和窄屏均有独立滚动与可用布局；
6. Domain-neutral 接口不包含 Novel 专属业务事实；
7. 现有 Query Adapter、Command Boundary、Projection 和测试保持兼容；
8. 无数据、过期、部分和错误状态均有明确展示；
9. 视觉验收基于真实运行页面，而不是只依赖静态代码检查。

## 9. 非目标

- 不实现跨项目 Portfolio；
- 不把 Projection 改造成 UI 状态存储；
- 不在本阶段新增大规模 Domain 模型；
- 不直接把完整 Trace 和 Source Ref 复制到每个页面；
- 不为了视觉重构破坏现有命令边界和只读约束。
