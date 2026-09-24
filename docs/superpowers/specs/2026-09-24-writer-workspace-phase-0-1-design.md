# Writer Workspace Phase 0–1 设计规范

## 1. 阶段定位

本阶段将 Creative OS 从“只读项目观察界面”推进为可以安全编辑单章小说的中文 Writer Workspace。

阶段只解决三个问题：

1. 普通作者界面使用中文产品语言，不直接展示内部事件名、ID、路径和 Trace；
2. 明确《文明升阶》正文的权威来源与可写边界；
3. 建立“打开章节 → 编辑 → 保存 → 预览 → 版本恢复”的最小写作闭环。

完整 Agent Proposal、Diff、局部接受、反馈学习和自动创作决策属于后续阶段，不在本阶段实现。

## 2. 产品分层

Creative OS Web 保持三个相互独立的产品表面：

- Writer Workspace：作者阅读、编辑、保存和预览正文；
- Project Workspace：查看项目进度、质量、任务和运行摘要；
- Projection Inspector：查看原始 Projection、Event、Trace、SourceRef、ID 和诊断数据。

Writer Workspace 是 Novel Domain 专属界面，通过现有最小 Domain Registry 接入，不提升为 Creative OS Core 的通用编辑器，也不为未来 Domain 预造动态 UI。

## 3. 中文产品语言

底层领域模型、事件类型和稳定标识继续使用现有英文名称。普通作者界面通过 Presentation Mapper 转换为中文语义，不修改底层契约。

示例：

| 内部值 | 作者界面 |
| --- | --- |
| `UserRevised` | 作者修改了章节 |
| `TaskFailed` | 本次运行失败 |
| `partial` | 部分数据暂未更新 |
| `start_chapter_run` | 开始生成本章 |
| `trace_id` | 默认隐藏，进入 Inspector 查看 |

普通界面不得直接出现：

- trace_id、execution_id、event_id、projection_refresh_id；
- SourceRef、content hash、内部事件类型；
- `chapter_status`、原始文件路径和 JSON 字段名；
- 英文空状态、按钮、栏目标题和页脚说明。

Advanced Detail 可以显示中文错误类型、是否可重试、发生时间和影响对象；原始值仍只进入 Inspector。

## 4. 正文权威来源模型

实现前必须由代码审计确定《文明升阶》当前目录中以下来源的真实关系：

- LLM Writer Draft；
- Working Draft；
- Production Final Chapter；
- Publication Migration Source；
- Target Edition；
- Published Chapter；
- Chapter Contract / Review / Checkpoint。

第一版采用以下逻辑角色，具体物理路径由审计结果映射：

```text
Published Source       已发布正文，只读
Canonical Chapter      当前确认的正式正文，禁止编辑器静默覆盖
Approved Version       作者确认接受的版本
Working Draft          Writer Workspace 唯一直接写入目标
Agent Proposal         后续阶段的独立候选版本
```

Writer Workspace 读取章节时必须返回：来源角色、版本号、内容哈希、可编辑状态和来源引用。无法证明可编辑的章节默认只读。

## 5. 写入链路

所有保存操作必须遵守：

`Writer Workspace → Command Boundary → Draft Application Service → Version Store → Event → Projection Refresh`

禁止浏览器直接写文件；禁止直接覆盖 Published Source、Canonical Chapter 或 Production Final Chapter。

保存命令至少包含：

- command_id / request_id；
- actor；
- project_id / chapter_number；
- draft_id / base_version；
- expected_content_hash；
- title / body；
- idempotency_key。

返回状态明确区分：saved、conflict、rejected、failed。冲突必须保留用户当前文本，并允许重新加载或另存为新草稿。

## 6. Writer Workspace 页面

页面继续采用 macOS-inspired 浅色视觉体系，正文占据最大视觉空间。

桌面布局：

