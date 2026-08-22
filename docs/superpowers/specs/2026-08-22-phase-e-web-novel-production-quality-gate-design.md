# Phase E：合同门禁下的逐章生产编排与网文质量 Gate 设计

**状态：** 待设计审核

**日期：** 2026-08-22

**项目：** Creative OS / 《文明升阶》

**依赖：** Narrative Director、Chapter Contract Approval、Versioned Authority Read Layer（Phase A–D）

## 1. 决策摘要

Phase E 首先建立 Reader Engagement Foundation，再新增项目级、单实例语义的 `ChapterProductionOrchestrator`，把既有 Director、合同审批、Lifecycle、Admission、Writer、Fulfillment 与 State 能力串成逐章、可暂停、可重启的生产闭环。Orchestrator 只协调权威组件，不拥有故事或 engagement 事实、不生成正文、不替代人工审批，也不建立第二事实源。

Phase E 引入两个项目级约束：

1. `ReaderEngagementPlan`：以 Book、Volume、Story Arc、Chapter 四层持续管理追读结构；opening 只是它的前十章 projection/profile。
2. `ProductionReadinessManifest`：证明已激活 engagement plan/ledger/curve，以及 Story Promise、主角成长、Information State、Narrative Thread 等权威来源齐备；缺项即暂停。

章节生产采用“自动硬门禁 + 人工质量判断”双轨：硬门禁验证合同、因果、状态和安全不变量；人工评分判断追读欲、兑现感与阅读体验。任何软评分都不能覆盖硬阻断。

## 2. 当前基线与问题

| 现状 | 已有能力 | Phase E 缺口 |
|---|---|---|
| Director / Contract | v2 合同、Preflight、审批、Reviewer、Lifecycle、版本切换 | 没有从项目准备度到下一章 Baseline 的纵向编排 |
| Admission / Writer | 两阶段准入、真实 Context fingerprint、run/token 绑定、版本化出口清单 | 正式 CLI 仍保留直接调用 Writer 的旧入口形态 |
| Fulfillment | 追加式 verification/realization Store、严格重读与求值 | 未接入章节生产成功判定 |
| State | 章节后可产生 Memory/State candidates；ACTIVE 状态可物化 | candidate 未进入人工审批、激活、物化和下一章 Baseline 闭环 |
| 项目 brief | 存在 `projects/文明升阶/brief.json` | `genre`、`logline` 为空；metadata.genre 为空；state 仍为“完善新书 brief” |
| 批量生产 | 旧脚本支持 chapter list、resume、force 等参数 | 没有逐章权威检查点；不能证明十章是十次完整闭环 |

因此，《文明升阶》在 Phase E 初次运行时必须停在 `AWAITING_READINESS_APPROVAL`。Writer 不得用 prompt 临时补写缺失的定位、承诺或主线。

## 3. 目标、边界与不变量

### 3.1 交付顺序

依赖顺序固定为：

1. **Phase E-A Reader Engagement Foundation**：权威 Plan、Expectation Ledger、Curve、Review 与人工 transition。
2. **Phase E-B Production Readiness**：exact 绑定已激活 engagement 权威状态和故事基础。
3. **Phase E-C Chapter Production**：单一 Orchestrator、质量 Gate、Fake Writer 十章闭环。
4. **Phase E-D Real Calibration**：离线全绿后做真实 7–8 章校准，再扩展 9–16 章。

后序阶段不得用 fixture、调用方临时对象或 Writer 临时规划代替前序权威对象。

### 3.2 目标

- 每次只推进一个章节的一个合法状态转换。
- 每个外部副作用前锁内 exact 重读权威状态，副作用后追加不可变回执。
- 人工审批可跨进程、跨重启暂停与恢复。
- 同一命令、同一 run 重放幂等，不重复调用模型、不重复发布、不重复写证据或状态。
- 分别输出工程可生产、网文结构合格、人工阅读质量三项结论。

### 3.3 非目标

- 不做 UI、多 Agent、Style Reference、通用知识平台、通用历史库或第二事实源。
- 不让 Orchestrator 自动批准合同、质量或 State candidate。
- 不修改 Writer 以绕过现有 Admission，不新增独立生产出口。
- 不把番茄男频经验机械化成固定情节模板。
- 不在本阶段重构无关模块。
- 不在本阶段接入真实 Reader Feedback、平台 Performance 数据或基于数据的自动 Revision；原因是生产前验证尚无已发布读者样本，提前引入会制造伪权威和额外平台边界。

