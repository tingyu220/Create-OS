# Workspace V0.1 浅色 Creative Workspace 设计规范

## 1. 目标

将当前偏开发者控制台的单项目 Workspace 重构为面向创作者的浅色 Creative Workspace。用户打开页面后，应在 30 秒内回答：

1. 作品当前进展到哪里；
2. 当前最重要的任务是什么；
3. 是否存在阻塞或需要关注的问题；
4. 最近发生了什么；
5. 下一步建议做什么。

本规范只覆盖单个小说项目的 Workspace V0.1。Domain、Knowledge、Runtime 仍是唯一事实来源，Projection 只读，Workspace 只通过 Query Adapter 读取稳定 ViewModel；所有写操作必须经过 Command Boundary。

## 2. 非目标

- 不开发跨项目 Portfolio 或多项目总览。
- 不新增第二套领域事实或 UI 专用业务规则。
- 不把 Projection Inspector 的原始数据搬到普通创作者界面。
- 不在本阶段实现完整编辑器、审批工作台或生产控制台。
- 不引入 React/Vue 等大型前端迁移；保留当前原生 HTML/CSS/JS 运行方式。

## 3. 信息架构

固定桌面布局为 Sidebar、Topbar、Main Content 三部分。Sidebar 和 Topbar 固定，Main Content 独立滚动，禁止整页无限纵向堆叠。

### Sidebar

- 项目身份：项目名、项目状态、当前数据新鲜度。
- 总览：Overview。
- 创作：章节、故事、角色。
- 系统：质量、运行。
- Inspector 入口：以独立工具入口打开 Projection Inspector。

第一版仅注册《文明升阶》。其他 Domain 只能通过最小 Registry/Descriptor 插槽接入，不显示空的伪模块。

### Overview

Overview 是默认入口，按以下顺序展示：

1. 项目进度与当前章节/阶段；
2. “下一步建议”主卡片；
3. Blocking 与 Warning 队列；
4. 当前任务和最近活动；
5. 章节、质量、运行的轻量摘要。

主界面只展示可行动的摘要。trace_id、事件哈希、原始错误堆栈和完整 Projection JSON 只能通过 Inspector 或详情展开查看。

### Chapters

章节页面采用 List + Detail：左侧为独立滚动的章节列表，右侧为固定详情面板。列表显示编号、标题、阶段、质量状态和问题数量；详情显示状态来源、阶段、质量结果、关联任务和可追溯证据。小屏幕下详情转为列表项下方的抽屉。

### Quality

质量页面按 pending、blocked、resolved 分组，统一呈现 Review、Gate、Issue。每项显示严重级别、影响对象、原因摘要、建议动作和来源引用，不直接暴露底层事件结构。

### Runtime

运行页面只显示当前任务、最近运行、尝试次数、token/usage 摘要、错误摘要、恢复/重试状态和最近活动。完整 trace、诊断上下文和原始日志通过“打开 Inspector”进入独立面板。

## 4. Core 与 Novel 边界

Core Workspace 只负责跨 Domain 通用能力：

- project identity / snapshot freshness；
- task、runtime、attempts、usage；
- quality、error、recovery、trace 摘要；
- recent activity、blocking/warning；
- Query Adapter、Command Boundary、状态和错误契约。

Novel Domain 只负责小说事实：

- chapters、characters、story threads、timeline；
- 小说章节阶段、叙事质量和小说特有的来源引用。

Core 不读取 Novel 内部对象；Novel 不复制 Core 状态。二者只通过稳定的 Projection ViewModel 和 Domain Descriptor 组合。

## 5. 最小 Domain Registry 契约

Registry 只描述可挂载的 Domain，不负责动态生成页面或业务逻辑：

```ts
type DomainDescriptor = {
  id: string;
  label: string;
  navigation: Array<{ id: string; label: string; view: string }>;
  capabilities: string[];
  snapshotKeys: string[];
};
```

V0.1 仅注册 `novel`。未来 Domain 必须声明自己的 snapshot keys 和 navigation，并复用 Core Workspace 的查询、状态、错误和追溯契约；禁止通过 Registry 注入任意业务组件。