```text
Sidebar              Editor Area                    Utility
章节列表              标题 / 正文                    保存状态
项目入口              编辑 / 预览                    版本记录
Project Workspace     字数 / 字符数                  Agent 入口占位
Inspector
```

第一版只提供：

- 章节选择；
- 章节标题；
- 长文本正文编辑；
- 字数/字符数；
- 自动保存；
- 手动保存；
- 编辑/预览切换；
- 版本列表与恢复；
- 明确的只读状态；
- Agent 入口占位说明。

不实现复杂 Block Editor、协同编辑、出版排版、局部 Diff 或完整 Agent 面板。

## 7. 编辑器行为

- 支持中文长文本、段落、选择、撤销/重做和键盘导航；
- 输入期间不得由 Projection Refresh、路由切换或后台任务覆盖编辑器内容；
- 切换章节前如有未保存修改，必须保存成功或明确确认放弃；
- 自动保存采用去抖策略，只保存 Working Draft；
- 手动保存提供明确结果；
- 页面关闭或刷新前对未保存内容提供保护；
- 长章节不一次渲染额外的 Projection/Trace 数据。

保存状态只使用：

- 有未保存修改；
- 正在保存；
- 已保存；
- 保存失败；
- 版本冲突；
- 只读。

## 8. 预览

预览模式以中文小说阅读体验为目标，展示标题、正文段落、合适阅读宽度、字体和行距。

预览读取编辑器当前内容，因此未保存的修改也能预览；预览本身不触发保存或修改 Canonical Chapter。

## 9. 版本与恢复

每次成功保存形成可追溯 Draft Version，记录：

- version_id；
- base_version；
- content_hash；
- actor；
- created_at；
- source_role；
- optional message。

恢复旧版本不直接删除新版本，而是以所选版本内容创建一个新的 Working Draft Version。版本历史必须可追溯、不可静默改写。

## 10. Agent 边界

第一版只保留统一 Agent 入口和自然语言意图输入的产品位置，不实现完整执行。

后续 Agent 必须复用现有 Task、Runtime、Retriever、Context、Command Boundary 和 Event Log，不建立第二套 Runtime。Agent 默认产生 Proposal，不直接修改 Working Draft 或 Canonical Chapter。

人物、基调、情绪、伏笔和节奏属于 Agent 可检索和推理的 Creative Context，不是强制填写的写作模板。

## 11. 错误与恢复

- 读取失败：保留当前编辑器内容，显示中文错误和重试入口；
- 自动保存失败：停止“已保存”提示，保留本地修改并允许手动重试；
- 版本冲突：禁止覆盖，显示服务器版本和当前本地版本的选择；
- Projection 刷新失败：保存结果仍按 Version Store 的权威写入结果显示，同时提示项目状态可能未更新；
- 章节只读：说明原因和来源角色，不显示不可用的保存按钮。

## 12. 测试与验收

必须验证：

1. Published/Canonical 章节无法被编辑器直接覆盖；
2. Working Draft 能保存并生成新版本；
3. expected hash 不一致时返回 conflict，用户文本不丢失；
4. 自动保存失败后仍保留编辑内容；
5. 恢复旧版本会创建新版本，不删除历史；
6. 编辑/预览使用相同的当前文本；
7. 普通作者界面不暴露内部 ID、英文事件名和原始路径；
8. Inspector 仍能访问完整诊断；
9. Web 不绕过 Command Boundary 直接写文件；
10. 使用《文明升阶》真实章节完成浏览器验收。

## 13. 完成定义

本阶段完成时，作者能够在 Creative OS 中安全完成：

`选择一章 → 阅读 → 编辑 → 自动/手动保存 → 预览 → 查看版本 → 恢复版本`

同时满足：中文优先、正文不丢失、Published/Canonical 不被静默覆盖、所有写入可追溯。

完成后再进入下一阶段：Agent Proposal、Diff、Human Decision 与 Feedback 学习闭环。
