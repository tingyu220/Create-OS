# Scene And Technology Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Creative OS 小说生产链实现可序列化、可提示、可审查的场景结构与技术发展 Gate。

**Architecture:** 在叙事合同层新增聚合值对象，Director 执行结构校验，Reviewer 输出稳定问题码，Writer 消费同一份合同。跨章规则基于近期已批准合同，不引入正文 NLP 或新外部依赖。

**Tech Stack:** Python 3、dataclasses、pytest

**Spec:** `docs/superpowers/specs/2026-08-24-scene-and-technology-gates-design.md`

## Global Constraints

- 不重写第 7–23 章正文，不生成第 24 章，不调用真实模型。
- 保持 v1 历史合同可读取。
- 不改动项目中既有未提交生产产物。
- 已获准局部返工第 7–23 章；第 24 章仍禁止生产。
- 裁决口径：第 19 章人为袭击，第 20 章现实证据转运，第 22 章七年倒计时。

---

### Task 1: Contract model

**Files:**
- Modify: `creative_os/domains/narrative_decision.py`
- Test: `tests/test_narrative_director.py`

**Interfaces:**
- Produces: `SceneContract`, `ScenePlan`, `TechnologyContract`, `TechnologyPlan`

- [x] 写序列化和字段校验失败测试。
- [x] 运行测试确认因类型缺失失败。
- [x] 实现最小数据模型与 v1 兼容解析。
- [x] 运行测试确认通过。

### Task 2: Director gates

**Files:**
- Modify: `creative_os/domains/narrative_director.py`
- Test: `tests/test_narrative_director.py`

**Interfaces:**
- Consumes: `ScenePlan`, `TechnologyPlan`
- Produces: `NarrativeDirectorBlockedError` 的稳定结构原因。

- [x] 写缺失变化、外部切面和技术工程链阻断测试。
- [x] 运行测试确认失败。
- [x] 实现最小 Gate。
- [x] 运行测试确认通过。

### Task 3: Reviewer and Writer

**Files:**
- Modify: `creative_os/domains/narrative_review.py`
- Modify: `creative_os/novel_continuation_runner.py`
- Test: `tests/test_narrative_review.py`
- Test: `tests/test_novel_continuation_runner.py`

**Interfaces:**
- Produces: 场景/技术问题码及正文 Prompt 合同。

- [x] 写正文未演出地点、普通人缺失和技术应用缺失测试。
- [x] 运行测试确认失败。
- [x] 实现 Reviewer 与 Prompt。
- [x] 运行相关测试确认通过。

### Task 4: Regression verification

**Files:**
- Test: `tests/test_narrative_director.py`
- Test: `tests/test_narrative_review.py`
- Test: `tests/test_novel_continuation_runner.py`
- Test: `tests/test_novel_continuation.py`

- [x] 运行叙事与接续测试集。
- [x] 运行完整 pytest。
- [x] 检查 git diff，确认未改正文和生产产物。

### Task 5: Independent hardening review

- [ ] 证明 v1 只兼容读取，不能作为 Director 新生产合同绕过 v2 Gate。
- [ ] 证明地点或技术名称的孤立提及不能通过 Reviewer。
- [ ] 证明有批准例外时允许连续同地点章节。
- [ ] 运行全量测试后才允许进入正文返工。

### Task 6: Approved manuscript rework

- [ ] P0：8、10、13、14、16–22。
- [ ] P1：7、11、12、15、23。
- [ ] P2：9。
- [ ] 每批完成连续性、场景功能、技术工程链、追读与状态一致性审计。
