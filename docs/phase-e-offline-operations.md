# Phase E 离线 Gate 运维与证据清单

本清单是 Phase E 离线验收的操作入口，不生成正文，也不授权真实模型调用。

## 权威输入与边界

- 项目 brief/schema/readiness：`projects/文明升阶/brief.json`、`.creative_os/readiness/`；readiness 必须 exact 绑定激活 engagement plan、projection、Ledger head 与 Curve。
- Engagement projection：Director 只能消费 ACTIVE projection；Writer/Orchestrator 不写 Ledger。
- Ledger/Curve/Foreshadow：Expectation Ledger 记录期待状态与人工 transition；Curve 记录张弛与因果证据；Foreshadow 仅为故事线索，不能替代 payoff 或自动关闭期待。

## Orchestrator 状态与人工操作

状态链由 `ChapterRunCheckpointStore` 追加保存：`awaiting_readiness_approval → readiness_approved → director_proposed → engagement_reviewed → fulfillment_recorded`。人工审批包括 readiness、Engagement Review、State decision/materialization；缺失或漂移统一阻断，常见错误码为 `approval_required`、`artifact_hash`、`fulfillment_state`、`tampered`、`record_id_conflict`。

## Store 备份与恢复

所有 authority Store 使用 canonical JSONL、head/journal 与 SHA-256 链。运维恢复顺序：停止写入 → 复制 `.creative_os/` 目录备份 → 调用 owner `recover()` exact 重读 → 校验 head/journal → 仅在人工确认后重试。篡改、部分追加或 head 不一致必须 fail-closed，不删除原记录。

## Writer 出口与机械扫描

`creative_os/domains/chapter_production_owner_registry.py` 的 `production_exit_manifest()` 是唯一出口清单；`validate_production_exit_manifest()` 机械扫描 Writer/Promotion 符号。CLI 直达 Writer 默认拒绝，必须由 Orchestrator 进入。Token、grant、context fingerprint、run_id、binding 任一错误均应零副作用。

## 离线验收记录

- A Gate：Reader Engagement Foundation 全绿。
- B Tasks 0–8：真实 CompositionRoot 十章、Fulfillment、State、CLI 与故障矩阵全绿。
- B Task 9：本文件与 roadmap 状态更新后执行文档清单机械检查。
- 真实校准：暂停等待人工批准，不在离线阶段调用模型或生成正文。
