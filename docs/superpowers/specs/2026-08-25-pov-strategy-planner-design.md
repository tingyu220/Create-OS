# POV Strategy Planner 架构设计

## 1. 状态、范围与目标

- 状态：总控已批准的架构设计稿。
- 本文只定义架构、数据契约、数据流、门禁、错误处理、迁移和验收，不包含生产代码、正文或实施计划。
- 目标：系统基于当前权威故事状态，为下一章提出可解释、可复核、可失效的 POV 策略候选，包括推荐人物、主角是否出场、理由、主线改变能力、备选方案、未来 3–4 章非冻结节奏建议与风险码。
- 核心原则：Planner 只提出候选，不拥有事实主权，不激活合同，不调用 Writer，不预写正文，不以固定比例或机械轮换代替叙事判断。

非目标：

- 不创建第二套 Chapter Contract、人物状态库或 Arc 状态库。
- 不预测或冻结未来 3–4 章的具体剧情、地点、技术成果或人物选择。
- 不自动批准 POV、重大事实、改纲或 Writer Admission。
- 不用“主角章占 60%–70%”之类硬编码比例作为评分或门禁。
- 不要求每章换 POV，也不因连续同一 POV 自动判错；连续性必须结合 Arc 原因和人物能动性判断。

## 2. 方案比较与架构决策

### 方案 A：独立纯决策域，输出证据绑定候选（采用）

新增小型 `pov_strategy` 领域，由输入装配器读取权威状态，纯 Planner 计算候选，Reviewer 校验候选与成稿。候选只作为 Director 输入；获批后唯一正式值仍写入 `ChapterContract.pov_plan`。

优点：无第二事实源；易测试、可替换评分算法；与现有 Director、审批、Writer、状态物化兼容。代价：必须定义稳定的证据引用、输入指纹与 stale 规则。

### 方案 B：把 POV 选择逻辑直接塞进 Narrative Director（不采用）

优点是调用链短；缺点是 Director 同时承担状态读取、候选搜索、评分和合同校验，形成高耦合大文件，也难以区分“建议”与“正式合同”。

### 方案 C：把 POV 历史和轮换表持久化为独立活动状态（不采用）

优点是查询直观；缺点是与正式合同、成稿和人物状态产生重复真值，容易出现“轮换表说 A、合同说 B”的分叉，违反无第二事实源原则。

决策：采用方案 A。Planner 输出是短生命周期的派生候选；Director 仍是唯一合同入口，`NarrativeDecision.chapter_contract.pov_plan` 仍是唯一获批 POV 意图。

## 3. 系统边界与组件

```text
权威故事状态 / 正式章节 / 活动合同 / Arc Profile
                     |
                     v
          POVStrategyInputAssembler
                     |
          immutable input + fingerprint
                     v
             POVStrategyPlanner
                     |
         candidate set + evidence + risks
                     v
          POVStrategyCandidateReviewer
                     |
                     v
 Narrative Director -> v2 Chapter Contract -> 人工批准
                     |
                     v
       Context / Writer Admission -> Writer
                     |
                     v
 Reviewer -> 正式章节 -> 状态物化 -> 下一章重新计算
```

| 组件 | 单一职责 | 明确禁止 |
|---|---|---|
| `POVStrategyInputAssembler` | 从权威来源装配最近历史、人物压力、Arc/线路状态、章节功能和场景需求，生成输入指纹 | 推断新事实、选择 POV、修改状态 |
| `POVStrategyPlanner` | 对可用 POV 计算服务能力、能动性、后果承接与风险，返回有序候选 | 激活合同、写正文、持久化事实 |
| `POVStrategyPolicy` | 承载项目级可配置策略参数与规则版本 | 保存章节真值、写固定比例 |
| `POVStrategyCandidateReviewer` | 校验证据、stale、功能适配、能动性和过渡理由，产生标准风险码 | 替代人工审批、改写候选 |
| `POVStrategyAdapter` | 把已选候选映射为 Director proposal 中的 `PointOfViewPlan` 骨架 | 绕过 Director 或补造 SupportingAgency 事实 |
| 现有 `NarrativeDirector` | 校验 POV 候选与完整 Chapter Contract、ScenePlan、TechnologyPlan 的一致性 | 把 Planner 建议当成已批准事实 |

