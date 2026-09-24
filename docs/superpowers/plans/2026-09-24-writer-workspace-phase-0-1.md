# Writer Workspace Phase 0–1 实施计划

> 日期：2026-09-24  
> 范围：单小说项目、第一版编辑闭环与 Agent Intent 入口契约  
> 前置设计：`docs/superpowers/specs/2026-09-24-writer-workspace-phase-0-1-design.md`

## 目标与边界

本计划把当前“只读投影工作台”推进为可实际写作的 Writer Workspace，但只做一个可验证的最小闭环：

```text
选择章节 → 读取正文 → 编辑 → 自动/手动保存 → 预览 → 查看版本 → 恢复版本
```

同时完成 Agent 的自然语言入口契约：用户可以只说“这一章目前写得不对，你自己检查一下”，系统接收该意图并返回稳定的任务/会话标识；本阶段不实现完整自主诊断、提案生成或自动改稿。

本阶段明确不做：完整 Agent Proposal 执行、跨项目 Portfolio、发布覆盖、生产最终稿静默改写、第二套领域事实、完整评论/审批工作台、复杂富文本编辑器。

## 现有实现基线

- `creative_os/workspace_query.py` 与 `workspace_dto.py` 是当前只读投影查询入口。
- `creative_os/workspace_view_models.py` 已有章节列表/详情的领域中立 ViewModel，但章节正文不是其职责。
- `creative_os/web_workspace.py` 当前只暴露 `/api/workspace`、刷新、接受审阅问题和启动章节运行。
- `creative_os/workspace_command.py`、`workspace_command_adapter.py` 是统一命令边界，新增写入必须复用它们。
- `creative_os/importing/materializer.py` 与项目 `production/final_chapters` 代表导入/正式章节来源，不能被浏览器直接写入。
- 现有 `ProjectSnapshot`、Runtime/Event Log 和 Projection 继续作为状态事实来源；Writer Workspace 只增加“工作稿及其版本”这一受控写入边界。

## 实施任务

### 1. 来源审计与 Writer DTO 契约

先写测试，锁定单章来源优先级、可编辑性和版本状态：

1. 审计项目中已发布章节、生产最终章节、当前草稿、运行产物、导入源的实际路径和读写责任。
2. 定义 `WriterChapterDTO`、`WriterSourceDTO`、`WriterVersionDTO`、`WriterChapterEnvelope`，至少包含：章节编号/标题、正文、来源角色、可编辑标志、版本号、更新时间、内容哈希、来源引用、freshness/partial/unavailable 状态。
3. 明确来源角色：Published/Canonical/Approved 只读；Working Draft 唯一可写；Agent Proposal 仅作为未来扩展接口。
4. DTO 编码不得把内部路径、哈希、事件 ID 默认展示给普通 Writer UI；证据引用只保留稳定引用键，Inspector 另行展开。

建议文件：

- 新增 `creative_os/writer_workspace_dto.py`；
- 新增或扩展 `creative_os/writer_source.py`；
- 新增 `tests/test_writer_workspace_dto.py`、`tests/test_writer_source_audit.py`。

验收：对真实《文明升阶》项目至少读取一章，能明确回答“当前展示的是哪一层、是否可编辑、为什么”。

### 2. 中文 Presentation Mapper

先补映射测试，再接入现有 Workspace 与 Writer 响应：

1. 新增独立 Presentation Mapper，集中处理 `fresh/stale/partial/unavailable`、任务状态、事件类型、错误码、命令名称和运行阶段。
2. 覆盖至少：`UserRevised`、`TaskFailed`、`ReviewFailed`、`start_chapter_run`、`partial`、`unavailable`、重试/恢复状态。
3. 普通页面不显示 `trace_id`、`projection_refresh_id`、内部 source path、event sequence、content hash；仅在 Inspector/详情抽屉展示并保留复制能力。
4. 既有 Projection UI 与新 Writer UI 共同调用该 Mapper，禁止各页面自行拼接英文标签。

建议文件：

- 新增 `creative_os/workspace_presentation.py`；
- 新增 `tests/test_workspace_presentation.py`；
- 修改 `creative_os/workspace_view_models.py`、`creative_os/workspace_dto.py`、`creative_os/web_workspace.py` 的编码出口。

验收：普通页面全部使用中文产品词汇；技术引用仍可在 Inspector 追溯。

### 3. Working Draft 版本存储与命令边界

采用 TDD 先定义失败行为，再实现最小服务：

1. 新增工作稿存储接口，版本记录至少包含 `project_id`、`chapter_number`、`version`、`content`、`content_hash`、`created_at`、`actor`、`parent_version`、`source_refs`。
2. 实现读取当前工作稿、创建新版本、恢复指定版本；首次编辑从只读 Canonical/Approved 内容复制为 Working Draft，不修改源文件。
3. 新增命令：`open_writer_chapter`（只读）、`save_writer_draft`、`restore_writer_version`。命令必须走 `CommandBoundary`，带 `request_id`、`actor`、`expected_version`、幂等键和审计引用。
4. 处理版本冲突、重复提交、空正文、超大正文、未知章节、只读来源写入、存储失败；返回中文稳定错误码。
5. 每次成功保存/恢复写入 Event Log，并触发最小 Projection Refresh 或标记待刷新，不允许 Query Adapter 直接读文件绕过事件。

建议文件：

