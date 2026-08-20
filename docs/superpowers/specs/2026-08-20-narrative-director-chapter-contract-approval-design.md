# Narrative Director + Chapter Contract Approval 设计

## 1. 文档状态与范围

- 状态：复审修订稿，待人工复审。
- 基线：`codex/legacy-novel-continuation`，提交 `a683446`。
- 本文只设计架构、模型、门禁、迁移和验收，不实现代码、不生成正文、不包含实施计划。
- 上一阶段结论为 `CONDITIONAL PASS`；本文第 14 节是下一阶段强制验收条件，不得降级为建议。

## 2. 目标与非目标

目标是让唯一的 Narrative Director 产出唯一的 Chapter Contract 候选，并在 Writer 获准前完成字段完整性、逐字段证据和人工审批闭环。系统必须清楚区分“计划意图”“审阅判断”“正文已实现事实”，且合同冻结后的任何变更都必须形成可审计修订。

非目标：

- 不新增平行 Director、平行 ChapterContract 或独立事实库。
- 不让回放投影替代正式合同，不让 Narrative State 覆盖 Knowledge/Novel State。
- 不在本阶段引入外部模型、向量相似度服务、图数据库或前端。
- 不自动批准合同、重大选择、信息策略、伏笔处置、新事实或改纲。
- 不把旧章节回放标注自动升级为未来写作合同。

## 3. 现状审计

### 3.1 已有可复用基座

| 现有模块 | 当前职责 | 本设计处理 |
|---|---|---|
| `narrative_decision.py` | `NarrativeDecision`、`ChapterContract`、选择、信息和压力模型 | 原位演进为 schema v2，保持唯一正式合同 |
| `narrative_director.py` | 校验 Director 输入和候选决策 | 扩展为候选生成边界；不创建第二 Director |
| `narrative_memory.py` | 将 Profile、Decision、ChangeRequest 保存为 `PROJECT_DECISION` | 继续作为唯一持久化入口 |
| `memory/model.py`、`approval.py`、`store.py` | candidate/active/rejected/archived、人工 actor、版本和审计 | 复用存储与人工激活；补充合同专用审批语义 |
| `narrative_replay*` | 从正文和生产产物生成只读审计投影 | 保持只读，升级字段级证据与选择完整度 |
| `narrative_review.py` | 可解释的合同/正文检查 | 拆分精确 Issue，并提供准入所需 Review 结果 |
| `narrative_progression.py` | 比较阶段、选择、压力、功能、伏笔动作 | 扩展为本地语义归一规则，不接外部模型 |
| `ContextCompiler` | 只编译活动 Memory 和可追溯来源 | Writer 仅接收冻结合同的有界投影 |

### 3.2 已发现缺口

1. 正式 `ChapterContract` 没有 `chapter_id`，合同身份依赖外层 `NarrativeDecision.chapter`。
2. `EvidenceRef` 只有来源类型、路径、摘录，缺少字段路径与证据角色；回放把整章证据集合复用给每个 Issue。
3. 回放人物选择是 `ProtagonistChoice | None`，无法表达 `partial`，也无法指出缺少 `alternatives/cost/consequence` 中哪一项。
4. `MemoryStatus.ACTIVE` 同时承担“已批准”和“可消费”，无法显式表达合同已冻结、修订待批和已取代。
5. `save_revision()` 能把活动项改回 candidate，但没有合同冻结后的修订原因、影响分析、审批项快照和旧版本绑定协议。
6. `review_replayed_contract()` 只区分缺选择与缺代价；人物选择部分存在时可能被误判为完整。
7. `repeated_chapter_function` 只做字面集合交集，无法识别同义功能，也无法区分“重复”与“升级/兑现”。
8. 当前生产主流程没有统一 Writer 准入服务；仅靠模型 `validate()` 不能证明人工审批、证据闭环或因果 unknown 已清零。

### 3.3 第 1–6 章回放审计含义

现有主报告共 12 个 Issue、36 个 unknown。其问题不是“正文没有选择”，而是“结构化回放不能以字段级闭环证明选择”。正文核对显示：

- 第 5 章有明确选择候选：许砚保存缺页证据且暂缓上报；可建立 `partial/complete` 标注，但仍须逐项确认备选方案、代价和后果。
- 第 2–4 章存在部分候选：如许砚私存监控、林澈接受交易、许砚不上报并放行；它们不能继续被压扁成单一 `missing`。
- 现有报告为 Issue 附带整章通用证据，不能证明具体缺失字段。
- Task 的 goal/outcome 是计划或生产意图，不是正文已完成事实；正文开头摘录也不能证明结尾变化。