### 3.4 强制不变量

1. 缺少 engagement、readiness、合同、审批、Reviewer、disposition、Context、Fulfillment 或 State 权威证明时 fail-closed。
2. Orchestrator 的检查点只记录引用、hash、状态与回执，不复制正文或故事事实。
3. 人工审批记录必须绑定被审对象 hash、规则版本和上一权威状态 hash。
4. Writer 只能接收最终 Admission token；grant 不进入生产出口。
5. 模型调用不持有项目锁；调用前写 prepared intent，调用后以同一 idempotency key 对账。
6. 最终章工件、Fulfillment、State 物化和下一章 Baseline 必须按顺序完成，不能跳步。
7. Writer 不规划 engagement、不直接修改 Expectation Ledger；Orchestrator 也不拥有这些事实。

## 4. 总体架构

```text
Story Core
    ▼
Book Engagement → Volume/Arc Engagement
    ▼
Expectation Ledger + Engagement Curve
    │ exact read
    ▼
E-B Readiness
    │
    └────────────┐
                 ▼
      ChapterProductionOrchestrator
        │       │       │       │
        ▼       ▼       ▼       ▼
     Director Lifecycle Admission Writer exits
        │       │       │       │
        └───────┴───────┴───────┘
                         ▼
               Hard Gate + Human Review
                         ▼
                   Fulfillment Store
                         ▼
              State approval/materialize
                         ▼
                Next Baseline binding
```

Orchestrator 依赖窄接口，不直接访问内部文件布局：

- `ReadinessAuthorityReader`
- `EngagementAuthorityReader`
- `NarrativeDirector`
- `ContractLifecycleCoordinator`
- `WriterAdmissionService`
- 现有版本化 Writer 出口
- `WebNovelQualityGate`
- `ContractFulfillmentStore` / `ContractFulfillmentEvaluator`
- `StateCandidateReviewer` / 现有 Memory 与 State materializer
- `ChapterRunCheckpointStore`

## 5. E-A：Reader Engagement Foundation

### 5.1 四层 Engagement

`ReaderEngagementPlan` 是长期权威模型，由稳定的 Planning Skill/Service 依据 Story Core 生成 candidate，经人工审批后激活。它不由 Writer 或 Director 临时构造，也不需要新增独立大 Agent。

四层职责如下：

| 层级 | 职责 |
|---|---|
| Book Engagement | 核心卖点、长期承诺、核心追读问题、主角幻想、全书级回报边界 |
| Volume Engagement | 卷级承诺、阶段问题、卷内回报窗口；项目暂无卷结构时必须显式 `N/A` 并给理由，不得 `UNKNOWN` |
| Story Arc Engagement | Arc 的期待、升级、转折、payoff 与退出条件 |
| Chapter Engagement | 从激活的上层 plan/ledger/curve 投影本章建立、推进、兑现或克制义务 |

`OpeningEngagementProfile` 是 Book/Volume/Arc plan 面向前十章的 opening projection，不是独立的唯一长期模型。原 `OpeningRetentionContract` 语义迁移到该 profile；十章后四层模型继续运行。

### 5.2 最小权威对象

`EngagementPlan` 至少包含 `project_id/version/scope/scope_id`、四层目标、opening profile、来源绑定、规则版本、状态和 `content_hash`。只有 APPROVED/ACTIVE 版本可被 readiness 与 Director 使用。

`ExpectationRecord` 是 Ledger 中不可变、追加演进的期待记录：

- `expectation_id`、`state`：`OPEN|ESCALATING|PAID|ABANDONED`；
- `created_chapter`、`expected_payoff_window`、`importance`；
- `related_arc_ids`、`related_character_ids`；
- `source/evidence` 的 exact ID/version/hash；
- `transition_history`：previous state/hash、candidate/evidence、人工 decision、reason、timestamp。

`ExpectationLedger` 保存记录集合的版本、head/hash 与 plan binding。状态转换只允许 `OPEN→ESCALATING|PAID|ABANDONED`、`ESCALATING→ESCALATING|PAID|ABANDONED`；PAID/ABANDONED 为终态。重复 transition 必须幂等，同 ID 异内容冲突。`ABANDONED` 必须有人工批准及非空理由；UNKNOWN 不能自动回收。

Expectation 与 Foreshadow 严格分离：Expectation 表示读者被建立的期待及回报义务，Foreshadow 表示故事内线索。二者可以用 ID 关联，但不能互相替代、共享状态机或因伏笔关闭而自动判定期待 PAID。

