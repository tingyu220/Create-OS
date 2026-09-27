# 项目状态评估时间线

以下内容保留不同阶段的权威评估快照；较新快照描述后续能力，不应反向改写早期验收记录。

## 2026-08-20 快照

# 项目状态验收

## 2026-08-20 章节合同与叙事回放基础

基线：`codex/legacy-novel-continuation`，包含既有 3-30 章生产验证能力。本阶段扩展现有 Novel Domain，没有建立第二套 Director 或生产合同模型。

### 已实现

- `narrative_decision.ChapterContract` 继续作为已审批生产合同。
- `ReplayedChapterContract` 作为只读审计投影，允许证据不足的字段为 `unknown`。
- 生产 Artifact 读取器按稳定顺序读取正式正文、Context、Review、Knowledge 和 Task。
- 回放器只映射结构化字段，不从正文关键词推测人物心理或读者认知。
- Reviewer 覆盖五项门禁：人物选择缺失、选择代价缺失、Reader State 未知、近期章节功能重复、结尾变化未知。
- CLI 稳定生成 JSON 和 Markdown 报告，Reviewer 不修改正文、Knowledge 或 Project State。

### 正式回放

项目：`projects/validation_novel`

```text
chapter range: 1-6
chapter_count: 6
issue_count: 12
unknown_field_count: 36
traceable: true
canonical chapter hashes unchanged: true
```

报告：

- `projects/validation_novel/production/reports/narrative_replay_001_006.json`
- `projects/validation_novel/production/reports/narrative_replay_001_006.md`

旧生产 Artifact 能明确证明各章 Scene Goal 和最终 Outcome，因此章节功能与结尾变化可追溯。它们没有显式保存戏剧问题、人物选择、Reader State 和压力曲线，所以相关字段保持 `unknown`；这属于可靠性保护，不是自动补全失败。

### 验收结果

- 完整测试：`235 passed`。
- 第 1-6 章各有且仅有一个回放合同。
- 所有确定性结论均带项目相对路径和证据摘录。
- 五项 Reviewer 门禁均有自动化测试，且只返回 Issue。
- 两种报告可重复生成，内容稳定。
- 回放前后六章正式正文 SHA-256 一致。
- 未新增自动改纲、正文生成、自动修复、数据库、前端或外部模型依赖。

下一阶段门禁：人工抽查回放证据，确认没有错误映射后，再规划回放基础与现有 Narrative Director、Chapter Contract Approval 的正式接入；当前报告不宣称该下一阶段已经完成。
---

## 2026-08-18 快照

# Creative OS 当前项目框架与能力评估

> 评估时间：2026-08-20
> 评估对象：Creative OS V1.1 Production Ready（当前工作区代码、测试与生产产物）

## 1. 结论摘要

Creative OS V1.1 已完成从系统底座到整书生产的端到端验证，核心闭环成立：

```text
Task -> Retriever -> Context -> Capability -> Result -> Compiler -> Knowledge
```

当前版本的准确定位是：**小说生产闭环已经通过验证，作者级叙事决策能力尚未落地。**

- V1 执行计划中的 M1-M15 已落地，当前 85 个测试全部通过。
- Foundation、Engine、Capability、Novel Domain 的边界清晰，Knowledge 写入入口受 Compiler 控制。
- 《雾城回声》已完成 36/36 章、108/108 Scene，Task、Context、Result、Review、Knowledge Patch、运行记录和恢复状态均有生产证据。
- 真实模型写作、重试反馈、断点续跑、耗时与 token 指标、事实校验和最终稿提升流程已经实现。
- 当前新增的《作者式动态叙事控制层设计》尚停留在设计阶段，`Narrative State`、`Director`、`Planner`、章节合同、动态改纲和叙事审核门禁尚未实现。
- 当前主要瓶颈已从“能否持续写完”转为“能否在写作前形成可审计的作者级叙事决策”。

## 2. 当前框架结构

### 2.1 分层结构

```text
creative_os/
├─ foundation/                 通用数据与生命周期
│  ├─ knowledge.py             KnowledgeStore、状态、引用索引、删除备份
│  ├─ project.py               Project、Milestone、进度
│  ├─ task.py                  Task、依赖、优先级、可运行任务
│  └─ state.py                 小型 ProjectState 与边界校验
├─ engine/                    通用创作引擎
│  ├─ workflow.py              阶段流转
│  ├─ retriever.py             基于标签的规则检索
│  ├─ context.py               Context 组装、大小与边界校验
│  └─ compiler.py              Result -> CompiledKnowledge
├─ capability/                能力层，只接收 Context
│  ├─ writing.py               模板写作能力
│  ├─ review.py                规则优先审核能力
│  └─ research.py              Provider 注入式研究能力
├─ domains/
│  ├─ base.py                  DomainPackage 契约
│  └─ novel.py                 Novel Schema、规则、模板、流程
└─ pipeline.py                 端到端编排入口
```