## 4. 方案比较与决策

### 方案 A（推荐）：原位演进 + 合同专用审批投影

在现有 `NarrativeDecision/ChapterContract` 上升级 schema；继续保存为 `MemoryItem(PROJECT_DECISION)`。新增独立但无持久化主权的 `ContractApprovalRecord`、`ContractRevisionRequest` 和 `WriterAdmissionResult` 投影/记录，由合同服务统一校验生命周期。

优点：唯一事实源不变；迁移面可控；Memory 的人审、版本和审计继续复用；回放与正式合同边界清楚。缺点：需要在通用 Memory 状态之上定义更严格的合同状态推导。

### 方案 B：把所有审批状态直接塞进 `ChapterContract`

合同内容同时携带审批人、审批项和冻结状态。

优点：单文件读取直观。缺点：内容和流程元数据耦合；审批会改变被审批对象本身；签名/摘要容易循环依赖；会放大 schema 迁移风险。不选。

### 方案 C：独立 Chapter Contract Store 和审批引擎

为合同建立专用数据库、状态机和 API。

优点：流程表达最自由。缺点：形成第二事实源和第二审批系统，与现有 Memory 并行，违反本阶段首要约束。不选。

决策：采用方案 A。正式合同内容的唯一来源仍是活动且冻结的 Narrative Decision 版本；审批记录只证明“谁在何时批准了哪个不可变内容摘要”，不得承载合同字段真值。

## 5. 总体架构与组件边界

```text
Director -> PreflightValidator -> ApprovalPolicy -> LifecycleCoordinator
                                                    |
                                                    v
                                      frozen contract + approval record
                                                    |
                       PrewriteReviewerResult -> WriterAdmissionService
                                                    |
                                                    v
                                         admission token -> Writer
                                                    |
                                                    v
                         FulfillmentEvidenceStore -> FulfillmentEvaluator
```

Contract Service 是逻辑边界，不实现为大类，拆为五个小组件：

| 组件 | 单一职责 | 禁止 |
|---|---|---|
| `ContractPreflightValidator` | schema、字段、intent 证据和因果判定完整性 | 审批、持久化、调用 Writer |
| `ContractApprovalPolicy` | 计算必需审批项、覆盖路径和重新审批集合 | 修改合同、代替人工批准 |
| `ContractLifecycleCoordinator` | 候选、冻结、修订和 current pointer 的原子协调 | 解释正文、生成剧情 |
| `WriterAdmissionService` | 汇总冻结、基线、Reviewer、审批和因果门禁，签发 token | 直接生成正文 |
| `FulfillmentEvaluator` | 以冻结合同和外部成稿证据推导完成状态 | 修改冻结合同或审批 hash |

其他边界：Director 仍只有现有 `NarrativeDirector`；Memory Store 仍是正式合同持久化真源；Reviewer 只产出版本化结果；Compiler 只产事实候选。任何新增事实仍走既有人工审批。

生产入口只能接收 `WriterAdmissionService` 返回的 `AdmittedContractProjection` 和一次性/短期 `admission_token`。Writer、Planner 和生产编排器禁止调用 `load_active_narrative_decision()`；该读取函数只允许 LifecycleCoordinator 和 WriterAdmissionService 使用。通用 Memory 检索在编译 Writer Context 时必须按 `physical_key + contract_version` 排除 token 已携带的 NarrativeDecision，防止合同重复或不同业务版本同时注入。

## 6. 数据模型

### 6.1 NarrativeDecision v2：冻结内容只含写前意图

```yaml
schema_version: 2
kind: narrative_decision
contract_id: narrative-chapter-007
contract_version: 2
chapter: 7
profile_id: profile-id
volume_id: volume-1
arc_id: arc-1
arc_phase: escalation
arc_goal: string
inherited_pressure: string
future_pressures: [string]
chapter_contract:
  chapter_id: chapter_007
  functions: [string]
  dramatic_question: string
  protagonist_choice:
    status: complete
    actor: string
    action: string
    alternatives: [string]
    cost: string
    consequence: string
    missing_fields: []
  reader_change:
    before: string
    after: string
  information:
    reveal: [string]
    withhold: [string]
    misdirect: {values: [], not_applicable_reason: string}
  pressure_curve: {start: string, turn: string, end: string}
  foreshadow_actions: {values: [], not_applicable_reason: string}
  ending_shift: string
  forbidden: {values: [], not_applicable_reason: string}
  target_chinese_chars: 7000
  optional_candidates: [OptionalCandidateResolution]
  intent_evidence_bindings:
    chapter_contract.functions[0]: [EvidenceRef]
```