`EngagementCurve` 用小枚举 `LOW|MEDIUM|HIGH|PEAK` 描述跨章张弛目标，并绑定 plan ID/version/hash。规则允许低谷和恢复章，但阻断长时间 LOW、无因果升级的连续 PEAK，以及与 Arc/Expectation 状态不一致的强度。它不机械要求每章高潮。

`EngagementReview` 是写后“规划兑现/读者追读结构 Review”，绑定 plan、ledger head、curve、Chapter Contract、Context、artifact 和 ruleset hash。它独立于正文文学质量人工 Review、Contract Fulfillment 和普通一致性 Review，检查：

- 本章承诺的 expectation 是否建立/推进/兑现；
- 旧期待是否超出 payoff window；
- 是否只开新坑、不回收旧期待；
- payoff 频率与重要性是否合理；
- hook 是否由本章因果结果产生；
- 情绪曲线是否重复、长期低刺激或连续峰值疲劳。

### 5.3 长期数据流与边界

```text
Story Core
  → Book Engagement
  → Volume / Story Arc Engagement
  → Expectation Ledger + Engagement Curve
  → Chapter Engagement projection / Chapter Contract
  → Context → Writer
  → Engagement Review + Fulfillment
  → expectation transition candidates
  → exact evidence + human approval
  → Expectation Ledger
  → next Chapter / Arc
```

Planning Skill/Service 只生成 plan candidate；人工审批负责激活。Narrative Director 只能消费 ACTIVE plan、exact Ledger head 和 Curve projection 来生成 Chapter Contract，不得发明新的长期期待。写后 Compiler/State candidate 链可产生 `established/escalated/paid/abandoned` candidate，但必须绑定 exact artifact evidence、经人工审批后才物化到 Ledger；Writer 和 Orchestrator 均无直接写 Ledger 权限。

## 6. E-B：生产准备度审计

### 6.1 最小权威数据

`ProductionReadinessManifest` 为不可变、版本化项目记录，仅保存以下 role 的精确绑定：

```text
role, source_id, source_version, content_hash
```

必需 role：

- `commercial_positioning`
- `story_promise`
- `protagonist_growth`
- `information_state`
- `narrative_thread`
- `active_engagement_plan`
- `expectation_ledger_head`
- `engagement_curve`

Resolver 仅通过显式 role→权威 adapter exact 重读。来源不能按 version/hash 读取时返回 `source_not_versioned`；不得回退到 latest、按路径猜测或把调用方对象当权威事实。

### 6.2 审计结果

`ProductionReadinessAuditResult` 包含 manifest hash、逐 role 校验结果、规则版本、issues 和 `READY|BLOCKED`。结果追加保存；人工批准记录绑定整个 audit hash。任何缺失、空核心字段、漂移、未知 role、重复 role 或解析异常都进入 `AWAITING_READINESS_APPROVAL`，且不创建章节 run。

Readiness 必须 exact 绑定 ACTIVE plan 的 ID/version/hash、Ledger head/hash 和 Curve ID/version/hash；三者任一 stale、互不匹配或缺失都阻断。《文明升阶》现有空 `genre`/`logline` 仍是确定性阻断项。Phase E 不自动填充它们。

## 7. Opening Engagement Projection

### 7.1 权威模型

`OpeningEngagementProfile` 是激活 `EngagementPlan` 的不可变 opening projection，字段保持最小：

- `project_id`
- `plan_id/plan_version/plan_hash`
- `core_hook`：核心卖点
- `long_term_promise`：长期承诺
- `core_retention_question`：核心追读问题
- `protagonist_fantasy`：主角幻想与读者代偿
- `first_return_deadlines`：承诺的首轮回报窗口
- `checkpoint_obligations`：1/3/6/10 章语义义务
- `projection_hash`

它不保存章节正文，不取代 Book/Volume/Arc Engagement 或 Chapter Contract。变更必须通过新 Plan 版本和人工批准，并使引用旧 plan/projection hash 的未执行 Chapter run 失效。

### 7.2 前十章约束

- 第 1 章：展示高概念差异与可感知威胁。
- 第 3 章前：主角完成有代价的主动选择。
- 第 3/6/10 章：分别完成微型、中型、阶段性 payoff。
- 连续两章不得只有新增谜团而无推进或兑现。
- 第 10 章回答“长期为什么值得看”，并开启更大的、因果相连的问题。
- 第 1/3/6/10 章必须有人工作出“是否想继续读、期待什么、原因是什么”的判断。