### 2.2 运行时依赖关系

`CreativePipeline.run()` 当前按以下顺序执行：

1. 将传入 Task 转为 `doing`。
2. Retriever 按 `Task.tags + Domain.default_retrieval_tags` 从索引取 Knowledge。
3. ContextBuilder 校验任务、状态、领域一致性，并限制条目数和字符估算量。
4. Capability 只读取 Context，生成 `Result`。
5. Compiler 将 Result 转成 `CompiledKnowledge`。
6. KnowledgeStore 应用编译结果。
7. 当前 Task 转为 `done`，返回一个依赖当前任务的 Review Task。

生产验证扩展主要位于 `production.py`、`validation_runtime.py`、`llm_writer.py`、`batch_runner.py` 和对应测试中。

## 3. 已经做到的能力

| 能力 | 当前实现 | 证据 | 状态 |
|---|---|---|---|
| Knowledge 管理 | 分类、生命周期、标签索引、引用索引、归档、删除前备份 | `creative_os/foundation/knowledge.py`、`tests/test_knowledge_model.py` | 已实现 |
| Project 管理 | 阶段状态机、Milestone、派生进度 | `creative_os/foundation/project.py`、`tests/test_project_model.py` | 已实现 |
| Task 驱动 | 状态、依赖、优先级、Owner、runnable 排序 | `creative_os/foundation/task.py`、`tests/test_task_model.py` | 已实现 |
| 小型 State | 当前阶段、当前任务、目标、领域、最多 10 条风险；拒绝额外字段 | `creative_os/foundation/state.py`、`tests/test_state_model.py` | 已实现 |
| 通用 Workflow | 默认流程和 Domain 自定义阶段，禁止跳阶段 | `creative_os/engine/workflow.py`、`tests/test_workflow_model.py` | 已实现，但未接入主 Pipeline 推进 |
| Context 组装 | User Input、Task、State、Knowledge、Domain Rules；边界和大小校验 | `creative_os/engine/context.py`、`tests/test_context_model.py` | 已实现 |
| 规则检索 | 标签倒排索引、匹配度排序、限制数量、排除 Archived | `creative_os/engine/retriever.py`、`tests/test_retriever_model.py` | 已实现；仅规则检索 |
| Result 编译 | Entity、Fact、Relationship、Summary；Research Draft 转 External Draft | `creative_os/engine/compiler.py`、`tests/test_compiler_model.py` | 已实现；解析规则较简化 |
| Writing | Context-only 输入，输出 Writing Result | `creative_os/capability/writing.py`、`tests/test_capability_model.py` | 已实现为模板能力 |
| Review | 缺少检索知识时生成 Issue 和 Fix Task | `creative_os/capability/review.py`、`tests/test_capability_model.py` | 已实现最小版本 |
| Research | Provider 注入、输出 Knowledge Draft，不直接写 Store | `creative_os/capability/research.py`、`tests/test_capability_model.py` | 已实现接口原型 |
| Novel Domain | 9 类 Schema、规则分组、模板、小说阶段流程 | `creative_os/domains/novel.py`、`tests/test_novel_domain.py` | 已实现最小包 |
| V1 闭环 | Task 到 Knowledge 的完整调用链，并生成后续 Review Task | `creative_os/pipeline.py`、`tests/test_v1_pipeline.py` | 已验证 |

## 4. 与最初 V1 设计/执行计划的差别

### 4.1 已符合的部分

`EXECUTION_PLAN.md` 中的四项 V1 验收标准均有代码和测试证据：

- 能维护 Knowledge。
- 能根据 Task 组织最小 Context。
- Capability 只依赖 Context 完成工作。
- Result 必须经过 Compiler 才能回写 Knowledge。

Novel 也已完成 Schema、Rule、Template、Workflow 四个阶段，符合“先通用底座，后领域包”的原始路线。

### 4.2 V1 计划与当前代码的细节偏差

| 设计期望 | 当前实际 | 影响 |
|---|---|---|
| Workflow 负责推进 ProjectState | Workflow 已有 `advance()`，但 `CreativePipeline.run()` 没有调用它，也没有持久化 Task/State | 主流程可运行，但跨任务连续推进仍靠调用方手动编排 |
| TaskStore 负责完整任务链 | Pipeline 只返回 `next_task`，没有写入 TaskStore | Review Task 不会自动进入可调度队列 |
| Retriever 输入包含 Task、State、Domain | 当前 `retrieve()` 没有接收 State | 检索无法直接利用当前阶段、风险和目标 |
| Compiler 负责冲突、重复、索引、时间线和摘要树 | 当前主要是按行解析文本并生成 KnowledgeItem | 复杂事实合并、一致性和历史演化尚未解决 |
| Review 做设定、时间线、人物、规则检查 | 当前主要检查“是否有检索到 Knowledge” | 审核能力尚不足以支撑长篇创作 |
| Research Provider 支持联网/文件/MCP 等来源 | 当前只有可注入的 `Callable[[str], str]` | 具备扩展点，但没有真实数据接入和引用验证 |
| Knowledge 是长期可信数据源 | 通用 `KnowledgeStore` 仍以内存模型为主；生产验证通过 JSON Artifact 和 Project State 持久化 | 已证明生产恢复，但正式可迁移的持久化知识仓库仍待建设 |