冻结合同仅保存 `intent` 与 `non_applicability` 证据。`verification/realization` 永远不追加到 NarrativeDecision，因此冻结内容和审批 hash 不会因成稿而变化。

三态选择规则：`complete` 要求 actor、action、至少一个 alternative、cost、consequence 完整且 `missing_fields=[]`；`partial` 必须列出全部缺失字段；`unknown` 不携带臆测值。后两者均阻断 Writer。统一使用 `reader_change.before/after` 和 `pressure_curve.start/turn/end`，API、Issue 与报告不得再使用 `reader_before/reader_after` 等别名。

### 6.2 因果字段闭包与可选候选判定

`causal_field_paths` 是版本化常量，至少包含：

```text
arc_phase
arc_goal
inherited_pressure
future_pressures[*]
chapter_contract.functions[*]
chapter_contract.dramatic_question
chapter_contract.protagonist_choice.status|actor|action|alternatives[*]|cost|consequence
chapter_contract.reader_change.before|after
chapter_contract.information.reveal[*]|withhold[*]|misdirect.values[*]
chapter_contract.pressure_curve.start|turn|end
chapter_contract.foreshadow_actions.values[*]
chapter_contract.ending_shift
chapter_contract.forbidden.values[*]
```

`chapter_id`、`target_chinese_chars`、三个 `not_applicable_reason` 不是剧情因果字段，但仍是 Writer 必填控制字段。`optional_candidates` 使用确定结构：

```yaml
candidate_id: string
kind: foreshadow_next_action|relationship_change|scene_transition
value_state: known|unknown
proposed_value: string|null
dependency_inputs: [field_path]
affects_current_chapter: yes|no|undetermined
rationale: string
decided_by: rule|human
decision_ref: string
```

`CausalDependencyAnalyzer` 的输入是完整候选、Profile、事实快照、上一章和改纲记录；输出是每个 candidate 的上述判定及规则版本。`undetermined` 或分析失败一律阻断。规则可判定明确的直接引用；其余必须由人类裁决为 yes/no。yes 时必须变为 known 并纳入相应正式字段；no 时允许不进入冻结投影，但保留裁决记录。实现者不得凭字符串或个人判断跳过。

### 6.3 字段级 EvidenceRef 与存储信封边界

```yaml
evidence_id: ev-uuid
field_path: chapter_contract.protagonist_choice.cost
role: intent|verification|realization|non_applicability|decision
source_id: production/...
source_version: string
source_content_hash: sha256
locator: {kind: json_pointer|line_range|text_anchor|record_id, value: string}
excerpt: string
assertion: string
```

- `MemoryEvidence` 仅证明 MemoryItem 这个存储信封来自哪里，不满足任何字段门禁。
- `EvidenceRef` 才能证明字段；它可以用 `source_id/source_version/source_content_hash` 引用与 MemoryEvidence 相同来源，但两者不互相替代。
- 去重键为 `(contract_id, contract_version, field_path, role, source_id, source_version, locator, source_content_hash)`；相同摘录绑定不同字段时是不同证据。
- 完整性校验验证来源存在、版本/hash、locator 可定位及 assertion 针对 field_path；来源漂移使证据陈旧，不允许仅凭 excerpt 继续有效。
- 数组必须逐元素绑定，使用稳定索引路径，如 `functions[0]`、`reveal[1]`、`withhold[0]`、`alternatives[0]`、`future_pressures[2]`。冻结后数组重排属于字段变化；不得用数组父路径的一条证据覆盖全部元素。
- `protagonist_choice.status` 和 `missing_fields[*]` 在回放/候选期需要字段级证据；正式冻结合同 status 必为 complete、missing_fields 为空。
- 空数组的 `not_applicable_reason` 必须有 `non_applicability` EvidenceRef；非空数组不允许 reason。状态派生值本身不要求正文 realization，但其组成字段均须闭环。

### 6.4 外部追加式成稿证据

```yaml
contract_fulfillment_evidence_record:
  record_id: string
  contract_id: narrative-chapter-007
  contract_version: 2
  contract_content_hash: sha256
  field_path: chapter_contract.protagonist_choice.cost
  evidence:
    role: verification|realization
    source_id: string
    source_version: string
    source_content_hash: sha256
    locator: {kind: line_range, value: string}
    excerpt: string
    assertion: string
  recorded_at: timestamp
```