这些是语义义务，不规定固定桥段、字数比例或爽点位置。自动系统只能验证可结构化的事实与证据；“是否好看”保留给人工。

这些约束也是 Fake Writer 十章验收用例；不是十章后的模型终点。第 11 章起继续由 Book/Volume/Arc/Chapter 四层 plan、Ledger 和 Curve 产生义务。

### 7.3 与现有合同的关系

- ACTIVE Engagement Plan/Ledger/Curve 产生本章 `engagement_obligations` 引用，Director 必须在 Chapter Contract 中声明本章如何建立、推进或兑现。
- Preflight 检查义务是否被合同覆盖；Reviewer 检查其合理性和因果一致性。
- Context 只注入冻结 Chapter Contract projection 与 engagement 引用摘要，不复制整份项目 plan 或 Ledger。
- 写后 Hard Gate 检查声明的动作是否有证据；Fulfillment 记录实际实现。
- Opening checkpoint 的 Engagement Review 独立于合同审批、文学质量 Review 和 Fulfillment，适用检查点必须全部通过才可提交。

## 8. E-C：逐章 Orchestrator 与检查点

### 8.1 API

```python
start(project_id, chapter_number) -> OrchestrationView
advance(run_id) -> OrchestrationView
resume(run_id) -> OrchestrationView
inspect(run_id) -> OrchestrationView
```

`advance` 每次至多跨越一个外部副作用边界，遇到人工决策立即返回暂停态。调用方不能传入 `PreparedWriterRun`、Baseline 事实对象或审批对象；它们必须由 Orchestrator 在锁内从权威记录重建。

### 8.2 状态机

```text
ENGAGEMENT_AUTHORITY_CHECK
  → AWAITING_ENGAGEMENT_APPROVAL
  → READINESS_CHECK
  → AWAITING_READINESS_APPROVAL
  → BASELINE_BOUND
  → DIRECTOR_CANDIDATE_RECORDED
  → AWAITING_CONTRACT_APPROVAL
  → CONTRACT_ACTIVE
  → PRE_ADMITTED
  → CONTEXT_COMPILED
  → ADMITTED
  → WRITER_PREPARED
  → WRITER_COMPLETED
  → ENGAGEMENT_REVIEWED
  → HARD_GATE_PASSED
  → AWAITING_QUALITY_REVIEW
  → QUALITY_APPROVED
  → FULFILLMENT_RECORDED
  → AWAITING_EXPECTATION_TRANSITION_APPROVAL
  → EXPECTATION_LEDGER_UPDATED
  → AWAITING_STATE_APPROVAL
  → STATE_MATERIALIZED
  → NEXT_BASELINE_COMMITTED
  → CHAPTER_COMMITTED
```

阻断态包括 `ENGAGEMENT_STALE`、`READINESS_BLOCKED`、`AUTHORITY_DRIFTED`、`ENGAGEMENT_REVIEW_BLOCKED`、`HARD_GATE_BLOCKED`、`FULFILLMENT_INCOMPLETE`、`STATE_REJECTED` 和 `AMBIGUOUS_EXTERNAL_RESULT`。阻断态只能通过新增权威记录或显式重试转换，不能原地改写历史检查点。

### 8.3 追加式检查点

`ChapterRunCheckpoint` 最小字段：

- `run_id/project_id/chapter_number`
- `sequence/previous_hash/checkpoint_hash`
- `state/ruleset_version`
- `authority_state_hash`
- `input_refs` 与 `output_refs`（ID、version、hash）
- `idempotency_key`
- `pause_reason/error_code`
- `created_at`

`ChapterRunCheckpointStore` 复用现有权威 Store 的 canonical JSON、链式 hash、head、journal、no-follow I/O、file/dir fsync、跨进程项目锁与恢复模式。它不是故事事实源；删除、截断、重排、重复 key、非 canonical 编码或 head 不一致必须拒绝重启。

### 8.4 分阶段 hash 绑定

避免一个不可维护的巨型循环 hash。每个阶段计算 `authority_state_hash`，至少绑定：

