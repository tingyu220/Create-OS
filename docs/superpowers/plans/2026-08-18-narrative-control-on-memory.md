# 基于现有记忆链路的叙事控制层实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有小说状态、Memory 审批和续写流程上增加章节级叙事决策与审核，验证《文明升阶》第 1 至 6 章的叙事状态，而不生成第 7 章正文。

**Architecture:** 新对象仅作为 `MemoryItem(PROJECT_DECISION)` 候选保存；批准后由既有 Retriever 和 ContextCompiler 读取。Director 生成候选，Continuation Builder 要求当前章活动合同，Reviewer 增加叙事门禁，现有 Compiler 继续产生事实候选。

**Tech Stack:** Python 3.11、标准库 dataclasses/json/pathlib、pytest；不增加第三方依赖。

**Spec:** `docs/superpowers/specs/2026-08-18-narrative-control-on-memory-design.md`

## 全局约束

- 不修改或替代六类事实状态和 Memory 审批机制。
- 所有 NarrativeDecision 必须有来源、候选状态和人工批准记录。
- 未批准的决策不能进入 Writer Context；真实写作缺失合同必须阻塞。
- 第 1 至 6 章只回放分析，不重写；第 7 章不生成正文。
- 不触碰当前工作树中已有未提交实现，除非该文件属于本任务且已先读懂其现状。

### Task 1: 定义 NarrativeDecision 与改纲对象

**Files:**
- Create: `creative_os/domains/narrative_decision.py`
- Test: `tests/test_narrative_decision.py`

**Interfaces:**
- `NarrativeProjectProfile.from_json(content: str) -> NarrativeProjectProfile`
- `NarrativeDecision.from_json(content: str) -> NarrativeDecision`
- `NarrativeDecision.to_json() -> str`
- `NarrativeDecision.validate() -> None`
- `NarrativeChangeRequest.from_json(content: str) -> NarrativeChangeRequest`
- `NarrativeValidationError(ValueError)`

- [x] 写失败测试：缺少全书承诺、分卷/剧情段目标、人物选择代价、读者变化、结尾变化或正目标字数时必须拒绝；序列化后字段不丢失。
- [x] 运行 `pytest tests/test_narrative_decision.py -q`，确认因模块缺失失败。
- [x] 以冻结 dataclass 实现最小 JSON Schema；不包含正文和事实状态字段。
- [x] 运行 `pytest tests/test_narrative_decision.py -q`，确认通过。

### Task 2: 将叙事决策映射到现有候选/审批链

**Files:**
- Create: `creative_os/domains/narrative_memory.py`
- Test: `tests/test_narrative_memory.py`

**Interfaces:**
- `save_narrative_candidate(project_root, decision, evidence) -> MemoryItem`
- `save_project_profile_candidate(project_root, profile, evidence) -> MemoryItem`
- `load_active_narrative_profile(project_root) -> NarrativeProjectProfile | None`
- `load_active_narrative_decision(project_root, chapter_number) -> NarrativeDecision | None`
- `save_change_request_candidate(project_root, request, evidence) -> MemoryItem`

- [x] 写失败测试：保存后状态是 `CANDIDATE`；人工批准后 Profile 和章节合同才能被加载；其他章节和其他项目不能被加载；候选内容保留来源。
- [x] 运行 `pytest tests/test_narrative_memory.py -q`，确认失败。
- [x] 复用 `JsonMemoryStore`、`MemoryItem.new_candidate` 与 `approve_candidate`；不实现平行存储和审批。
- [x] 运行 `pytest tests/test_narrative_memory.py tests/test_memory_approval.py -q`，确认通过。

### Task 3: Director 只生成候选章节合同

**Files:**
- Create: `creative_os/domains/narrative_director.py`
- Test: `tests/test_narrative_director.py`

**Interfaces:**
- `DirectorInput(project_root, chapter_number, profile, fact_snapshots, previous_ending, active_decisions, target_chinese_chars)`
- `NarrativeDirector.propose(input: DirectorInput, proposal: NarrativeDecision) -> NarrativeDecision`
- 失败时抛出 `NarrativeDirectorBlockedError`。