组件建议保持分文件、小模型：输入/输出数据类、策略规则、Planner、Reviewer、适配器分别承担职责，避免扩张 `narrative_director.py` 或 `narrative_decision.py`。

## 4. 权威输入与证据模型

### 4.1 `POVStrategyInput`

```yaml
project_id: string
target_chapter: int
assembled_at: timestamp
policy_version: string
baseline_fingerprint: sha256
recent_pov_history:                 # 默认最近 8 章；项目可设 6–10
  - chapter: int
    primary_owner: character_id
    protagonist_present: bool
    chapter_functions: [string]
    mainline_outcomes: [state_change_ref]
    source_refs: [EvidenceRef]
protagonist_load:
  consecutive_absence: int
  consecutive_primary_pov: int
  unresolved_consequences: [ConsequenceRef]
character_pressures:
  - character_id: string
    unfinished_goals: [StateRef]
    pending_choices: [StateRef]
    unpaid_costs: [StateRef]
    agency_capabilities: [MainlineCapability]
arc_state:
  arc_id: string
  phase: string
  core_question: string
  current_pressure: string
storyline_states:
  engineering: StorylineState
  society: StorylineState
  international: StorylineState
  opponent: StorylineState
unclaimed_consequences: [ConsequenceRef]
chapter_needs:
  functions: [string]
  dramatic_question: string
  required_scene_capabilities: [string]
  required_world_slice: string|null
  technology_roles: [core|supporting|background]
```

输入来源只允许：

- 最近正式章节及其获批 `PointOfViewPlan`；成稿出场事实优先于计划，但两者必须同时保留来源。
- 当前活动 `NarrativeProjectProfile`、Arc 状态、正式大纲或已批准改纲。
- 已物化且处于活动状态的人物、事件、Hook、关系、时间线和工程状态快照。
- 下一章 Director 已知的章节功能候选、戏剧问题、ScenePlan/TechnologyPlan 需求；它们是计划输入，不是已发生事实。

不得从未批准草稿、被拒合同、Planner 旧候选或模型自由联想中装配事实。

### 4.2 稳定身份与引用

人物使用权威 `character_id`，展示名仅用于报告。每个 `StateRef`、`ConsequenceRef` 和 `EvidenceRef` 至少包含：

```yaml
source_id: string
source_version: string
source_content_hash: sha256
locator: string
assertion: string
materialized_after_chapter: int|null
```

`baseline_fingerprint` 对全部输入引用、策略版本、目标章节和项目参数做规范化哈希。任一来源版本/hash、活动状态、目标章节或策略版本变化，候选立即 stale。

### 4.3 “未承接后果”的定义

后果不是靠关键词猜测。它必须来自已批准合同的 `ending_shift/mainline_change` 或成稿物化状态，并且满足：

1. 已由某章产生；
2. 对后续 Arc 核心问题、主角选择条件或至少一条故事线仍有影响；
3. 尚无后续正式章节证据标记为 `acknowledged/acted_on/resolved`；
4. 有明确可能承接者和可改变状态。

“主角未承接”不等于主角必须亲自解决，而是系统需要判断主角的知识、选择条件或行动方向是否仍与已发生后果脱节。

## 5. 输出契约

### 5.1 `POVStrategyCandidateSet`

```yaml
target_chapter: int
input_fingerprint: sha256
policy_version: string
generated_at: timestamp
expires_when: [source_or_policy_changed, target_chapter_changed, contract_activated]
recommended:
  primary_owner: character_id
  protagonist_present: bool
  rationale: string
  chapter_function_fit: [EvidenceBinding]
  independent_mainline_change:
    target_state_ref: string
    change_type: acknowledge|choose|block|reveal|commit|pay_cost|redirect
    capability: string
    evidence_refs: [EvidenceRef]
  required_supporting_agency:
    actor: character_id
    goal_ref: StateRef
    resistance_ref: StateRef
    choice_boundary: string
    plausible_cost_ref: StateRef|null
  transition_reason:
    from_recent_pov: character_id
    arc_reason: string
    evidence_refs: [EvidenceRef]
alternatives:
  - primary_owner: character_id
    protagonist_present: bool
    benefits: [string]
    tradeoffs: [string]
    cannot_serve: [string]
    evidence_refs: [EvidenceRef]
rhythm_outlook:                    # 建议而非合同，不冻结具体人物
  horizon_chapters: 3|4
  pressures_to_revisit: [string]
  suggested_pov_functions: [acknowledge|externalize|counteract|ordinary_life|integrate]
  flexibility_notes: [string]
risks:
  - code: string
    severity: blocking|high|medium|low
    evidence_refs: [EvidenceRef]
    explanation: string
```

