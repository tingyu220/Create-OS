# 作者式动态叙事控制层设计

## 1. 目标与非目标

本设计为 Creative OS 增加一层独立的 `Narrative State` 与 `Director`，使系统在生成正文前能够回答：本章为什么存在、谁主动改变局面、付出了什么代价、读者的判断将如何变化。

本阶段以《文明升阶》第 1 至 6 章作为回放样本，不接入网文示例库，不生成第 7 章，不引入前端或图数据库。

不把叙事控制做成固定配额系统。情绪、场景数量和高潮间隔只能作为判断依据，不能成为机械规则。

## 2. 总体架构

```text
Knowledge
  -> Memory
  -> Novel State
  -> Narrative State
  -> Director
  -> Planner
  -> Writer
  -> Reviewer
  -> Compiler
```

### 2.1 边界

| 组件 | 负责 | 禁止 |
|---|---|---|
| Knowledge | 世界规则、人物设定、已确认资料 | 决定本章叙事目标 |
| Memory | 历史资料保存与检索 | 代替当前叙事判断 |
| Context | 按任务组装可追溯输入 | 持久化新的事实 |
| Novel State | 已发生的人物、地点、事件、时间线、伏笔和信息边界 | 规划未来情节 |
| Narrative State | 叙事承诺、剧情阶段、读者状态、节奏和章节意图 | 覆盖事实来源 |
| Director | 生成章节级导演决策和改纲提案 | 写正文、静默改事实 |
| Planner | 将导演决策拆成场景和行动任务 | 改变章节职责 |
| Writer | 依据已审批计划生成正文 | 自行改纲或补充重大设定 |
| Reviewer | 检查事实、叙事和文本问题 | 静默修改正文或状态 |
| Compiler | 编译已审批结果，生成状态更新和归档 | 做创作决策 |

`Knowledge` 是事实真源；`Novel State` 是由已审批结果生成的当前结构化事实投影，便于按实体和时间范围检索。`Narrative State` 是可版本化的创作意图。任何事实冲突必须回到 `Knowledge` 和审批流程处理，不能用叙事层掩盖。

## 3. Narrative State 模型

第一版使用结构化文档和追加式变更记录，保留当前投影，不把所有历史细节放入运行上下文。

### 3.1 多尺度结构

```text
Story Contract
  -> Volume
    -> Arc
      -> Rolling Window (当前章前后 3 至 5 章)
        -> Chapter Contract
          -> Scene Plan
```

各层职责：

- `Story Contract`：全书核心问题、主题冲突、读者承诺和不可突破的长期边界。
- `Volume`：本卷要兑现或加深的承诺，以及卷末不可逆变化。
- `Arc`：一段连续冲突的起点、压力、转折和结果。
- `Rolling Window`：短期因果桥，保存上一章后果、当前章决策和后续 3 至 5 章压力。
- `Chapter Contract`：本章唯一的叙事合同，审批后冻结。
- `Scene Plan`：场景功能、人物行动、冲突、结果和转场理由。

### 3.2 最小字段

```yaml
story_contract:
  core_question: string
  reader_promise: [string]
  theme_conflict: string
  invariants: [string]

scale:
  volume_id: string
  arc_id: string
  arc_phase: setup|escalation|turn|aftermath|closure
  rolling_window:
    previous_consequence: string
    current_pressure: string
    upcoming_pressures: [string]

chapter_contract:
  chapter_id: string
  functions: [string]
  dramatic_question: string
  protagonist_choice:
    actor: string
    action: string
    alternatives: [string]
    cost: string
    consequence: string
  reader_change:
    before: string
    after: string
  information:
    reveal: [string]
    withhold: [string]
    misdirect: [string]
  pressure_curve:
    start: string
    turn: string
    end: string
  foreshadow_actions: [string]
  ending_shift: string
  forbidden: [string]
  target_chinese_chars: integer

reader_state:
  known: [string]
  suspected: [string]
  misbeliefs: [string]
  expectations: [string]

agency_ledger:
  - actor: string
    desire: string
    choice: string
    cost: string
    consequence: string
    relationship_delta: string
    source_chapter: string

foreshadow_lifecycles:
  - id: string
    state: planted|deepened|misdirected|partially_revealed|revealed|consequence|archived
    next_action: string
    payoff_boundary: string
    source_chapters: [string]

outline_changes:
  - id: string
    reason: string
    old_plan: string
    new_plan: string
    affected_arcs: [string]
    affected_chapters: [string]
    affected_entities: [string]
    written_conflicts: [string]
    strategy: keep|local_revision|rewrite_candidate|archive
    status: proposed|approved|rejected|applied
```