## 6. Query Adapter 与 ViewModel 约束

Web 层只能依赖统一 Query Adapter，不得直接读取 Domain、Knowledge、Runtime、Projection 文件或内部 Python 对象。Adapter 只组合已有 Projection，禁止创造领域事实。

所有 ViewModel 均须携带：

- `status`: `fresh | stale | unavailable | partial`；
- `generated_at` 与可选 `source_version`；
- `source_refs`，用于追溯状态来源；
- `errors` 或 `diagnostics` 摘要（不得默认展开原始堆栈）。

列表和摘要必须限制数量并提供“查看全部/打开 Inspector”路径。Adapter 接口不得绑定“全量扫描”，应保留未来 Event Log 增量刷新能力。

## 7. 写入链路

任何 UI 变更都必须遵守：

`Web → Command Boundary → Application/Domain → Event → Projection Refresh → Query Adapter`

Command 至少包含 command_id、request_id、actor、target、payload、expected_version 和 idempotency_key。返回值明确区分 accepted、rejected、failed，并携带 conflict、validation、audit 和 trace 信息。UI 不得直接修改 Projection 或 Domain。

## 8. 视觉系统

- 画布：暖白背景；Sidebar 使用略深的浅灰；内容区域使用白色卡片。
- 强调色：单一低饱和 teal，用于主操作、当前导航和可交互链接。
- 状态色：阻塞使用红、警告使用琥珀、完成使用绿色，同时配合文字和图标，不能只靠颜色传达。
- 分隔：使用弱边框和充足留白，避免大面积阴影和渐变。
- 字体：系统字体栈，正文 14–16px，标题采用清晰的层级比例。
- 组件：状态徽章、进度条、摘要卡、列表行、详情面板、空状态、错误状态和 Inspector 入口统一样式。

## 9. 响应式与可访问性

桌面宽度下使用固定 Sidebar 与双栏内容；窄屏下 Sidebar 收缩为可展开导航，章节 List + Detail 变为单栏抽屉。每个主要区域必须有可见标题和键盘焦点顺序；按钮和状态不依赖颜色；滚动容器须有明确边界、可见滚动行为和 `aria-label`。

## 10. 状态处理

- `fresh`：展示当前数据与更新时间。
- `stale`：保留最近快照，但显式显示“数据可能不是最新”，提供刷新/重试入口。
- `partial`：显示已知部分并说明缺失范围，不伪装成完整数据。
- `unavailable`：显示原因摘要、诊断入口和可执行的恢复动作。

所有状态都必须由 Query Adapter 传递到 UI；UI 不自行推断“当前”或吞掉刷新失败。

## 11. 测试与验收

### 跨层测试

1. Domain change → Event → Projection refresh → Query Adapter 返回最新状态。
2. Projection stale 时，Adapter 明确暴露 stale。
3. Projection refresh failure 可诊断、可重试。
4. Query Adapter 不绕过 Projection 读取业务内部状态。
5. Command Boundary 的接口约束可被未来 Web Workspace 复用。

### UI 验收

- 真实《文明升阶》数据可加载，且不依赖 mock 才能展示主路径。
- 首屏 30 秒内可识别进度、当前任务、Blocking/Warning、最近活动和下一步建议。
- 主界面没有原始 trace、长错误堆栈或无限纵向数据堆叠。
- 桌面与窄屏均有独立滚动和可用的 List + Detail 交互。
- Projection Inspector 仍能查看完整诊断数据，且与创作者界面保持独立。
- Core Workspace 与 Novel Domain 的 ViewModel/DTO 边界通过测试验证。

## 12. 交付边界

实现完成后，先在独立分支完成代码审查、回归测试和真实浏览器验收，再创建 PR 并合并到 `main`。合并后冻结 Workspace V0.1，不继续堆叠同一阶段的视觉功能；下一阶段转向《文明升阶》的真实创作反馈闭环：`Feedback → Lesson → Knowledge → Future Context`。