输出不得包含正文段落、对话、具体场景描写或未批准的新事实。`choice_boundary` 只声明“该人物必须有真实选择”，不替 Chapter Contract 编造具体选择；具体 `SupportingAgencyContract` 仍由 Director proposal 基于权威资料形成并接受审批。

### 5.2 未来 3–4 章节奏建议

`rhythm_outlook` 只描述需要被承接的压力和 POV 功能，例如“主角整合三线后果”“普通人验证制度是否落地”“国际线反作用于工程决策”。它不得指定第 28 章必由某人出场，也不得预建未来合同。每章物化后全部重新计算，旧展望仅保留审计记录，不作为下章输入真值。

## 6. 决策逻辑：适配优先，不按比例轮换

Planner 先做资格过滤，再做可解释排序。

### 6.1 资格过滤

候选人物必须同时满足：

- 能承担至少一个当前章节功能或场景视点需求；
- 有来源明确的独立目标、阻力和可支付代价；
- 其选择可以直接改变一个权威主线状态，而非只能观察或汇报；
- POV 转换存在 Arc、后果承接、信息权限或场景行动理由；
- 不要求人物知道其无权知道的信息。

不能满足者不进入推荐，只进入被拒候选及风险证据。

### 6.2 排序维度

排序采用离散解释等级，不输出伪精确概率：

1. `chapter_function_fit`：能否完成本章功能与戏剧问题；
2. `mainline_agency`：能否以选择直接改变主线状态；
3. `consequence_ownership`：是否最适合承接尚未处理的后果；
4. `arc_relevance`：是否推进当前 Arc 核心问题；
5. `information_legitimacy`：该 POV 是否自然拥有所需信息；
6. `continuity_pressure`：连续缺席、连续垄断或无理由切换是否造成风险；
7. `scene_technology_fit`：是否能真实执行 ScenePlan/TechnologyPlan 所需行动。

前四项是正向适配，后三项是约束。连续次数只触发复核，不直接决定人选。一个人物即使连续多章，只要每章承担不同的 Arc 必要选择且有证据，也可由人工批准例外。

### 6.3 项目级策略参数

允许项目配置：历史窗口 6–10、连续缺席/垄断的“开始复核”阈值、必须关注的故事线、主角身份、合法 POV 名单、严重风险是否阻断。配置不得包含目标百分比、固定轮换序列或“第 N 章必须回主角”。

例外记录必须包含 `rule_id`、理由、证据、人工 actor、适用目标章节和失效条件；不得成为全项目永久豁免。

## 7. 风险码与 Reviewer 语义

| 风险码 | 触发条件 | 默认级别 | 修复方向 |
|---|---|---:|---|
| `protagonist_absence_unresolved` | 主角连续缺席期间产生了会改变其知识/选择条件的后果，仍无承接证据，而候选章仍排除主角且无替代承接机制 | high；可配置 blocking | 让主角出场承接，或证明另一 POV 的行动能合法改变主角条件且无需汇报收尾 |
| `protagonist_pov_monopoly` | 主角连续占用 POV，存在其他具备独立主线能动性的角色/故事线被压制，且本章无 Arc 必要性解释 | medium/high | 评估有行动权的配角 POV；若继续主角 POV，记录 Arc 理由 |
| `supporting_pov_without_agency` | 推荐配角缺少独立目标、阻力、选择、代价或直接主线改变能力 | blocking | 更换 POV 或补齐有证据的能动性，不得靠写作时临时发明 |
| `pov_cannot_serve_chapter_function` | POV 的信息权限、行动范围或场景能力无法完成章节功能 | blocking | 改 POV、改章节功能候选，或经 Director 调整场景结构 |
| `supporting_outcome_only_reported_to_protagonist` | 配角的结果只有“得知后向主角汇报”，在汇报前未改变任何主线状态 | high | 让配角决定、阻断、承诺、付费或改变制度/工程/关系状态 |
| `pov_transition_without_arc_reason` | 相对最近主导 POV 的切换缺少 Arc、后果、信息权限或行动场景证据 | medium/high | 补充转换理由或保持原 POV；不得为“换口味”机械切换 |

