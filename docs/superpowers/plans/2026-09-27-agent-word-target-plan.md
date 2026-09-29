# Agent 字数目标与允许误差 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 Writer Agent 增加可追溯的目标字数与允许误差契约，并在写作界面显示范围和结果。

**Architecture:** 请求进入后端时校验 `target_words` 与 `tolerance_words`，计算最小/最大字数并写入 AgentJob；运行提示词携带范围，完成后记录实际字数与是否达标。前端只负责输入和展示，正式稿发布边界不变。

**Tech Stack:** Python、标准库 `dataclasses/json`、现有 `unittest/pytest` 测试、原生 HTML/JavaScript。

## Global Constraints

- 默认目标字数为 4500，默认允许误差为 300。
- 最小字数必须大于 0，允许误差必须大于等于 0，目标与误差必须为整数。
- 字数统计沿用现有前端去除空白字符的规则，并在后端使用同一规则。
- 字数不足或超出只产生状态提示，不自动截断或覆盖正文。
- 不改变正式稿发布流程。

### Task 1: Agent 字数契约与运行记录

**Files:**
- Modify: `creative_os/agent_runtime.py`
- Test: `tests/test_agent_runtime.py`

- [ ] 写测试：提交任务时保存目标、误差、最小值、最大值；非法参数被拒绝；完成任务记录实际字数和达标状态。
- [ ] 运行测试确认失败。
- [ ] 添加参数校验、AgentJob 字段和后端字数统计。
- [ ] 将范围写入写作提示词和决策记录。
- [ ] 运行相关测试确认通过。

### Task 2: Web API 传递字数参数

**Files:**
- Modify: `creative_os/web_workspace.py`
- Test: `tests/test_writer_word_target.py`

- [ ] 写 API 测试：请求携带字数参数后，runtime 收到完整契约；缺失时使用默认值。
- [ ] 运行测试确认失败。
- [ ] 扩展请求解析和错误返回，保持旧客户端兼容。
- [ ] 运行 API 测试确认通过。

### Task 3: Writer 界面输入与结果反馈

**Files:**
- Modify: `creative_os/web/writer.html`
- Modify: `creative_os/web/writer.js`
- Test: `tests/test_writer_word_target.py`

- [ ] 写静态断言测试：页面包含目标字数、允许误差和范围显示；请求体携带字段。
- [ ] 运行测试确认失败。
- [ ] 增加输入控件、范围预览、提交时的字段和完成后的实际字数/达标提示。
- [ ] 保持中文界面、键盘可用和无自动截断。
- [ ] 运行静态测试和现有 Writer 测试。

### Task 4: 回归与验收

**Files:**
- Modify: `docs/superpowers/plans/2026-09-27-agent-word-target-plan.md`

- [ ] 运行 Agent、Writer、Web 相关测试。
- [ ] 启动 8877 工作台，验证 `/writer` 返回 200。
- [ ] 用第 79 章提交一次带目标字数的 Agent 请求，确认任务记录和界面结果。
- [ ] 检查 git diff，不提交或推送，等待用户后续确认。