记录只能追加，不能修改合同、MemoryItem 内容、contract content hash 或 ContractApprovalRecord。更正采用 `supersedes_record_id` 新记录；Evaluator 只取未被取代且完整性有效的记录。`CONTRACT_FULFILLED` 由“冻结合同内 intent/non_applicability + 外部 verification/realization records”推导，而非改变冻结合同。

`chapter_id` 和目标字数的 realization 可引用最终工件元数据；显式空字段使用 `intent + verification + non_applicability`，其他确定性叶字段使用 `intent + verification + realization`。

### 6.5 BaselineManifest 与审批记录

```yaml
baseline_manifest:
  entries:
    - role: profile|fact_snapshot|previous_chapter|outline_change
      source_id: string
      source_version: string
      content_hash: sha256
  fingerprint: sha256(canonical_json(entries_sorted))

contract_approval_record:
  contract_id: narrative-chapter-007
  contract_version: 2
  contract_content_hash: sha256
  baseline_manifest: BaselineManifest
  approvals:
    full_contract:
      status: approved|rejected
      reason: string
      approved_by: human-id
      approved_at: timestamp
    major_choice_and_cost: ApprovalItem
    information_reveal_and_misdirect: ApprovalItem
    foreshadow_payoff_or_close: ApprovalItem
    new_facts: ApprovalItem
    outline_change: ApprovalItem
    post_freeze_revision: ApprovalItem
```

每个专项项状态为 `approved|rejected|not_applicable`；`not_applicable` 必须有非空 reason、人工 actor 和时间，不能使用全局 notes 代替。`full_contract` 永远不能 N/A。

Baseline 至少绑定批准时使用的 Profile、所有事实快照、上一章正式工件/冻结合同、所有适用改纲记录的 `source_id/source_version/source_content_hash`。WriterAdmission 重新构造 manifest：条目集合、任一来源版本/hash 或整体 fingerprint 不同即 `stale_contract_baseline`（blocking/high），必须重新运行预写 Reviewer 并重新审批完整合同及受影响专项项。

### 6.6 审批覆盖路径与冲突规则

| 审批项 | 覆盖 field_path | 触发重新审批 |
|---|---|---|
| full_contract | NarrativeDecision 全部内容与 baseline fingerprint | 任一合同字段、intent 证据、baseline 变化 |
| major_choice_and_cost | `protagonist_choice.*`、相关 pressure/ending consequence | 覆盖路径或其因果依赖变化 |
| information_reveal_and_misdirect | `information.*`、相关 reader_change/forbidden | 覆盖路径或依赖变化 |
| foreshadow_payoff_or_close | `foreshadow_actions.*` 及对应 hook | 兑现、关闭、归档或 N/A 原因变化 |
| new_facts | 合同声明的事实候选/事实边界引用 | 新增、删除或修改事实候选 |
| outline_change | `arc_phase/arc_goal` 和 NarrativeChangeRequest 引用 | 改纲引用或受影响因果字段变化 |
| post_freeze_revision | revision request 全部 changed_field_paths | 任一冻结后 replacement candidate |

`full_contract=approved` 不能覆盖专项 rejected、缺失或非法 N/A；任一必需专项非 approved 即阻断。专项 approved 也不能覆盖 full_contract rejected/缺失。N/A 仅在 ApprovalPolicy 判定该项无适用字段/事件且人类给出原因时合法；适用却标 N/A 报 `invalid_approval_not_applicable`。

## 7. 逻辑身份、物理版本与状态机

### 7.1 JsonMemoryStore 兼容布局

- 逻辑 `contract_id` 固定为 `narrative-chapter-NNN`。
- `contract_version` 是唯一业务版本，从 1 开始单调递增且不得复用；所有审批、证据、Reviewer 和 token 只引用它。
- 每版使用不可变物理键 `narrative-chapter-NNN-vMMMM`，其中 `MMMM = contract_version` 的四位十进制补零；例如业务版本 2 必须使用 `v0002`，codec 拒绝不相等的键。
- current pointer 独立为小型索引 `contract-current-NNN`，只含 `physical_key/contract_version/content_hash`；`pointer.contract_version` 必须等于合同内 `contract_version` 和物理键后缀。
- `MemoryItem.version` 不参与业务版本。由于每个物理键只写一次，v2 合同信封的 `MemoryItem.version` 固定为 `1`；codec 读取到其他值即报 `invalid_contract_envelope_version`。不得把它与 `contract_version` 同步或用于排序。
- replacement candidate 使用下一 `contract_version` 的新物理键；旧物理版本不被覆盖，因此二者可共存。
- 现有固定 ID 读取仅作为 v1 adapter；v2 业务不得覆盖同一 items 文件来模拟修订。