- 新增 `creative_os/writer_draft_store.py`、`creative_os/writer_command.py`；
- 修改 `creative_os/workspace_command.py`、`creative_os/workspace_command_adapter.py`、`creative_os/web_workspace.py`；
- 新增 `tests/test_writer_draft_store.py`、`tests/test_writer_commands.py`、`tests/test_writer_command_http.py`。

验收：成功保存后版本递增、事件可追溯；并发保存返回 conflict；重复 request 不产生第二个版本；Canonical/Published 永不被覆盖。

### 4. Writer Query Adapter 与 HTTP 边界

1. 在现有 `WorkspaceQueryAdapter` 之外增加面向 Writer 的查询适配器，不让浏览器直接依赖 `ProjectSnapshot`、领域模型或文件系统。
2. 增加只读接口：章节列表、章节正文、版本列表、单版本内容、来源与可编辑性状态。
3. 增加写接口：保存工作稿、恢复版本；所有写请求进入统一命令边界。
4. 统一 HTTP 状态：成功读取 200，保存接受 202，版本冲突 409，校验失败 422，来源不可用 503；响应中只返回稳定 DTO。
5. 保留 trace/audit/source refs，但普通响应隐藏内部标识，Inspector 查询可按引用展开。

建议修改 `creative_os/web_workspace.py` 与 `scripts/novel_web_workspace.py`，新增 `tests/test_writer_query_adapter.py`、`tests/test_writer_routes.py`。

### 5. Writer Workspace 前端最小闭环

先完成交互测试与 DOM 契约，再实现样式：

1. 新增 Writer 页面入口（建议 `/writer`），保持现有 Project Workspace 与 Projection Inspector 独立。
2. 左侧仅显示章节选择与搜索；主区域显示标题、正文编辑器、字数、保存状态、来源角色和版本入口；底部提供预览切换。
3. 支持手动保存、受控自动保存（去抖、失败重试、冲突停写）、加载状态、保存成功/失败/冲突提示、版本恢复确认。
4. 页面默认中文、浅色 macOS-inspired 视觉；技术字段进入“来源详情/Inspector”抽屉，不污染正文阅读区。
5. Agent 区只先提供自然语言输入框和“检查本章”按钮，提交后显示受理状态与任务引用；不在本阶段伪造诊断结果。

建议文件：

- 新增 `creative_os/web/writer.html`、`creative_os/web/writer.js`；
- 修改 `creative_os/web/styles.css`、`creative_os/web_workspace.py`；
- 新增 `tests/test_writer_shell_assets.py`、`tests/test_writer_interactions.py`。

验收：真实项目中完成一次“打开第 79 章 → 改一段 → 保存 → 刷新页面仍保留 → 查看版本 → 恢复旧版本 → 预览”的闭环。

### 6. Agent Intent 入口契约

1. 定义 `AgentIntentRequest/Response`，输入只需自然语言、目标章节和可选 actor/request_id。
2. 允许用户使用“这一章目前写得不对，你自己检查一下”这类意图，不强迫用户选择人物/节奏/伏笔/情绪检查项。
3. 系统先建立可追踪的 Agent Task/Session，并返回“已受理/排队/不可用”等状态；上下文选择由后续 Agent Runtime 自主完成。
4. 契约保留未来诊断结果字段：优先级问题、证据范围、建议动作、置信度/不确定性、`查看修改方案/让 Agent 修改/我自己改` 三类后续动作。
5. 本阶段禁止把固定检查清单硬编码为用户必填项，也禁止隐藏思维链或直接覆盖工作稿。

建议新增 `creative_os/agent_intent.py` 与对应 DTO/测试；后续完整自主诊断单独立项。

### 7. 跨层测试与真实项目验收

必须覆盖：

1. 只读 Canonical → Working Draft 初始化 → 保存版本 → Event → Query Adapter 返回最新版本。
2. 版本过期时保存明确返回 conflict，不伪装成功。
3. 存储/刷新失败可诊断、可重试，且页面不丢失本地编辑内容。
4. 普通 Writer 页面不直接读取 Projection 内部对象或文件；通过接口契约测试锁定边界。
5. 中文 Presentation Mapper 对所有普通状态生效，Inspector 仍能追溯原始引用。
6. Agent Intent 只创建可追踪请求，不产生未经确认的正文修改。
7. 对真实《文明升阶》第 79 章执行浏览器验收；保留现有 Workspace/Projection 测试及已知全量测试基线，不把无关历史失败误判为本阶段回归。

## 执行顺序与检查点

按以下顺序实施，每个阶段都先测试后代码，并在阶段末进行小范围审查：

1. 来源审计 + DTO；
2. 中文 Presentation Mapper；
3. Draft Store + Command Boundary；
4. Query Adapter + HTTP；
5. Writer 前端闭环；
6. Agent Intent 入口；
7. 跨层测试与真实项目验收。

完成第 3 步后必须确认“正式章节永不被覆盖”；完成第 5 步后必须进行真实浏览器验收；完成第 7 步后才允许讨论 PR。

## 完成定义

- Writer 页面可以稳定打开单章并编辑长文本；
- 保存、自动保存、冲突、失败、恢复均有可理解的中文反馈；
- 正式章节和投影事实没有被 Writer 页面直接改写；
- 所有写入均经过 Command Boundary，并有 Event/Trace/Version 记录；
- Agent 可以接收自然语言“自己检查”意图，但不会假装已经完成自主诊断；
- 真实项目闭环通过，现有 Workspace/Projection 回归不退化；
- 尚未实现的自主诊断与提案执行明确列为下一阶段，而不是在 UI 中伪装完成。

