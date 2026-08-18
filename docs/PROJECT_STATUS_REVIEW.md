# Creative OS 当前项目框架与能力评估

> 评估时间：2026-08-18  
> 评估对象：Creative OS V1.0（当前工作区代码与文档）

## 1. 结论摘要

Creative OS V1 已经完成一个可运行、可测试的创作系统底座，核心闭环成立：

```text
Task -> Retriever -> Context -> Capability -> Result -> Compiler -> Knowledge
```

当前版本的准确定位是：**工程验证完成的内存原型**，还不是生产可用的长期创作工具。

- V1 执行计划中的 M1-M15 已基本落地，33 个测试全部通过，`compileall` 通过。
- Foundation、Engine、Capability、Novel Domain 的边界清晰，Knowledge 写入入口受 Compiler 控制。
- 当前新增的《作者式动态叙事控制层设计》尚停留在设计阶段，`Narrative State`、`Director`、`Planner`、章节合同、动态改纲和叙事审核门禁尚未实现。
- 真实使用的主要瓶颈不是“能否跑通”，而是持久化、长周期状态推进、检索质量、审核深度、规模压力和人工审批流程均未验证。

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

CodeGraph 当前索引：31 个 Python 文件、283 个节点、742 条边；索引状态为最新。

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
| Knowledge 是长期可信数据源 | 当前 Store 仅驻留内存 | 进程结束即丢失，尚未形成真实知识库 |

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

## 6. 具体使用反馈

以下反馈来自当前测试集和实际冒烟调用，不冒充长期用户调研结论。

### 6.1 使用感受较好的地方

- **边界清楚**：Capability 不拿 Store、不读文件，必须通过 Context 工作；这让调用链容易审计。
- **闭环直观**：一次 Pipeline 调用能看到输入 Task、检索到的 Knowledge、Result、编译产物和下一步 Review Task。
- **检索可解释**：标签命中和匹配度排序简单，出现“为什么拿到这条知识”时有明确原因。
- **状态约束有效**：Task、Project、Knowledge、State 都有显式状态机，非法跳转会立即报错。
- **原型反馈速度快**：当前 33 个测试耗时约 0.14 秒，适合快速验证模型和规则。

### 6.2 真实使用时最明显的摩擦

- **像一次性执行器，不像长期工作台**：Pipeline 返回下一任务，但不保存它；State 也不会随运行自动前进。
- **写作结果仍是占位模板**：`TemplateWritingCapability` 主要把任务和输入拼成文本，尚不能代表真实创作质量。
- **Review 反馈过浅**：目前最有实质性的反馈是“缺少检索 Knowledge”，还不能发现人设、时间线、伏笔和因果问题。
- **检索依赖人工打标签**：无标签时直接返回空结果，不做语义兜底；标签体系增长后维护成本会快速上升。
- **知识回写偏文本解析**：Compiler 依赖 `Entity:`、`Fact:` 等行首格式，复杂结果、重复事实、冲突事实和版本合并尚未有稳定策略。
- **Research 只有接口，没有来源治理**：Provider 可以注入，但没有真实连接、引用、可信度、去重和验证流程。
- **无法承受长周期风险**：没有持久化、日志、恢复、并发控制、性能基准或大规模 Knowledge 压测。
- **叙事控制尚未进入使用链路**：当前无法回答“本章为什么存在、谁做了选择、代价是什么、读者认知如何变化”。

## 7. 建议的后续优先级

### P0：让 V1 成为可连续运行的系统

1. 为 Knowledge、Task、ProjectState 增加持久化适配层，业务模型保持内存实现可测试。
2. 将 Pipeline、Workflow、TaskStore、State 更新接通，确保 `next_task` 真正进入任务队列。
3. 增加运行日志、错误恢复、幂等编译和最小审计记录。
4. 建立 100 章 / 1000 Task / 10000 Knowledge 的自动压力测试和 Benchmark。

### P1：提高创作反馈质量

1. 先把 Review 拆成可解释规则：人物状态、时间线、世界规则、伏笔、章节功能重复。
2. 给 Retriever 增加可观测指标和评测集，再考虑语义检索；不要直接用全文扫描兜底。
3. 将 Compiler 的结构化输入从行首文本升级为明确的数据契约，并处理冲突、重复和版本。

### P2：落地最新叙事控制设计

1. 先实现最小 `Narrative State` 和 `Chapter Contract`，以第 1 至 6 章回放为验收入口。
2. 再实现 Director 输出、人工审批和 `OutlineChange`，最后接入 Planner/Writer。
3. 叙事层只引用已确认 Knowledge，不把叙事意图写回通用 Foundation。

## 8. 验证记录与边界

- `python -m pytest -q`：33 passed。
- `python -m compileall -q creative_os`：通过。
- 冒烟调用确认：Pipeline 完成 Task 并生成 Summary；Review 生成 Issue/Fix Task；Research 编译为 `external + draft`。
- CodeGraph：31 files / 283 nodes / 742 edges，索引最新。
- 本报告未进行远程仓库提交或推送，也未改变已有用户修改。