`current pointer` 是唯一业务活动真源。`MemoryStatus` 只是存储信封的派生/校验字段：pointer 指向的物理记录最终应为 `ACTIVE`，未指向的新版本应为 `CANDIDATE` 或 `REJECTED`，历史版本应为 `ARCHIVED`。所有对外读取必须先解析 pointer，禁止通过 `JsonMemoryStore.list()` 中的状态推断活动合同。这样即使多文件状态更新不能成为单一文件事务，也不会产生对外可见的双 ACTIVE。pointer 永远不得指向 `CANDIDATE`、`REJECTED` 或 hash 不匹配记录。

### 7.2 首次激活（阶段 A）

首次激活在单项目锁内完成，前置条件是 pointer 不存在、v0001 candidate 已完成审批且内容/hash 不再变化。

| 锁内步骤 | v0001 MemoryStatus | pointer | 对外活动版本 |
|---|---|---|---|
| 0 初始 | CANDIDATE | 不存在 | 无；Writer 必须阻断 |
| 1 写 `initial_activation_prepared` | CANDIDATE | 不存在 | 无 |
| 2 将信封状态写为 ACTIVE | ACTIVE | 不存在 | 无；对外读取只认 pointer |
| 3 原子创建 pointer | ACTIVE | v0001/1/hash | v0001 |
| 4 写 `initial_activation_committed` | ACTIVE | v0001/1/hash | v0001 |

步骤 0–2 不存在活动合同是合法的“尚未首次发布”状态，不是既有活动版本丢失；此时 Admission 必须返回 `missing_active_contract`。崩溃恢复：pointer 不存在且有 prepared 时，将 v0001 恢复为 CANDIDATE 后重试；pointer 已指 v0001 时验证 hash/status，补写 ACTIVE 或 committed。首次激活完成后，pointer 必须始终解析到一个已审批、hash 匹配、信封状态 ACTIVE 的冻结版本。

### 7.3 Replacement 切换（阶段 C）

```text
DRAFT_CANDIDATE -> PREFLIGHT_BLOCKED | AWAITING_APPROVAL
AWAITING_APPROVAL -> REJECTED | APPROVED_FROZEN
APPROVED_FROZEN + replacement CANDIDATE -> REVISION_PROPOSED
REVISION_PROPOSED -> REVISION_REJECTED | SWITCHING
SWITCHING -> old SUPERSEDED + replacement APPROVED_FROZEN
```

切换要求 `replacement.contract_version = current.contract_version + 1`，在单项目锁内执行 CAS。表中“双 ACTIVE”仅指两个信封状态的短暂落盘值；对外活动真源仍是 pointer，因此始终只有一个可消费版本。

| 锁内步骤 | 旧版 MemoryStatus | replacement MemoryStatus | pointer | 对外活动版本 |
|---|---|---|---|---|
| 0 初始 | ACTIVE | CANDIDATE | old | old |
| 1 校验 CAS 并写 `switch_prepared` | ACTIVE | CANDIDATE | old | old |
| 2 校验新审批/hash，预置新信封 | ACTIVE | ACTIVE | old | old |
| 3 原子替换 pointer | ACTIVE | ACTIVE | new | new |
| 4 归档旧信封 | ARCHIVED | ACTIVE | new | new |
| 5 写 `switch_committed` | ARCHIVED | ACTIVE | new | new |

步骤 2 的双 ACTIVE 不通过任何领域 API 暴露；禁止绕过 pointer 按 MemoryStatus 查询。绝不先归档旧版，pointer 不会指向 CANDIDATE，因此不存在零活动版本窗口。

崩溃恢复矩阵：

| 崩溃位置 | 可观察状态 | 恢复动作 | 保持的不变量 |
|---|---|---|---|
| 步骤 1 后 | old ACTIVE、新 CANDIDATE、pointer=old | 清理 prepared 或重试 | old 唯一对外活动 |
| 步骤 2 后 | 两信封 ACTIVE、pointer=old | 将新信封降回 CANDIDATE，或重试 CAS | pointer 仍解析 old；无对外双活动 |
| 步骤 3 后 | 两信封 ACTIVE、pointer=new | 验证 new 审批/hash 后归档 old | new 唯一对外活动 |
| 步骤 4 后 | old ARCHIVED、新 ACTIVE、pointer=new | 补写 committed | new 唯一对外活动 |
| 审计提交后 | 标准终态 | 幂等返回成功 | 历史版保留且不可变 |