- [x] 写失败测试：Director 拒绝章节号不一致、事实边界不足、试图覆盖已批准合同，以及正文非空的提案。
- [x] 运行 `pytest tests/test_narrative_director.py -q`，确认失败。
- [x] 实现确定性的输入/提案校验器；第一版不调用模型、不生成正文、不写 Memory。
- [x] 运行 `pytest tests/test_narrative_director.py -q`，确认通过。

### Task 4: 将已批准合同接入续写 Context

**Files:**
- Modify: `creative_os/domains/novel_continuation.py`
- Modify: `creative_os/novel_continuation_runner.py`
- Test: `tests/test_novel_continuation.py`
- Test: `tests/test_narrative_continuation.py`

**Interfaces:**
- `ContinuationTask.narrative_contract: NarrativeDecision | None`
- `build_next_chapter(..., require_narrative_contract: bool = False)`；正式 CLI 传入 `True`，兼容旧迁移调用
- `ContinuationBlockedError("missing approved narrative decision for chapter ...")`

- [x] 写失败测试：真实续写在缺少活动合同时阻塞；批准的合同进入 CompiledContext 来源并覆盖目标字数和禁止项。
- [x] 运行针对性测试并确认缺口后实现。
- [x] 仅加载当前章活动决策，压缩为 Context 所需投影；底层默认兼容旧调用，正式 CLI 强制合同。
- [x] 运行 `pytest tests/test_narrative_continuation.py tests/test_novel_continuation.py tests/test_continue_novel_script.py -q`，确认通过。

### Task 5: 实现叙事 Reviewer 门禁

**Files:**
- Create: `creative_os/domains/narrative_review.py`
- Modify: `creative_os/novel_continuation_runner.py`
- Test: `tests/test_narrative_review.py`

**Interfaces:**
- `NarrativeIssue(code, severity, evidence)`
- `review_narrative(contract, recent_contracts, text) -> list[NarrativeIssue]`

- [x] 写测试并捕获缺失主动选择/代价/读者变化、无伏笔动作、近期功能重复、时间词连续开头和草稿泄露禁止信息。
- [x] 实现结构检查和窄范围文本检测；问题对象保留字段或原文证据。
- [x] 将叙事问题代码接入续写和草稿晋升门禁；审核问题不会静默修改合同或正文。
- [x] 将结构化 evidence 持久化到章节审核 JSON，并在续写时加载最近两章合同供重复功能检查。

### Task 6: 对第 1 至 6 章回放并生成证据报告

**Files:**
- Create: `creative_os/domains/narrative_replay.py`
- Create: `tests/test_narrative_replay.py`
- Create: `projects/文明升阶/production/reports/narrative_replay_001_006.md`

**Interfaces:**
- `analyze_chapter(project_root, chapter_number, decision) -> ReplayFinding`
- `render_replay_report(findings) -> str`

- [x] 写测试：读取正式正文，按合同输出字段完整性、开头模式和文本证据；正文缺失时抛出明确错误。
- [x] 使用回放和 Reviewer 门禁生成报告，明确区分“自动检测”和“人工待定”。第 1 至 6 章当前没有已批准合同，因此不臆测章节功能。
- [x] 运行最终完整回归并复核报告内容。

## 验收

- 事实状态和叙事决策可同时存在，但来源和职责不混淆。
- 当前章 Writer Context 只读取已批准的 NarrativeDecision。
- Director 只能提出候选，不能写正文或自动批准。
- Reviewer 能带证据报告已知 AI 化模式，不能自动重写。
- 第 1 至 6 章回放报告可追溯至正式正文，且不修改它们。
- 第 7 章在没有人工批准合同前无法继续生成。

## 当前阶段审计结论

已完成的是“章节叙事合同门禁”的最小闭环，不等于已经具备百万字生产能力。当前确认的高优先级缺口如下：