风险产生于两个时点：

- 写前候选 Reviewer：检查 Planner 推荐能否进入 Director。
- 写后 Narrative Reviewer：对照获批 `PointOfViewPlan/SupportingAgencyContract` 与正文，确认结果已戏剧化，且不是末尾才向主角汇报。

风险码相同但证据角色不同：写前证据是权威状态与合同意图，写后证据是正式正文与状态变化。二者不得互相替代。

## 8. 与现有生产链的接口

### 8.1 Director 与 Chapter Contract

`POVStrategyAdapter` 只提供：推荐 `primary_owner`、`protagonist_present`、`rationale`、证据引用以及 SupportingAgency 所需边界。Director proposal 仍必须形成完整的：

- `PointOfViewPlan`；
- 至少一项 `SupportingAgencyContract`；
- 与 POV 匹配的 `ScenePlan.viewpoint/participants/action/state_change`；
- 如有技术行动，与 `TechnologyPlan.validation_stage/first_application` 匹配；
- 与 `ChapterContract.functions/dramatic_question/protagonist_choice/ending_shift` 一致。

Director 必须拒绝 Planner 候选指纹与当前输入不一致、推荐人物不在场景中、配角无主线改变或 POV 无法执行技术链的 proposal。Planner 推荐不强制 Director 采纳；人工可选择有证据的备选或覆盖。

### 8.2 审批与 Writer Admission

Planner 候选本身不进入 `ACTIVE` Memory，也不获得合同审批状态。人工批准对象仍是完整 v2 Chapter Contract。审批记录附带：

- 使用的 `candidate_set_id/input_fingerprint`；
- 采纳推荐、采纳备选或人工覆盖；
- 覆盖理由及证据；
- 当前合同内容 hash。

Writer Admission 只读取已批准合同，不直接读取 Planner 候选。这样即使候选过期，已批准合同仍按现有 baseline/stale 规则独立判断；若批准后权威故事状态变化，合同重新进入 stale/审批流程，而不是静默重跑 Planner 替换 POV。

### 8.3 Context 与 Writer

Context 只注入已批准 `PointOfViewPlan`、SupportingAgency、ScenePlan 和 TechnologyPlan。Planner 的候选排名、失败方案和未来节奏展望不进入 Writer Prompt，避免模型把备选人物或未来建议误写进正文。

### 8.4 状态物化与下一章重算

正式章节通过 Gate 后，现有章节候选与 `build_state_changes` 物化人物、事件、Hook 和时间线状态。新增 POV 投影只读取：实际出场、实际 POV、选择结果、代价兑现和主线状态变化，并引用正式章节。下一章 InputAssembler 重新装配并产生新指纹；上一章 Planner 候选不回写为事实。

## 9. Stale、人工覆盖与审计

### 9.1 Stale 条件

出现以下任一变化即返回 `stale_pov_strategy_candidate`，不得进入 Director：

- 新正式章节物化或目标章节改变；
- 最近 POV 历史、人物目标/选择/代价、Arc 或任一故事线活动状态变化；
- 章节功能、场景需求、TechnologyPlan 角色需求变化；
- 活动合同、Profile、批准改纲或项目策略版本变化；
- 任一证据来源版本/hash 无法复核。

### 9.2 人工覆盖

人工可覆盖推荐，但必须从以下两种方式中选择：

1. 采纳 Planner 备选：记录备选 ID、取舍和批准 actor；
2. 新 POV：提交 `HumanPOVOverride`，包含人物、主角是否出场、章节功能适配、独立主线改变、过渡理由、证据和仅本章有效的例外。