- Engagement Plan ID/version/hash、opening/chapter projection hash、Ledger head/hash、Curve ID/version/hash，以及 readiness audit/approval；
- 当前合同 pointer、Baseline、审批、Reviewer、ruleset/语义资产、dispositions 和 activation binding；
- Admission authority state、Context fingerprint、run_id；
- Writer execution receipt、工件 hash；
- Hard Gate 规则/结果、人工质量评审；
- Engagement Review 与每个 expectation transition candidate/decision/evidence hash；
- Fulfillment Store head 与 active record IDs；
- State candidate、审批、物化 snapshot；
- 下一章 Baseline manifest/fingerprint；
- 上一检查点 hash。

任何上游 hash 改变都使未完成的下游检查点 stale；已发布历史不被静默重算。

## 9. 人工暂停与恢复

人工操作只追加领域记录：Engagement Plan approval、readiness approval、合同 approval/reviewer/disposition、Engagement Review、文学质量 Review、expectation transition decision、state candidate decision。CLI 或人工工具不得直接修改 Orchestrator state。

恢复流程：

1. 获取项目级 authority lock。
2. 严格重读 checkpoint chain/head/journal。
3. 按当前 state exact 重读全部关联权威记录。
4. 重算 authority state hash 与适用 Gate。
5. 若人工记录仍缺失，返回同一暂停态；若漂移，追加 `AUTHORITY_DRIFTED`。
6. 仅在前置条件完全一致时追加下一 checkpoint。

等待不是错误；轮询和重复 `resume` 必须零副作用。

## 10. 番茄男频质量 Gate

### 10.1 自动硬门禁

`WebNovelHardGateResult` 保存规则版本、contract/artifact/context hash、逐规则 verdict/evidence 和总状态。硬规则包括：

- 主角有主动选择且存在可识别代价；
- 本章推进主线或声明的 Arc；
- 冲突发生升级、转向或有意义的结算；
- 期待被建立、推进或兑现，且符合 Ledger payoff window 与 Engagement Curve；
- 人物、关系、信息或世界状态发生可审计变化；
- 章末存在与因果链相关的追读钩子；
- 与 Baseline、冻结合同、已物化 State 一致；
- 阻断拖沓堆砌、主角旁观、突兀爽点和重复叙事功能。

无法由确定性结构/证据判断时返回 `UNKNOWN/BLOCKING`，不能用关键词命中冒充通过。语义重复沿用已版本化 `function_semantics` 资产。

### 10.2 人工文学质量 Gate

`HumanReadingQualityReview` 最小字段：

- reviewer、artifact hash、ruleset version；
- `continue_reading_desire`、`promise_clarity`、`payoff_satisfaction`、`pacing`、`surprise_fairness`、`male_frequency_fit`；
- 每项简短理由、总 disposition、签名/记录 hash。

第 1/3/6/10 章另需 opening `EngagementReview`：追读欲、当前期待、已兑现内容、未兑现原因、下一期待。Engagement Review 评价规划兑现结构；`HumanReadingQualityReview` 评价成文阅读体验，二者不得合并。人工评审可以要求修订，但不能把 Hard Gate 的 BLOCKED 改成 PASS。

### 10.3 工件生命周期与延期边界

Writer 输出先进入受 Admission 保护的 staged artifact，并生成 execution receipt；Hard/Soft Gate 完成后才通过现有受保护 promotion/final sink 发布。失败版本保留 hash 引用用于审计，不覆盖已发布 final。修订必须创建新 run/attempt，并重新绑定 Context、token 和工件 hash。

本阶段只实现与 staging/final 相关的 Published/Draft boundary。真实 Reader Feedback、平台 Performance 指标和基于反馈的 Revision Boundary 延后：它们依赖发布后的真实样本、平台身份和采集治理，不能成为当前生产前验证的伪造输入或阻断条件。

## 11. Fulfillment、Expectation 与 State 闭环

### 11.1 Fulfillment

Quality 通过后，Reviewer 只向 `ContractFulfillmentStore` 追加 verification/realization 记录。Evaluator 必须基于冻结合同全部权威叶、真实 final artifact metadata 和 exact validator 求值；`STALE` 或 `INCOMPLETE` 均不得进入 State 物化。

### 11.2 Expectation transition

写后 Compiler 从 final artifact、Engagement Review 与 Fulfillment 生成 `ESTABLISHED|ESCALATED|PAID|ABANDONED` candidates。candidate 必须指出目标 expectation、from/to state、chapter、plan/ledger/contract/artifact hash 和 exact evidence。Ledger owner 在人工批准后执行 compare-and-append：旧 head、旧 state 或 payoff window 不匹配即 stale；同 transition 重放幂等，异内容冲突；不存在的期待不得被越权 PAID；ABANDONED 没有人工理由必拒绝。

