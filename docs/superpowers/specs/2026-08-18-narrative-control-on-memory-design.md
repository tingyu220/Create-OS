# 基于现有记忆链路的叙事控制层设计

## 目标

在不改变现有六类事实状态、Memory 审批和 Context 编译边界的前提下，增加一层可审批、可追溯的叙事决策。它回答“下一章为什么写、谁主动行动、读者将改变什么判断”，而不重复记录已发生事实。

本阶段仅分析并规划《文明升阶》第 1 至 6 章；第 7 章不生成正文。

## 现有基座

```text
正式正文
  -> StateChange Candidate
  -> Memory Candidate
  -> 人工审批
  -> Active Snapshot / ContextCompiler
```

- `Knowledge`：事实真源和已确认项目资料。
- `novel_state_model`：人物、地点、时间线、事件、伏笔、信息边界六类事实变化。
- `MemoryItem`：候选、人工批准、审计、作用域和来源。
- `ContextCompiler`：按任务编译有限、可追溯的上下文。

这些机制不被 Narrative Layer 替代。

## 新增对象

### NarrativeProjectProfile

项目级叙事承诺同样作为 `MemoryItem(PROJECT_DECISION)` 候选保存，人工批准后才可被章节决策引用：

```yaml
schema_version: 1
kind: narrative_project_profile
story_contract:
  core_question: string
  reader_promise: [string]
  theme_conflict: string
  invariants: [string]
volumes:
  - id: string
    goal: string
    irreversible_change: string
arcs:
  - id: string
    volume_id: string
    goal: string
    phase: setup|escalation|turn|aftermath|closure
```

全书承诺、分卷目标和剧情段目标只在 Profile 中维护；章节合同只能引用、不能修改它们。

### NarrativeDecision

每个决策绑定一个章节，并作为 `MemoryItem(PROJECT_DECISION)` 的 JSON 内容保存。它的状态仍完全由既有 `MemoryStatus` 管理。

```yaml
schema_version: 1
kind: narrative_decision
chapter: 7
profile_id: narrative-project-profile
scale:
  volume_id: string
  arc_id: string
  arc_phase: setup|escalation|turn|aftermath|closure
  arc_goal: string
  rolling_window:
    inherited_pressure: string
    future_pressures: [string]
chapter_contract:
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
  target_chinese_chars: integer
  forbidden: [string]
```

`NarrativeDecision` 不能包含正文，不能修改六类事实状态，不能在没有人工批准时进入 Writer Context。

### NarrativeChangeRequest

改纲使用独立候选决策，不覆盖原始大纲：

```yaml
schema_version: 1
kind: narrative_change_request
reason: string
old_plan: string
new_plan: string
affected_chapters: [integer]
affected_state_subjects: [string]
affected_hooks: [string]
written_text_strategy: keep|local_revision|rewrite_candidate|archive
status: proposed|approved|applied|rejected
```

它必须经过已有人工批准；批准后才允许更新未来章节的 NarrativeDecision。已发布正文不会被自动改写。

## 组件边界

| 组件 | 输入 | 输出 | 禁止 |
|---|---|---|---|
| Director | 已批准事实状态、活动伏笔、上一章结尾、已批准 Profile 和叙事决策 | NarrativeDecision 候选 | 写正文、激活候选、改写事实 |
| Planner | 已批准 NarrativeDecision | Scene 约束与任务 | 变更章节合同 |
| Writer | Scene 约束、事实 Context、叙事决策 Context | 正文草稿 | 自行改纲、加入重大设定 |
| Reviewer | 草稿、合同、近期合同、事实 Context | 带证据的问题列表 | 自动修订正文或状态 |
| Compiler | 已通过草稿 | 事实状态候选、章节摘要候选 | 直接激活候选 |

补充控制层：

| 模块 | 负责 | 不负责 |
|---|---|---|
| `narrative_progression` | 比较连续合同的阶段、人物选择、压力、功能和伏笔动作 | 替 Director 选择剧情 |
| `narrative_lifecycle` | 管理结构化伏笔转移、人物情绪历史、读者预期连续性 | 从正文关键词臆测状态 |
| `narrative_change` | 分析改纲影响并生成迁移任务 | 自动修改正文、自动批准改纲 |
| `novel_state_store` | 合并已批准状态、处理数组/标量、冲突、幂等和 Context 投影 | 改变原始 Memory 候选 |

## 接入路径

```text
Director 提出 narrative-chapter-007 候选
  -> 人工批准
  -> build_next_chapter 只读取第 7 章活动决策
  -> ContextCompiler 注入紧凑投影
  -> Writer 按章节合同生成
  -> Reviewer 同时检查事实与叙事门禁
  -> Compiler 生成下一轮事实/叙事候选
```

未找到当前章节的活动叙事决策时，真实写作应阻塞；`--dry-run` 只报告缺失项，不调用模型。

## Reviewer 门禁

第一版只提供可解释、低误报检查：

1. 缺少人物选择、代价、后果或读者认知变化。
2. 与最近两章合同存在相同章节功能但没有明确升级。
3. 伏笔只重复、没有生命周期动作。
4. 开头连续使用时间词，或直接复述上一章摘要。
5. 场景切换缺少功能或因果桥。
6. 结尾没有具体新失衡。
7. 正文偏离已批准的信息揭露/隐藏边界。
8. 存在未经批准的改纲信号。

检查只报告字段、文本片段和严重度；不假装理解全文语义。

## 回放验证

第 1 至 6 章分别创建“回放候选”而不是修改原正文。每章输出：章节功能、人物选择与代价、读者前后判断、压力变化、伏笔动作、异常模式和证据段落。

回放通过的含义是：系统能识别第 1 至 6 章中的已知问题，并把不能可靠判断的内容标为人工待定；不是宣称旧章节已经符合新标准。

## 非目标

- 不接入网文示例库或风格检索。
- 不新增图数据库、前端或多模型自治。
- 不重新实现 Memory、审批、事实状态或全文向量检索。
- 不自动批准决策，不自动改写第 1 至 6 章，不生成第 7 章正文。
- Context 只使用有界状态投影；原始状态和证据仍保留在 Memory/快照中，可按来源重新检索。