Reviewer 对人工覆盖运行同一组硬规则。人工身份可以批准合理例外，但不能让缺失事实、stale 证据、无能动性配角或无法服务章节功能的方案直接通过。

### 9.3 候选存档

候选集可作为追加式审计工件保存在 `.creative_os/runtime/pov_strategy/`，状态仅为 `proposed/selected/expired/superseded`。它不是 MemoryItem、不是 ProjectDecision、不能被普通 Context 检索。审计工件记录输入指纹和引用，不复制完整权威状态。

## 10. 错误处理

| 错误码 | 条件 | 行为 |
|---|---|---|
| `missing_pov_strategy_input` | 关键输入缺失，如无 Arc 核心问题或无章节功能 | 阻断候选生成，列出缺失字段 |
| `invalid_pov_history_window` | 窗口不在 6–10 或章节不连续 | 阻断并要求修复项目策略/历史来源 |
| `unknown_character_identity` | POV 人物无法映射到权威 character_id | 排除该候选；若无候选则阻断 |
| `unverifiable_pov_evidence` | 引用缺失、hash 不符或 locator 无法定位 | 标记 stale 并阻断 |
| `no_viable_pov_candidate` | 所有人物都无法同时满足功能与能动性 | 阻断 Director，要求调整章节功能或先补权威状态 |
| `stale_pov_strategy_candidate` | 输入指纹已变化 | 丢弃候选并重新计算，不自动复用 |
| `pov_strategy_policy_error` | 参数非法、出现比例或固定轮换配置 | 拒绝加载策略，使用项目发布前验证阻断生产 |
| `pov_override_insufficient_evidence` | 人工覆盖缺少理由、主线改变或证据 | 阻断审批 |

Planner 内部异常不得降级为“默认主角 POV”。安全失败方式是无候选、停止 Director proposal，并保留不含敏感正文的诊断记录。

## 11. 第24–26章验收样例：第27章

### 11.1 输入证据

- 第24章活动合同与正式正文：林正弘/韩宁冻结 D-0447 关联批次，工程线由抢修转入追溯；`protagonist_present=false`。
- 第25章活动合同与正式正文：陈玉兰/老周改变夜班与家属风险告知规则，社会后果进入复工条件；`protagonist_present=false`。
- 第26章活动合同与正式正文：马库斯/伊莲娜建立七地跨站校验，国际线排除单一设备故障但保留版本差异；`protagonist_present=false`。
- 三章均未出现林子轩；工程、社会、国际后果已经改变主线条件，但尚无正式章节证明林子轩已获知、选择或整合这些后果。

### 11.2 期望 Planner 输出

推荐：

- `primary_owner=林子轩`；
- `protagonist_present=true`；
- 理由：连续三章配角 POV 产生的工程冻结、普通人复工条件与国际校验结果都将改变主角下一步的知识和选择条件，当前 Arc 需要由核心人物承接，而不是继续扩大外部切面；
- 可独立改变的主线状态：林子轩必须对三线后果作出选择、整合或拒绝，改变首堆复工/验证方向；具体选择内容仍由第27章合同决定；
- 备选 POV：林正弘可继续处理工程责任，但无法单独承接国际样本对主角认知的影响；国际工程人员可深化校验，但会继续延迟主角承接；普通人 POV 可验证制度落地，但不能服务“整合三线”的章节功能；
- 风险：若仍推荐主角缺席，应产生 `protagonist_absence_unresolved`；若选择任何只汇报结果的配角，应产生 `supporting_outcome_only_reported_to_protagonist`；
- 未来 3–4 章展望：只建议“主角整合 → 外部后果反作用 → 对手线响应”等功能节奏，不冻结具体 POV 或章节事实。

该结果由通用规则导出：连续缺席次数本身不决定推荐；决定性证据是“未承接后果会改变主角知识/选择条件”与“第27章功能需要整合”。若第26章结尾已经由正式状态证明主角完成承接，或第27章功能改为境外现场立即阻断事故，Planner 可以合法推荐不同 POV。

## 12. 测试策略

### 12.1 单元测试