若 CAS 发现 pointer 已变化，则不得自动递增或覆盖：replacement 保持 CANDIDATE，报 `contract_switch_conflict` 并要求基于新 current 重新提案。恢复器只执行表中确定动作；任何 pointer 目标缺失、非 ACTIVE、审批/hash 不匹配都进入隔离并阻断 Admission，不猜测修复。

## 8. 审批与冻结流程

1. Director 依据显式 baseline 提出 v2 candidate。
2. Preflight 校验字段、数组 intent 证据、N/A 原因及 CausalDependencyAnalyzer 结果。
3. 预写 Reviewer 针对该 candidate 的 `contract_version/contract_content_hash`、baseline fingerprint 和规则资产版本生成 `PrewriteReviewerResult`。
4. ApprovalPolicy 计算必需审批项与覆盖路径；人工逐项裁决。
5. LifecycleCoordinator 验证无冲突后冻结 candidate；首次合同按第 7.2 节创建 v0001 并首次激活，修订合同按第 7.3 节切换 pointer。
6. WriterAdmissionService 重新读取所有绑定对象并签发 token。
7. 成稿后 Reviewer 追加 fulfillment records；FulfillmentEvaluator 推导完成状态。

人工审批只能阻止或通过特定 hash，不能自动补全字段。冻结后任何变化都创建 replacement physical version 和 RevisionRequest；原版本保持有效至 CAS 成功。

## 9. Writer 准入与不可绕过约束

`WriterAdmissionService` 仅在以下条件全部满足时返回 `allowed=true`：

1. current pointer 唯一解析到活动冻结版本，合同的 `contract_version/contract_content_hash` 与审批一致。
2. 所有必填控制字段和 `causal_field_paths` 非 unknown；选择 complete；允许空字段有合法 reason 和证据。
3. 每个标量和数组元素有有效 intent；Task 与 Director 对同一 field_path 的 intent 值冲突时报 `conflicting_intent_evidence`，由人工裁决后重签审批。
4. 可选候选均为 yes+known 或 no+人工/规则裁决；undetermined/分析失败阻断。
5. 所有适用审批项 approved，N/A 合法，无待决修订、改纲或事实冲突。
6. 当前 baseline manifest 与审批绑定值完全一致。
7. 存在 `PrewriteReviewerResult`，其 `contract_version/contract_content_hash`、baseline fingerprint、规则资产版本均当前有效，且无未裁决 Issue。

Reviewer 结果在合同、baseline、Reviewer rule-set、语义资产任一版本变化时 stale。缺失报 `missing_prewrite_review/high/blocking`；陈旧报 `stale_prewrite_review/high/blocking`。

Issue 结构必须包含 `code/severity/blocking/field_path/evidence_checks/repair_hint`。high 一律阻断；warning 默认阻断，只有人类 `ReviewIssueDisposition(status=accepted|resolved, reason, actor, time, reviewer_result_hash)` 后才放行；low 默认不阻断，但若规则标记 `requires_human_disposition=true` 仍需裁决。

admission token 至少绑定 `project_id/chapter_id/contract_id/contract_version/contract_content_hash/baseline_fingerprint/reviewer_result_hash/context_fingerprint/run_id/expires_at` 并签名。生产入口验证 token 后才构造 Writer 请求；没有 token、过期、run 不匹配或任何绑定漂移均拒绝。ContextCompiler 使用 token 的排除清单避免通用 Memory 再注入同一 NarrativeDecision。

## 10. Reviewer 与语义重复边界

### 10.1 人物选择 Issue

- `missing_protagonist_choice`：status unknown，只绑定 status 检查轨迹。
- `partial_protagonist_choice`：status partial，列出并绑定 `missing_fields[*]`。
- `missing_choice_cost`、`missing_choice_alternatives`、`missing_choice_consequence`：分别绑定具体缺失路径。

Issue 不携带整章通用证据。缺失字段以 `evidence_checks` 记录已检查的精确来源和 locator；已有字段证据不能冒充缺失证明。

### 10.2 本地语义重复资产

语义归一只使用仓库内版本化测试资产：