### 11.3 State 审批与物化

现有 `save_chapter_candidates`/`build_state_changes` 只能产生 candidate。Phase E 增加窄接口 `StateCandidateReviewer` 与追加式 `StateChangeDecisionRecord`，绑定：

- candidate ID/content hash；
- final artifact hash；
- contract ID/version/hash；
- fulfillment evaluation hash；
- reviewer/disposition。

只有 APPROVED candidate 可由现有 Memory/State owner 激活并物化。通用解析或“待人工补充”内容不得自动成为 ACTIVE 事实。物化后 exact 重读 snapshot，生成下一章 BaselineManifest；只有新 Baseline fingerprint 持久化成功，本章才进入 `CHAPTER_COMMITTED`。

## 12. 崩溃恢复、TOCTOU 与安全

- 所有状态转换在统一项目 authority lock 内完成“重读—验证—追加”。不得嵌套不兼容锁。
- 模型调用前追加 `WRITER_PREPARED`，包含不可变请求 hash 与 idempotency key，然后释放锁。
- 模型调用后重新加锁并对账 execution receipt。若远端结果未知，进入 `AMBIGUOUS_EXTERNAL_RESULT`，禁止盲目重调。
- Admission token 必须绑定 project/chapter/contract/projection/context/run/authority state，并在 handoff 前重读验证。
- staged/final 写入、模型调用、promotion/publish 继续受版本化出口清单和 AST Gate 覆盖。
- 所有路径使用可信根与 no-follow I/O；项目 basename 不能充当项目身份。
- checkpoint、人工记录与回执均严格 canonical、exact schema、SHA-256、domain separation。
- 恢复优先观察真实外部状态，再幂等补齐缺失 checkpoint；不得用 checkpoint 声称替代真实工件或权威 Store。
- Engagement transition 采用 prepared→decision observed→Ledger CAS→committed journal；崩溃恢复必须重读真实 Ledger head，绝不重复追加或把 UNKNOWN 推断成 PAID。

## 13. E-C：Fake Writer 十章纵向验收

Fake Writer 是受控 adapter，只返回可验证的不同章节测试工件与 metadata，不包含真实小说正文，也不绕过 Admission。测试必须由同一 Orchestrator 基于当章最新 Ledger/Curve 逐章构建真实 Context 和 Prepared run，不能预制十份 `PreparedWriterRun`，也不能一次性预计算十章 engagement plan/projection。

每章结束后关闭并重开 Engagement Plan/Ledger/Curve、checkpoint、合同、pointer、五类合同权威记录、Fulfillment、Memory/State Store 与 Admission service，再从磁盘恢复：

| 章 | 重点场景 |
|---|---|
| 1 | plan/readiness 人工等待；高概念与威胁；建立 expectation；opening review |
| 2 | 合同审批等待与重复 resume 幂等 |
| 3 | 主动选择、代价、微型 payoff；transition 审批与 opening review |
| 4 | Context 后崩溃恢复，不重复编译或调用 |
| 5 | Writer 回执部分失败与 ambiguous outcome 隔离 |
| 6 | 中型 payoff；Ledger/Curve/Fulfillment 闭环；人工 review |
| 7 | Plan/Ledger/Curve 或 Baseline 漂移阻断并重建新 run |
| 8 | Fulfillment supersede、重复 expectation transition 与重启 |
| 9 | State 审批等待、物化中断恢复、下一 Baseline |
| 10 | 阶段 payoff、回答长期看点、开启更大问题；opening projection 最终 review |

每章还需证明：审批缺失零 Writer 副作用、旧 token 失效、重复命令不重复写、State 未批不进入 Baseline、上一章未 committed 时下一章不能开始。

## 14. E-D：真实验证

真实模型与人工验证必须在全部离线 Gate 通过后显式暂停等待授权：

1. 先以第 7–8 章做少量校准，逐章人工合同审批与阅读评审。
2. 校准结论通过后，再逐章扩展至第 9–16 章。
3. 任一章失败只修订该章合同/run，不自动批量继续。

真实验证不允许 `force` 跳过 Gate，不把人工审批变成模型自评，也不自动生成后续正文。每章分别报告：工程闭环、结构 Gate、人工阅读质量。

## 15. 正式 CLI 与兼容迁移

正式入口统一为 Orchestrator：