- 输入窗口只接受 6–10 章，按正式章节连续排序；不足 6 章时使用全部历史并显式标记冷启动，不伪造历史。
- `baseline_fingerprint` 对任一来源、策略或章节需求变化敏感。
- 无固定比例、无轮换序列；连续次数只产生风险，不直接覆盖功能适配结果。
- 配角缺少目标/阻力/选择/代价/主线改变时产生 `supporting_pov_without_agency`。
- 信息权限或场景能力不足时产生 `pov_cannot_serve_chapter_function`。
- 只有汇报行为时产生 `supporting_outcome_only_reported_to_protagonist`。
- 无 Arc 证据的切换产生 `pov_transition_without_arc_reason`。
- 主角长期占用且压制可行动故事线时产生 `protagonist_pov_monopoly`，合理 Arc 例外不报错。
- 候选序列化不包含正文或新事实字段。

### 12.2 集成测试

- Planner 推荐经 Adapter 进入 Director proposal，最终仍由现有 `PointOfViewPlan` 和 `SupportingAgencyContract` 表达。
- 未批准候选不能被 Context、Writer 或 MemoryRetriever 消费。
- Writer Admission 缺活动合同、合同 stale 或审批不完整时继续阻断。
- ScenePlan viewpoint、participants、action 与推荐 POV 不一致时 Director 阻断。
- TechnologyPlan 需要现场验证而 POV 无行动权限时阻断。
- 成稿通过后状态物化触发下一章新指纹，旧候选变为 expired。
- 人工采纳备选与新 POV 覆盖均留下审计记录并接受相同 Reviewer。

### 12.3 回归与验收

- v1 历史合同仍可读取，不要求补 Planner 数据；Planner 只面向下一章候选。
- 现有 v2 `PointOfViewPlan` JSON 格式保持兼容，不把 Planner 元数据写进合同。
- 第24–26章固定验收夹具必须自然推荐第27章林子轩 POV，并证明是由后果承接与章节功能导出，而不是章节号或“三章阈值”硬编码。
- 反例夹具：连续三章配角 POV 后若下一章必须在境外现场即时阻止不可逆事故，允许继续配角 POV，但必须给出 Arc/场景理由和主角后果承接展望。
- 全量测试和 `git diff --check` 必须通过。

## 13. 迁移与分阶段实现边界

这里只定义阶段边界，不构成实施计划：

1. **纯模型阶段**：数据契约、策略参数验证、风险码和确定性 Planner；不接生产入口。
2. **只读影子阶段**：从真实项目装配输入并输出审计候选，不影响 Director、合同或 Writer。
3. **Director 候选阶段**：Adapter 将已复核候选提供给 Director；仍要求完整合同人工审批。
4. **生产门禁阶段**：Writer Admission 校验合同引用的候选指纹、stale 与人工覆盖记录；成稿后自动失效并重算。
5. **语义增强阶段**：仅在确定性证据规则不足且已有离线评测时考虑模型辅助排序；模型输出仍是无事实主权候选，硬风险与证据完整性保持确定性。

迁移遵循向后兼容：旧合同不补写 Planner 字段；现有合同/状态文件不搬迁；Planner 审计工件独立追加且不进入普通 Memory 检索。任一阶段都不得绕过人工合同批准或 Writer Admission。

## 14. 架构不变量与验收清单

- 唯一正式 POV 真值仍是已批准 v2 `ChapterContract.pov_plan`。
- Planner 无事实主权、无激活权限、无 Writer 调用权限、无正文输出字段。
- 每项推荐、备选和风险均绑定可定位、带版本/hash 的证据。
- 每章状态物化后重新装配输入；旧候选按指纹自动失效。
- 不存在 POV 目标比例、固定轮换或章节号特判。
- 人工覆盖可审计、仅对目标章节有效，并接受同一硬门禁。
- ScenePlan、TechnologyPlan、SupportingAgency、审批、状态物化和 Writer Admission 使用现有接口，不建第二事实源。
- 第24–26章样例推荐第27章回到林子轩，但反例可以基于更强的 Arc/场景理由合法覆盖。
- 错误采用阻断式失败，不静默回退到主角 POV。
- 文档无占位符，不包含实施计划、生产代码或正文。