- `function_semantics/v1/action_lexicon.json`：动作同义词到 canonical action。
- `function_semantics/v1/stop_phrases.json`：仅删除无语义前缀，如“让”“推进”；否定词不得删除。
- `function_semantics/v1/function_types.json`：建立/升级/转折/揭示/兑现/收束及允许迁移。
- `function_semantics/v1/entity_slots.json`：来自已批准 Profile/事实实体 ID 的别名映射，不从正文自由猜测。
- `function_semantics/v1/cases.json`：正例、反例、升级/兑现边界和词典外样本。

比较键为 `function_type + canonical_action + entity_or_hook_id + before_state + after_state + arc_phase + ending_shift`。资产版本写入 ReviewerResult。

- 字面不同但结构相同且无升级/新后果：`repeated_chapter_function` warning、`blocking=true`，必须人工 resolved/accepted。
- 词典外或槽位含糊：`uncertain_function_similarity` warning、`blocking=true`，必须人工裁决，不自动判重复。
- 字面相同但有合法阶段迁移、兑现或新后果：记录 non-blocking relation；仍保留比较证据。

## 11. 冻结后修订与改纲协议

1. 以新物理键创建 replacement candidate，引用 `base_contract_version/base_contract_content_hash`；冻结合同绝不原地覆盖。
2. RevisionRequest 列出 changed_field_paths、因果影响、场景/正文影响及是否涉及改纲、新事实、伏笔或信息策略。
3. ApprovalPolicy 根据变化路径要求 `post_freeze_revision + full_contract + 所有受影响专项项` 重新审批；baseline 变化还要求新 ReviewerResult。
4. 人物目标、核心因果、揭示时点、伏笔兑现/关闭、结局方向或事实边界变化必须引用已批准 NarrativeChangeRequest。
5. LifecycleCoordinator 按第 7.3 节 CAS 切换；失败时旧版继续有效。
6. 已签发 token 绑定旧 hash，新版本切换后立即失效；旧 run 必须取消或由人类对旧合同显式准许继续，不能换约运行。
7. 已有正文不自动改写，只生成显式修订任务并重新建立 fulfillment evidence。

## 12. 错误、陈旧与完成判定

主要阻断码：`incomplete_contract`、`invalid_not_applicable_reason`、`conflicting_intent_evidence`、`unresolved_causal_candidate`、`causal_analysis_failed`、`missing_required_approval`、`invalid_approval_not_applicable`、`approval_hash_mismatch`、`stale_contract_baseline`、`missing_prewrite_review`、`stale_prewrite_review`、`unresolved_review_warning`、`contract_switch_conflict`、`invalid_admission_token`、`stale_fulfillment_evidence`。

所有错误 fail-closed，不调用 Writer、不自动补值、不自动改纲。`WRITER_READY` 由冻结合同、审批、baseline、Reviewer 和因果裁决推导；`CONTRACT_FULFILLED` 由同一冻结合同加外部追加式 fulfillment records 推导。后者缺证据不会反向改变合同或审批状态。

## 13. Schema codec、迁移与兼容

- `NarrativeDecisionCodec` 是版本分派边界：`decode_v1()`、`decode_v2()`、`encode_v2()`；领域服务只接收规范化 v2，不散布版本判断。
- `ReplayContractCodec` 独立处理回放 v1/v2，不能返回正式 ChapterContract。
- `LegacyNarrativeAdapter` 将 v1 映射为 v2 candidate 和 MigrationReport；不写存储、不审批、不设置 pointer。
- v1 `chapter` 可派生 chapter_id，但不算证据；旧 EvidenceRef 映射 `legacy_unclassified`，不满足新门禁。
- v1 空数组迁为待人工确认，不能自动生成 N/A reason；旧活动合同写前必须迁移并重审，已完成章节只做回放。
- 迁移以 `(legacy_item_id, legacy_version, legacy_content_hash)` 为幂等键；重复运行产出同一候选/报告。部分失败不移动 current pointer；恢复时重用已成功写入的不可变物理版本，校验 hash 后继续。
- v2 codec 必须拒绝未知必填字段状态，保留明确允许的扩展区；v1/v2 round-trip、跨版本读取和损失报告均有契约测试。

## 14. 测试策略