1. `novel_state_model.py` 对第 3 至 6 章存在样例硬编码；必须改为通用的候选抽取、规则校验和人工审批链。
2. `novel_state_store.py` 目前采用字段浅合并；需要定义数组追加/覆盖、时间有效期、冲突和回滚规则。
3. Reviewer 尚未从项目存储加载最近合同；下一步要检查连续章节的功能升级，而不只是单章字段。
4. `NarrativeChangeRequest` 目前只能保存候选，尚未执行影响分析和未来章节迁移。
5. 伏笔、人物情绪和读者预期尚未形成可计算的生命周期与阶段转移指标。
6. 长篇记忆还缺少按卷/剧情段压缩、过期状态归档和 Context 成本监控。
7. 失败经验目前主要记录为问题代码，尚未区分项目事实、项目经验和跨项目写作规则。
8. 当前有章节合同，但还没有“卷/剧情段/全书”三级导演状态，无法判断连续章节是否完成铺垫、升级、高潮或回收。
9. 还没有把“人物主动性、冲突升级、场景目的、读者期待兑现”转成跨章节验收指标，Reviewer 目前只能做局部门禁。
10. 还没有生产级的中断恢复、幂等写入、失败重试和模型调用成本/耗时记录，无法可靠评估连续写作压测。
11. 旧章节回放没有合同和结构化状态时，只能输出“未知/待人工确认”，需要把历史资料导入作为显式迁移任务，不能靠正文关键词猜测。
12. Context 不能直接携带全量长期状态；当前已增加有界投影，但还需要在 10/30/100 章数据上记录压缩率、遗漏数量、编译耗时和恢复结果。

## 下一阶段顺序

```text
通用状态候选抽取
→ 快照合并与冲突规则
→ 最近合同与剧情阶段检查
→ 伏笔/情绪/读者预期生命周期
→ 改纲影响分析与迁移任务
→ 长篇记忆压缩与性能验证
```

## 当前目标边界

本阶段成功标准不是“接入更多写作样例”，而是：

> 在没有外部网文示例库的情况下，连续完成可审核、可恢复、状态不混乱的章节生产，并能解释每章为什么这样推进。

网文示例暂缓的原因：当前主要风险是事实状态、信息边界、章节功能和记忆生命周期不稳定；此时接入示例只能增加风格输入，无法修复控制层缺陷，还可能把范文风格与项目事实、长期经验混在一起。未来接入时必须作为独立 `Style Reference`，只影响表达和节奏建议，不写入事实 Knowledge 或长期记忆。

## 当前目标后的下一阶段

1. 完成状态快照合并规则：字段类型、数组追加/覆盖、冲突、有效期、回滚和幂等。
2. 建立卷/剧情段/章节三级动态导演：每章输出功能变化、冲突变化、人物选择、读者认知和结尾失衡。
3. 建立伏笔、人物情绪、读者预期的生命周期，并让 Reviewer 检查推进而不是只检查存在。
4. 实现改纲影响分析：变更请求影响哪些章节、人物、地点、伏笔和已生成正文，并生成迁移任务。
5. 增加 10 章连续生产验证，再进行 30 章、100 章的 Context 大小、耗时、记忆数量和恢复能力压测。

## 本轮已落地的控制层能力

- `novel_state_store.py`：数组字段追加去重、标量字段按章节覆盖、同章冲突阻断、重复物化幂等、有界 Context 投影。
- `narrative_progression.py`：剧情阶段倒退、人物选择重复、压力曲线停滞、章节功能与结尾失衡同时停滞、伏笔动作停滞检测。
- `narrative_lifecycle.py`：伏笔状态转移、人物情绪历史、读者预期连续性校验。
- `narrative_change.py`：改纲对已写正文、未来合同和状态快照的影响分析与迁移任务生成；不自动应用。

## 仍需真实生产验证的事项

- 当前进度指标基于结构化合同，不代表模型正文已经完成语义兑现；必须用第 7 至 16 章的真实生成结果验证误报和漏报。
- 情绪状态目前记录“状态集合”，没有强度标尺；在真实项目中先观察是否需要数值化，暂不提前引入复杂心理模型。
- 伏笔必须由 Compiler 产生明确状态候选，正文关键词不能自动把伏笔标记为回收。
- 压缩投影不能替代原始 Memory；任何被压缩或省略的内容都必须可以通过来源重新检索。

网文示例库不进入本阶段；待连续十章以上稳定通过后，再以独立 `Style Reference` 能力进行小范围 A/B 验证。