```text
creative-os novel readiness --project-root PATH
creative-os novel engagement status --project-root PATH
creative-os novel start --project-root PATH --chapter N
creative-os novel advance --project-root PATH --run-id ID
creative-os novel resume --project-root PATH --run-id ID
creative-os novel status --project-root PATH --run-id ID
```

审批仍由相应领域命令写入权威 Store；`advance/resume` 只观察并继续。

旧接口迁移：

- `continue_novel.py` 和 `run_llm_writer_pilot.py` 变为薄兼容层，只调用 Orchestrator。
- `--target-chinese-chars` 不再临时覆盖合同；需要变更时走合同 revision。
- `--max-attempts` 只能映射为已版本化运行策略，不能绕过质量 Gate。
- `--promote-draft` 不直接晋升，只恢复到相应 Gate。
- `--chapters` 可展开成顺序请求，但必须逐章 committed；不能预建后续 Context。
- `--resume` 映射 checkpoint resume；`--force` 被拒绝；`--local-repair` 只能作为受合同和 Admission 约束的新 attempt。
- 兼容层输出弃用警告和 run_id；不保留直达 Writer 的后门。

历史已完成章节不被自动追认或重写。它们可进入只读审计；若要继续生产，必须先人工建立并激活 Engagement Plan、导入有证据的 Ledger 初始状态、建立 readiness 与当前 Baseline。迁移不得从旧正文自动推断 PAID/ABANDONED，也不得一次生成未来十章 projection。

## 16. 错误分类

| 错误 | 行为 |
|---|---|
| Plan/Ledger/Curve 缺失、unknown 或 stale | 暂停，等待人工/权威修订 |
| Volume 层缺失 | 仅显式 N/A+理由可通过；unknown 阻断 |
| expectation transition 重复/越权 | 同内容幂等；异内容、非法 from/to 或无证据 payoff 拒绝 |
| ABANDONED 无人工理由 | 拒绝物化 Ledger |
| 合同审批、Reviewer、disposition 缺失 | 暂停，不创建 Admission |
| authority/source drift | 追加 drift checkpoint，旧 run 不再推进 |
| pending revision | 阻断 pre-admit/finalize/validate |
| Writer outcome ambiguous | 隔离并人工对账，不自动重试 |
| Hard Gate UNKNOWN/BLOCKED | 不晋升、不写 realization |
| 人工质量未批准 | 保留 staged artifact，暂停 |
| Fulfillment incomplete/stale | 不产生 State 权威事实 |
| State rejected/pending | 不物化、不生成下一 Baseline |
| checkpoint/store 篡改 | 启动失败并要求人工恢复，不 fail-open |

领域错误使用稳定 code，保留可审计 details，但不泄露密钥、token 或正文。

## 17. 模块拆分

| 模块 | 单一职责 |
|---|---|
| `reader_engagement_model.py` | 四层 Plan、opening/chapter projection、Expectation、Curve 的严格模型 |
| `reader_engagement_store.py` | Plan/Ledger/Curve 追加式权威持久化与 exact 重读 |
| `reader_engagement_planning.py` | 稳定 Planning Service 生成 candidate，不审批 |
| `engagement_review.py` | 写后追读结构 Review 与 transition candidate compiler |
| `production_readiness.py` | readiness 模型、审计与 exact reader 组合 |
| `chapter_production_orchestrator.py` | 状态转换协调，不持有领域事实 |
| `chapter_run_checkpoint_store.py` | 追加式 checkpoint、journal、恢复 |
| `web_novel_quality.py` | 硬 Gate 与人工评审模型/策略 |
| `state_change_approval.py` | State candidate 决策与物化授权 |
| `novel_production_cli.py` | Orchestrator 命令适配 |

现有 Director、Lifecycle、Admission、Writer exits、Fulfillment、Memory/State Store 保持各自 owner。若单个新模块开始承担持久化、策略和编排三类职责，必须继续拆分，不能形成超大文件。

## 18. 验收矩阵

### 18.1 离线 Gate

