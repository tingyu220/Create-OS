# 合同审阅 accepted 命令设计

## 背景与目标

为单小说 Web Workspace 增加第一个真实 Novel Domain 写入闭环：人工确认一条质量问题（`accepted`）。写入必须经过 Command Boundary，由领域层持久化审阅事实并发布事件，再刷新只读 Projection。首版不允许用户直接提交 `resolved`；已解决只能来自合同变更后的新审阅证据。

## 边界

- Web 仅调用统一 Workspace Command Adapter，不读取领域内部对象。
- 命令只接受 `accepted`，必须携带问题标识、当前审阅结果绑定、理由、操作者、请求/幂等信息和期望版本。
- 领域层继续以 `ContractReview` 与 `ContractRecordStore` 为事实来源；Projection 不可写。
- 失败必须返回可诊断的拒绝/冲突/失败结果，并保留 trace 与审计引用。
- 事件驱动刷新允许短暂延迟；刷新失败显式暴露 stale/unavailable，不伪装为最新。

## 命令契约

`AcceptReviewIssueCommand` 包含 `command_id`、`request_id`、`actor`、`target(project_id, issue_id)`、`payload(reason, reviewer_result_id, reviewer_result_hash, expected_version)`、`idempotency_key` 与 `trace_id`。校验顺序为：结构与状态 → 绑定与证据 → 版本/幂等 → 领域写入。

结果状态固定为 `accepted`、`rejected`、`conflict`、`failed`，返回 command receipt、审计引用、事件 ID（成功时）和 projection refresh 状态。

## 领域与事件

领域调用现有 `ReviewIssueDisposition` / `save_disposition`，不得在 Adapter 中重建校验。成功后发布一个带 `issue_id`、规范问题哈希、审阅结果哈希、actor、reason 和 trace 的领域事件。重复幂等键返回原 receipt；不同内容复用同一幂等键必须拒绝。

## Projection 与查询

事件映射到 Quality Projection 的问题状态与审计记录。刷新器可全量构建，但接口保留事件增量入口。Query Adapter 返回 accepted 状态、来源引用、事件/命令/trace 标识及 freshness；刷新失败返回 stale 或 unavailable 和 retry 信息。

## 测试与验收

1. 成功命令完成 Domain → Event → Projection → Query Adapter 闭环。
2. `resolved`、缺理由、错误哈希、过期版本被拒绝。
3. 重复请求幂等，冲突请求不覆盖原事实。
4. 刷新失败可诊断、可重试，查询不返回伪最新。
5. Web 只通过 Adapter，不能直接访问领域或 Projection 写接口。

## 非目标

不实现完整编辑器、批量审阅、`resolved` 用户命令、跨项目 Portfolio 或新的大规模领域模型。
