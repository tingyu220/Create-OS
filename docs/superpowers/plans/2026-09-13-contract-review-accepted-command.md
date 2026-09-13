# 合同审阅 accepted 命令实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 通过统一 Command Boundary 实现人工接受质量问题的安全写入闭环。

**Architecture:** Web 请求进入 Workspace Command Adapter，先做 DTO/幂等/版本校验，再调用领域审阅服务持久化 `ReviewIssueDisposition(status="accepted")`，发布事件并刷新 Quality Projection；Query Adapter 只读取投影并暴露 freshness 与 trace。

**Tech Stack:** Python 领域模块、现有事件日志/持久化、HTTP Web Workspace、pytest。

## Global Constraints

- 单小说项目；不引入 Portfolio。
- Projection 只读；Web 不得直接访问 Domain、Knowledge、Runtime 或 Projection 实现。
- 首版用户命令只允许 `accepted`，不得接受 `resolved`。
- 不新增大规模领域模型；复用 `ReviewIssueDisposition`、`save_disposition` 和现有刷新器。

### Task 1: 领域命令与事件

**Files:**
- Create: `creative_os/domains/review_issue_command.py`
- Modify: `creative_os/domains/contract_review.py`
- Modify: `creative_os/domains/contract_record_store.py`
- Test: `tests/test_review_issue_command.py`

**Interfaces:** `AcceptReviewIssueCommand`, `accept_review_issue(command, store, event_sink) -> CommandOutcome`。

- [ ] 写测试覆盖成功、缺理由、错误绑定、旧版本、重复幂等键和 `resolved` 拒绝。
- [ ] 运行目标测试确认失败。
- [ ] 复用领域现有校验与 `save_disposition`，成功后写入带 trace 的领域事件。
- [ ] 实现确定性的幂等指纹与冲突结果。
- [ ] 运行目标测试确认通过并提交中文 commit。

### Task 2: Workspace Command Adapter 接入

**Files:**
- Modify: `creative_os/workspace_command_adapter.py`
- Modify: `creative_os/workspace_command.py`
- Modify: `creative_os/web_workspace.py`
- Test: `tests/test_workspace_review_command.py`

**Interfaces:** 新增 `POST /api/commands/accept-review-issue`，请求 DTO 与 receipt 遵循现有刷新命令契约。

- [ ] 写 HTTP 成功、拒绝、冲突、幂等重放测试。
- [ ] 运行测试确认路由不存在或失败。
- [ ] 接入 Task 1 命令，禁止 Adapter 自己重建领域规则。
- [ ] 将事件、审计和 trace 传递给刷新器，返回 projection freshness。
- [ ] 运行目标测试并提交中文 commit。

### Task 3: Quality Projection 与 Query Adapter

**Files:**
- Modify: `creative_os/workspace_projection.py`
- Modify: `creative_os/workspace_query_adapter.py`
- Test: `tests/test_review_projection_query.py`

- [ ] 写 Domain→Event→Projection→Query Adapter 闭环测试。
- [ ] 将 accepted 事实映射为来源可追溯的 Quality DTO。
- [ ] 刷新失败返回 stale/unavailable 与 retry/diagnostic 引用，不伪装为 fresh。
- [ ] 运行目标测试并提交中文 commit。

### Task 4: 跨层回归与文档

**Files:**
- Create: `tests/test_review_command_contract.py`
- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS_REVIEW.md`

- [ ] 验证 Web 只能通过 Adapter、命令不能写 Projection、重复请求不重复产生事实。
- [ ] 运行相关全量测试并记录已知基线失败与新增结果。
- [ ] 更新 API/状态语义文档。
- [ ] 提交中文 commit，准备独立 PR 与审查。