- E-A 四层 Plan strict round-trip；Volume 明确 N/A+理由可用，unknown 阻断；未批准 Plan 不可投影。
- Expectation 状态机、transition history、Foreshadow 分离、exact evidence、人工审批、Ledger CAS/restart/tamper。
- 不存在或不适用 expectation 的 payoff 越权、重复异内容 transition、ABANDONED 无人工理由均阻断。
- Engagement Curve 允许合理 LOW，阻断长时间 LOW、无因果连续 PEAK；规则精确绑定 plan/version/hash。
- Engagement Review 与文学质量 Review、Fulfillment、一致性 Review 的记录和 verdict 不可互相替代。
- Readiness 每个 role exact success；Plan/Ledger/Curve stale、缺失、空值、未知/重复 role、不可版本化均阻断。
- Opening projection/hash/人工批准、1/3/6/10 义务和连续两章 mystery-only 负测；十章后四层仍能继续投影。
- Director 在无 ACTIVE projection 时阻断，且不能新增长期 expectation；Writer/Orchestrator 无 Ledger 写权限。
- 状态机每条合法/非法转换、人工暂停、重复 resume、并发 advance。
- 每个外部副作用的 no token、旧 token、错误 context/run/authority hash 零副作用。
- prepared/receipt/journal 各故障点恢复；ambiguous model result 不重调。
- Hard/Soft Gate 分离；soft approval 不能覆盖 hard block。
- Fulfillment exact 闭环、stale/supersede；未闭环不进入 State。
- State pending/rejected 不物化；批准后重启物化并生成 exact 下一 Baseline。
- 十个不同章节逐章关闭重开全 Store；无十份预制 Prepared run，也无一次性十章 engagement 预计算。
- CLI/AST 确认正式与兼容入口均不直达 Writer/promotion/final sink。
- 篡改、删尾、重排、CRLF、重复 JSON key、symlink/reparse、跨进程竞争 fail-closed。

### 18.2 真实 Gate

- 第 7–8 章逐章校准后才允许 9–16 章。
- 每章真实合同由人工批准，真实 Context fingerprint 与 run/token 绑定。
- 模型调用、staged artifact、Engagement Review、文学质量、Fulfillment、Expectation/State、下一 Baseline 完整留痕。
- 1/3/6/10 的历史 checkpoint review 可重读；扩展章节继续验证长期承诺兑现。

### 18.3 三项独立结论

最终报告不得合并成单一 PASS：

1. **工程可生产：** 权威链、恢复、幂等、安全和出口均通过。
2. **结构符合网文：** Engagement Plan/Ledger/Curve、Engagement Review、自动硬 Gate 与 opening 义务通过。
3. **人工阅读质量：** 指定 reviewer 明确给出追读欲、期待、兑现与原因。

任一项未通过，整体不得宣称可扩大生产。

## 19. 文档与运维更新

实施时需同步更新：

- 项目 brief/schema 与 readiness 填写说明；
- Narrative Director/Chapter Contract 文档中的 Engagement projection 引用；
- Engagement Plan/Ledger/Curve 状态、人工 transition 与 Foreshadow 分离说明；
- CLI 参考与旧参数迁移表；
- Orchestrator 状态机、错误码和人工审批操作手册；
- 权威 Store/备份/灾难恢复说明；
- Writer 出口 JSON 清单与 AST 架构测试说明；
- 《文明升阶》仅保存人工批准后的 Engagement 与 readiness 权威数据，不在文档中生成正文。

## 20. 设计自审

- **依赖顺序：** E-A Engagement → E-B Readiness → E-C Orchestrator/Fake 十章 → E-D 真实校准，不允许反转或 fixture 替代。
- **范围：** 仅 Phase E Engagement Foundation、纵向编排、前十章 opening projection 与质量 Gate；未引入 UI、多 Agent、Style Reference、第二事实源或通用平台。
- **事实所有权：** Orchestrator/checkpoint 只保存绑定和回执；故事事实与 engagement 事实仍由各自权威 owner 管理。
- **人工边界：** readiness、合同、质量与 State 决策均不可自动批准。
- **安全：** 每个副作用都有锁内 exact 重读、idempotency key、回执与恢复策略；模型调用不持锁。
- **可测试性：** 每个状态、错误、hash 漂移、I/O 故障和人工暂停均有确定性测试接口；Fake Writer 不需正文或模型。
- **序列化边界：** 当前只纳入 staging/final 发布边界；真实反馈、Performance 和反馈驱动 Revision 明确延后且不阻断生产前验证。
- **现状一致性：** 明确处理旧 CLI、纵向编排缺失、Fulfillment 未接线、Expectation/State candidate 未审批物化，以及《文明升阶》brief 空字段。
- **开放项：** 无需要改变已批准目标的开放架构决策。具体字段命名与错误码可在实施计划中细化，但不得削弱本文不变量。