## 5. 与最新“作者式动态叙事控制层”设计的差别

这份设计文档定义的是 V1 之后的新架构目标，当前代码尚未实现以下核心对象和流程：

| 设计文档要求 | 当前状态 |
|---|---|
| `Novel State`：人物、地点、事件、时间线、伏笔、信息边界的结构化事实投影 | 未实现，Novel 目前只有 SchemaDefinition 和规则字符串 |
| `Narrative State`：Story Contract、Volume、Arc、Rolling Window、Chapter Contract、Scene Plan | 未实现 |
| `Director`：章节级叙事决策、信息揭露、伏笔推进、改纲提案 | 未实现 |
| `Planner`：将导演决策拆成场景和行动任务 | 未实现 |
| Writer 依据已审批计划写正文 | 当前是模板化输出，没有审批计划输入 |
| Reviewer 的 10 项叙事审核门禁 | 未实现；当前只有最小规则检查 |
| `OutlineChange` 动态改纲协议和影响分析 | 未实现 |
| 事件记录 + 当前投影的版本化生命周期 | 未实现 |
| 《文明升阶》第 1 至 6 章回放报告 | 未发现实现或报告 |
| “回放完成前不生成第 7 章、不接入网文库、不远程提交” | 当前没有对应的执行门禁代码 |

因此，当前项目与最新设计的关系是：**V1 通用底座已具备接入位置，但叙事控制层尚未开始工程化落地。**

## 6. 生产验证后的反馈

以下反馈来自完整验证小说、生产产物、测试集和真实模型写作试运行。

### 6.1 使用感受较好的地方

- **边界清楚**：Capability 不拿 Store、不读文件，必须通过 Context 工作；这让调用链容易审计。
- **闭环直观**：一次 Pipeline 调用能看到输入 Task、检索到的 Knowledge、Result、编译产物和下一步 Review Task。
- **检索可解释**：标签命中和匹配度排序简单，出现“为什么拿到这条知识”时有明确原因。
- **状态约束有效**：Task、Project、Knowledge、State 都有显式状态机，非法跳转会立即报错。
- **生产闭环已有证据**：36 章和 108 个 Scene 均保留 Task、Context、Draft、Review、Knowledge 和 Run Artifact。
- **真实写作链路已接入**：支持模型调用、失败重试、审核反馈回灌、断点续跑、指标记录与最终稿提升。

### 6.2 真实使用时最明显的摩擦

- **验证运行时过度集中**：`validation_runtime.py` 同时承担样本数据、生产编排、正文模板、审核、编译和报告生成，适合作为验收脚手架，不适合作为下一阶段核心架构。
- **项目样本与通用能力耦合**：《雾城回声》的蓝图和具体生产逻辑需要从可复用运行能力中进一步隔离。
- **Review 仍偏结果检查**：能够检查事实、格式、重复和文本质量，但还不能系统判断章节职责、人物主动选择、代价、读者认知变化和伏笔生命周期。
- **检索依赖人工打标签**：无标签时直接返回空结果，不做语义兜底；标签体系增长后维护成本会快速上升。
- **叙事控制尚未进入使用链路**：当前无法回答“本章为什么存在、谁做了选择、代价是什么、读者认知如何变化”。

## 7. 建议的后续优先级

### P0：章节合同与叙事回放

1. 实现最小 `Narrative State`、`Chapter Contract`、Reader State、人物主动性账本和伏笔生命周期。
2. 使用现有第 1 至 6 章做只读回放，不生成新正文。
3. 输出带证据与不确定性标记的章节解释和叙事问题报告。

### P1：叙事审核门禁

1. 检查章节功能重复、人物主动选择与代价、读者认知变化、压力变化和伏笔推进。
2. Reviewer 只报告证据、严重级别和修复任务，不直接修改正文。
3. 将验证小说建立为后续版本的固定叙事回归样本。

### P2：Director 与生产链接入

1. Director 只输出结构化章节决策，不写正文、不静默修改事实。
2. Chapter Contract 经人工审批后，Planner 和 Writer 才能执行。
3. 最后增加 `OutlineChange`、影响分析和显式修订任务。

## 8. 验证记录与边界

- `python -m pytest -q`：85 passed。
- `python -m compileall -q creative_os`：通过。
- 生产证据：36/36 章、108/108 Scene，完整产物见 `projects/validation_novel/production/`。
- 本报告未进行远程仓库提交或推送，也未改变已有用户修改。