- 字段表驱动：每个必填/因果字段逐一 unknown；数组逐元素缺 intent；status、missing_fields、N/A reason 证据规则。
- 意图证据：Task/Director 同值合并、冲突阻断、MemoryEvidence 不能冒充 EvidenceRef、来源/hash/locator 漂移。
- Reviewer：缺失与陈旧结果、规则资产变化、missing/partial/cost 等精确分流、Issue 不泄漏整章证据。
- 审批：每个专项 approved/rejected/N/A、N/A 原因缺失、full_contract 与专项冲突、覆盖字段变化触发重审。
- 语义：字面相同但升级、字面不同同结构、词典外不确定、warning 未裁决阻断、资产版本固定。
- 因果：yes/no/undetermined、人工裁决、分析器失败、外层 arc/pressure 字段变化。
- 准入：生产入口无 token、伪造/过期/stale token、直接 load 被架构测试禁止、Memory 重复注入排除。
- fulfillment：追加 verification/realization 不改变合同/hash；更正记录 supersede；旧合同或正文 hash 的证据 stale。
- 生命周期：首次激活各步骤与崩溃恢复、旧 ACTIVE 与 replacement candidate 共存、CAS 竞争、每个合法中间态恢复；首次激活后始终有一个有效 current。
- 版本映射：contract_version 单调递增、物理键后缀及 pointer.contract_version 严格相等、MemoryItem.version 恒为 1，codec 拒绝任一不一致。
- 迁移：幂等、部分失败恢复、v1/v2 codec、v2 兼容与回放读取。
- 第 1–6 章回放：第 5 章选择候选、第 2–4 章 partial 及逐项 missing_fields 可判定。

## 15. 分阶段交付与独立验收

以下是产品能力切片，不是实施计划。每阶段均可独立测试，且后续阶段不能削弱前序门禁。

### 阶段 A：不可绕过的最小写前闭环

范围：v2 codec/model、唯一 contract_version 映射、首版不可变物理键、current pointer、首次激活与恢复、字段与数组 intent、因果闭包、Preflight、完整合同及全部适用专项审批、BaselineManifest、预写 Reviewer、冻结、token 化 WriterAdmission、Context 排重。

验收：可独立完成 v0001 创建、审批、冻结、首次激活、pointer 解析、Admission 和 Writer 调用；首次激活任一步崩溃均可恢复为“未激活”或“v0001 已激活”的确定状态。任何 unknown、证据冲突/缺失、N/A 非法、因果未决、Reviewer 缺失/陈旧、warning 未裁决、审批缺失/冲突、baseline 漂移或 token 异常均无法调用 Writer。重大选择、信息、伏笔、新事实、改纲从本阶段起即强制人工审批。

### 阶段 B：独立成稿证据闭环

范围：追加式 `ContractFulfillmentEvidenceRecord`、正文/工件 locator、证据更正和 FulfillmentEvaluator。

验收：追加 verification/realization 不改变冻结合同或审批 hash；每个确定性字段形成要求的角色闭环；计划意图不计作完成事实。

### 阶段 C：冻结后安全修订

范围：在阶段 A 已有不可变物理键与 current pointer 之上，仅增加 replacement candidate、RevisionRequest、CAS 切换、各崩溃点恢复、旧 token 失效与历史版本保留；不首次引入 pointer。

验收：旧 ACTIVE 与 replacement candidate 合法共存；冻结后修订及受影响专项重新人工审批；注入故障时无零活动窗口且可确定恢复。

### 阶段 D：回放迁移与语义重复

范围：v1/v2 adapters、幂等迁移、1–6 章回放、版本化本地语义资产。

验收：第 5 章明确候选和第 2–4 章 partial 可表达；重复/不确定 warning 未裁决阻断；不接外部模型；旧报告可读。

## 16. 完成定义与自审记录

- `WRITER_READY` 前，合同、baseline、Reviewer、审批、因果裁决和 token 全部绑定同一 `contract_version/contract_content_hash`。
- `CONTRACT_FULFILLED` 只由冻结合同与外部追加式证据推导，绝不修改冻结内容。
- 所有审批项、允许空字段和数组元素具有精确 field_path 与证据规则。
- 首次激活前 pointer 可不存在且 Admission 阻断；首次激活后 pointer 始终指向一个有效冻结版本，修订失败不影响旧版。
- Codec/adapter 隔离 v1/v2；不存在平行 Director、平行 ChapterContract 或第二合同真源。
- 占位符检查：未发现未决占位标记。
- 内部一致性检查：冻结合同只含写前证据；成稿证据、审批记录和 baseline 均外置并绑定同一 `contract_version/contract_content_hash`；无 hash 自修改闭环。
- 阶段独立验收检查：A 已包含 v0001 物理键、pointer、首次激活、Admission 全闭环，B 只追加完成证据，C 只增加 replacement/CAS/恢复/token 失效/历史保留，D 只增加兼容迁移与语义增强；各阶段输入、输出和验收可单独判定。
- Git 差异检查：`git diff --check` 通过；本次仍只修改本设计文档。