字段是最小约束，不要求每一章填满所有数组。缺失信息必须显式标为未知或未决定，不能由 Writer 自行猜测。

## 4. 状态生命周期与合并

采用“事件记录 + 当前投影”而不是全量重算：

```text
章节决策审批
  -> 追加 Narrative Event
  -> 更新当前层级投影
  -> 章节完成后冻结 Chapter Contract
  -> 滚动窗口过期后压缩为 Arc 摘要
```

- 章节状态在审批后不可静默覆盖。
- 分卷和剧情段结束时生成摘要，但保留原始事件。
- 运行 Context 只加载全书承诺、当前分卷/剧情段、滚动窗口、本章合同和相关事实投影。
- 改纲只追加变更记录；应用变更时生成新的状态版本。
- 已写正文不自动重写，必须产生显式修订任务。

## 5. Director 契约

### 输入

```text
已确认 Novel State
当前 Story Contract、Volume、Arc
上一章后果与 Rolling Window
未兑现承诺和活跃伏笔
人物欲望、关系和当前可选行动
用户要求、目标字数和事实边界
```

### 输出

```text
Chapter Contract
候选 Scene Plan 约束
信息揭露/隐藏方案
伏笔推进动作
动态改纲提案（如有）
风险与需要人工审批的决策
```

Director 只产生可审计决策，不生成最终正文。若无法确定人物选择、事实边界或改纲影响，输出阻塞状态，交给人工，而不是猜测。

## 6. 叙事审核门禁

Reviewer 新增以下可解释检查：

1. 章节功能是否明确且未与近期章节重复。
2. 是否存在关键人物主动选择、代价和可追踪后果。
3. 读者认知是否发生具体变化。
4. 伏笔是否推进，避免只重复名词。
5. 是否机械回顾前文或复制章节开头模式。
6. 连续章节是否在压力来源、关系、信息确定性或行动风险上发生变化。
7. 场景切换是否有叙事功能，是否存在硬拼接。
8. 是否出现过度解释、人物已知信息重复说明或无因果移动。
9. 是否出现未审批的大纲变化、事实变化或新重大设定。
10. 结尾是否制造具体的新失衡，而非只使用抽象悬念句。

门禁只生成证据、严重级别和修复任务，不直接重写正文。

## 7. 动态改纲协议

任何改变人物目标、剧情因果、伏笔兑现或结局方向的调整都必须建立 `OutlineChange`：

```text
提出原因
  -> 计算影响范围
  -> 与已写正文比对
  -> 人工审批策略
  -> 生成迁移/修订任务
  -> 应用新 Narrative State 版本
```

小型语言润色不进入改纲；重大剧情变化必须进入改纲。系统不得因生成失败而自动改变核心承诺。

## 8. 与现有 V1 的接入方式

- 不修改 Foundation 的通用 `State`，叙事对象放在 Novel Domain。
- 扩展 Novel Domain 的 Schema 和规则，不把小说字段写入通用层。
- `ContextBuilder` 增加叙事投影输入，但仍只接收已检索、可追溯的资料。
- 现有 Planner、Writer、Reviewer、Compiler 保持职责，先增加输入契约和门禁，不重写闭环。
- 首次实现允许使用内存对象或项目 JSON 文件；持久化接口必须与业务逻辑分离。

## 9. 回放验证

对《文明升阶》第 1 至 6 章只做分析，不重写正文，逐章生成：

- Chapter Contract 回放；
- 人物主动性账本；
- Reader State 前后差异；
- 伏笔生命周期动作；
- 压力曲线；
- 章节功能重复报告；
- 机械回顾、时间词开头和场景硬拼接报告。

验证通过条件：系统能为每章生成完整、可追溯的叙事解释，并能识别已知问题；对无法可靠推断的内容必须标记不确定，而不是伪造事实。

## 10. 阶段验收

本设计阶段完成的证据应包括：

- Schema 和生命周期文档；
- 组件边界和 Director I/O 契约；
- 改纲协议；
- Reviewer 门禁清单；
- 第 1 至 6 章回放报告；
- 针对上述模型的单元测试和流程测试。

在回放验证完成前，不生成第 7 章，不接入网文示例库，不进行远程提交或推送。
