# Phase E Chapter Production Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Reader Engagement 权威 Gate 之上实现逐章可暂停、可恢复、零重复副作用的生产编排，并完成 Fake Writer 十章离线闭环。

**Architecture:** 单一 `ChapterProductionOrchestrator` 用追加式 checkpoint 协调 readiness、Director/Lifecycle、Admission/Context、受保护 Writer 出口、Engagement/质量 Review、Fulfillment、Expectation/State 审批和下一章 Baseline。它只重读与编排现有 owner；真实模型阶段仅暴露授权后入口，本计划不执行模型。

**Tech Stack:** Python 3.12、现有 Phase A–D 合同/Admission/Writer/Fulfillment/State 组件、Phase E-A Reader Engagement APIs、canonical JSON/SHA-256、pytest、AST 架构清单。

**Spec:** `docs/superpowers/specs/2026-08-22-phase-e-web-novel-production-quality-gate-design.md`

## Global Constraints

- 前置条件：`2026-08-22-reader-engagement-foundation.md` 的 Phase E-A Exit Gate 全部 PASS；本计划不得补建或替代 A 的模型、Store、Planning、Ledger、Curve、Review。
- 不生成小说正文、不调用真实模型、不自动审批，不执行 E-D 真实校准。
- Orchestrator 不拥有故事/engagement 事实，不接受调用方 PreparedWriterRun、Baseline 事实或审批对象。
- 每个外部副作用前锁内 exact 重读；模型调用不持锁；prepared/receipt/idempotency 解决崩溃与重复。
- 所有 B 阶段 owner 必须实现 Task 1 lock-aware internal 方法并验证同一 `LockContext`；Orchestrator 禁止嵌套获取 owner 私有锁。
- grant 不进入生产出口；最终 token 绑定实际 project/chapter/contract/projection/context/run/authority state。
- Fake Writer 十章必须逐章真实构建 Context/Prepared run，并在每章关闭重开全部 Store；禁止预制十份 PreparedWriterRun 或十章 engagement projection。
- CLI 正式与兼容入口只走 Orchestrator；不得保留直达 Writer/promotion/final sink。
- 不新增 UI、多 Agent、Style Reference、第二事实源、通用平台、撤销服务、历史库或无关重构。
- Reader Feedback/Performance/反馈驱动 Revision 延后；本阶段只实现 staging/final 发布边界。
- 每 Task 严格 RED→GREEN→相关回归→独立复审→中文本地提交；不得推送、合并或创建 PR。

## File Structure

- `production_readiness.py`：E-B manifest/audit/approval 与 exact adapter 组合。
- `production_readiness_store.py`：readiness audit/approval 权威追加式持久化。
- `chapter_run_checkpoint.py`：状态、checkpoint、view/error 纯模型。
- `chapter_run_checkpoint_store.py`：追加式 checkpoint/journal/recovery。
- `project_authority_transaction.py`：统一项目锁、LockContext 与 lock-aware owner 协议。
- `chapter_production_orchestrator.py`：单步状态协调器。
- `writer_execution_reconciliation.py`：ambiguous provider 结果的人工对账决定。
- `writer_execution_authority_store.py`：intent、本地 MAC receipt、人工对账决定唯一权威 Store。
- `web_novel_quality.py`：确定性 hard Gate 与人工文学质量记录。
- `web_novel_quality_store.py`：Hard result/人工 Review 权威追加式持久化。
- `state_change_approval.py`：State candidate 决策和物化授权。
- `state_change_authority_store.py`：State decision/materialization receipt 权威持久化。
- `novel_production_cli.py`：正式 CLI；旧 scripts 仅兼容转发。
- `chapter_production_owner_registry.py`：生产组合根导出的真实持久 owner 清单。
- `tests/fakes/fake_chapter_writer.py`：受 Admission 的十章差异化测试 adapter，不含正文。

---

### Task 0: 机械验证 Phase E-A Exit Gate

**Files:**
- Create: `tests/test_phase_e_a_exit_gate.py`

**Interfaces:**
- Consumes: 计划 A 的 `evaluate_reader_engagement_exit_gate` 与非持久化 `ReaderEngagementExitGateResult`，以及冻结架构清单。
- Produces: B 阶段测试 fixture `require_phase_e_a_gate(project_root: Path) -> ReaderEngagementExitGateResult`，每次只调用 A evaluator；失败抛 `PhaseEAPrerequisiteError`，不写生产模块、不缓存 result。

- [ ] **Step 1: 写缺组件/未全绿/权限逃逸 RED**

```python
def test_b_cannot_create_readiness_or_run_when_a_gate_fails(tmp_path):
    with pytest.raises(PhaseEAPrerequisiteError):
        require_phase_e_a_gate(tmp_path)
    assert not (tmp_path / ".creative_os" / "production-runs").exists()
```

- [ ] **Step 2: 实现机械清单**

每次检查 A 的 schema versions、ACTIVE plan/activation binding、Ledger/Curve exact、projection round-trip、唯一 EvidenceRef、Director/Writer/Orchestrator 无 Ledger 写权限，以及计划 A 冻结测试清单；不读取或写入任何持久化 Gate 记录。失败不得创建 Readiness 或 run；本 Task 只验证，不补 A 能力。

- [ ] **Step 3: Gate、独立复审、提交**

Run: `python -m pytest tests/test_phase_e_a_exit_gate.py tests/test_reader_engagement_model.py tests/test_reader_engagement_store.py tests/test_expectation_ledger.py tests/test_reader_engagement_planning.py tests/test_engagement_review.py -q`
Expected: PASS。

```bash
git add tests/test_phase_e_a_exit_gate.py
git commit -m "test: 冻结读者吸引力阶段出口"
```

### Task 1: 统一 Project Authority Transaction 与锁身份

**Files:**
- Create: `creative_os/domains/project_authority_transaction.py`
- Modify: `creative_os/domains/reader_engagement_store.py`
- Modify: `creative_os/domains/contract_record_store.py`
- Modify: `creative_os/domains/contract_fulfillment_store.py`
- Create: `tests/test_project_authority_transaction.py`

**Interfaces:**
- Consumes: 现有 contract/engagement authority lock primitives。
- Produces: `ProjectAuthorityTransaction(project_root)`；`LockContext(project_id, lock_id, owner_thread, process_id)`；owner 的 `*_locked(lock_context, ...)` 内部方法约定。

- [ ] **Step 1: 写锁身份/嵌套/跨进程 RED**

```python
def test_nested_or_foreign_lock_context_is_rejected(transaction):
    with transaction.acquire() as context:
        with pytest.raises(ProjectAuthorityLockError):
            transaction.acquire()
        with pytest.raises(ProjectAuthorityLockError):
            owner.load_exact_locked(foreign_context(), "id", HASH)
```

- [ ] **Step 2: 实现单一项目事务锁**

`acquire()` 创建不可伪造的进程内 lock identity，并持有现有跨进程项目锁。为 ReaderEngagement、ContractRecord、Fulfillment 三个既有 owner 增加不改变领域行为的 lock-aware internal read/append 方法；public 方法自行开事务，Orchestrator 只在外层事务中调用 internal 方法。internal 必须验证 project/lock/thread/process identity，禁止再次获取同项目锁；这只是 B 的组合事务适配，不新增 A schema/Planning 能力。

- [ ] **Step 3: 定义领域记录先写、checkpoint 后写恢复协议**

每次 transition 先写带 `orchestration_operation_id` 的领域 record，再写 checkpoint；若中间崩溃，resume 在同锁内按 operation ID exact 找到领域 record、验证 authority binding 后幂等补 checkpoint。不存在/多条/异 hash 均阻断。

- [ ] **Step 4: 并发与恢复 Gate**

两进程竞争同 run 只有一个 transition 成功；嵌套锁、错误 context、领域 record 已写而 checkpoint 未写、checkpoint 已写但领域 record 缺失分别测试。

- [ ] **Step 5: 独立复审并提交**

Run: `python -m pytest tests/test_project_authority_transaction.py tests/test_contract_record_store.py tests/test_reader_engagement_store.py -q`
Expected: PASS。

```bash
git add creative_os/domains/project_authority_transaction.py creative_os/domains/reader_engagement_store.py creative_os/domains/contract_record_store.py creative_os/domains/contract_fulfillment_store.py tests/test_project_authority_transaction.py
git commit -m "feat: 统一项目权威事务锁"
```

### Task 2: E-B Production Readiness Authority

**Files:**
- Create: `creative_os/domains/production_readiness.py`
- Create: `creative_os/domains/production_readiness_store.py`
- Create: `tests/test_production_readiness.py`
- Create: `tests/test_production_readiness_store.py`
- Modify: `creative_os/domains/contract_baseline_resolver.py`
- Modify: `tests/test_contract_baseline_resolver.py`

**Interfaces:**
- Consumes: Task 0 每次新求值的 `ReaderEngagementExitGateResult`、E-A `ReaderEngagementStore.active_plan/ledger_head/load_exact`、`EngagementCurve`; existing `AuthorityRoleAdapter.read_exact`。
- Produces: `ReadinessRole`, `ProductionReadinessManifest`, `ProductionReadinessAuditResult`, `ReadinessApproval`; `ProductionReadinessStore.append_audit/append_approval/load_exact/recover` 及对应 `*_locked(lock_context, ...)`；`ProductionReadinessService.audit(project_root, manifest)`, `approve(audit_hash, actor, reason)`, `load_ready_snapshot(project_root)`。

- [ ] **Step 1: 写缺失/空 brief/stale RED**

```python
def test_empty_genre_and_logline_block_before_chapter_run(civilization_project):
    result = service.audit(civilization_project, manifest())
    assert result.status == ReadinessStatus.BLOCKED
    assert {i.code for i in result.issues} >= {"genre_missing", "logline_missing"}
```

覆盖 commercial_positioning、story_promise、protagonist_growth、information_state、narrative_thread、active_engagement_plan、ledger_head、curve 的缺失、重复、unknown、wrong version/hash、source_not_versioned。

`ProductionReadinessService` 每次调用的第一项前置检查必须重新运行 Task 0 evaluator；result 非 PASS 时在创建 audit/approval/run 文件前失败，不持久化或比较旧 Gate result。

- [ ] **Step 2: 运行 RED 并实现 strict models/service**

Run: `python -m pytest tests/test_production_readiness.py -q`
Expected: FAIL because module is absent。Manifest 只保存 binding，不承载解析对象；approval exact 绑定 audit hash。

- [ ] **Step 3: 接入显式 authority adapters**

```python
class EngagementPlanAuthorityAdapter:
    def read_exact(self, project_root: Path, entry: BaselineEntry) -> AuthorityRead:
        raise NotImplementedError
```

分别为 active plan、Ledger head、Curve 注册只读 adapter；无 exact 能力直接 `source_not_versioned`，禁止 latest fallback。

- [ ] **Step 4: 重启与漂移 Gate**

`ProductionReadinessStore` 复用 canonical envelope/head/journal、可信句柄、no-follow、file/dir fsync 和项目锁；audit/approval 为追加记录，approval 绑定 audit/ruleset/previous head/actor/time/reason/decision hash。关闭重开 Readiness/Engagement Store 后 exact 重读成功；并发、篡改、各 I/O fault 可恢复。Plan/Ledger/Curve 任一变化使旧 audit/approval stale，且不创建章节 run。

- [ ] **Step 5: 回归、独立复审、提交**

Run: `python -m pytest tests/test_project_authority_transaction.py tests/test_production_readiness.py tests/test_production_readiness_store.py tests/test_contract_baseline_resolver.py tests/test_reader_engagement_store.py -q`
Expected: PASS。

```bash
git add creative_os/domains/production_readiness.py creative_os/domains/production_readiness_store.py creative_os/domains/contract_baseline_resolver.py tests/test_production_readiness.py tests/test_production_readiness_store.py tests/test_contract_baseline_resolver.py
git commit -m "feat: 增加章节生产准备度门禁"
```

### Task 3: Chapter Run 模型与追加式 Checkpoint Store

**Files:**
- Create: `creative_os/domains/chapter_run_checkpoint.py`
- Create: `creative_os/domains/chapter_run_checkpoint_store.py`
- Create: `tests/test_chapter_run_checkpoint.py`
- Create: `tests/test_chapter_run_checkpoint_store.py`

**Interfaces:**
- Consumes: no domain write owner。
- Produces: `ChapterRunState`, `ChapterRunCheckpoint`, `OrchestrationView`, `OrchestrationError`; `ChapterRunCheckpointStore.append/load_run/current/recover` 及对应 `*_locked(lock_context, ...)`；不再暴露第二个 project lock。

- [ ] **Step 1: 写状态机 RED**

```python
def test_checkpoint_rejects_skipping_writer_and_quality_states():
    with pytest.raises(CheckpointError, match="invalid_transition"):
        checkpoint.advance(ChapterRunState.CHAPTER_COMMITTED)
```

逐项冻结 spec 状态、暂停态、阻断态；sequence、previous/checkpoint/authority hash、refs、idempotency key 精确校验。

- [ ] **Step 2: 运行 RED 并实现纯模型**

Run: `python -m pytest tests/test_chapter_run_checkpoint.py -q`
Expected: FAIL；实现显式 transition table，不用枚举顺序隐式放行。

- [ ] **Step 3: 写 Store RED 并实现**

复用 authority Store 的可信句柄/no-follow/锁策略；canonical records/head/journal、链 hash、file/dir fsync、exact schema。

- [ ] **Step 4: 故障/篡改/并发恢复**

覆盖 prepared/head/record 的写、replace、fsync、unlink 故障；删尾/截断/重排/CRLF/重复 key/祖先替换拒绝；两进程同 checkpoint 幂等，异内容冲突。

- [ ] **Step 5: Gate、复审、提交**

Run: `python -m pytest tests/test_project_authority_transaction.py tests/test_chapter_run_checkpoint.py tests/test_chapter_run_checkpoint_store.py tests/test_contract_record_store.py -q`
Expected: PASS。

```bash
git add creative_os/domains/chapter_run_checkpoint.py creative_os/domains/chapter_run_checkpoint_store.py tests/test_chapter_run_checkpoint.py tests/test_chapter_run_checkpoint_store.py
git commit -m "feat: 增加逐章生产检查点存储"
```

### Task 4: Orchestrator 前写作状态链

**Files:**
- Create: `creative_os/domains/chapter_production_orchestrator.py`
- Create: `tests/test_chapter_production_orchestrator_prewrite.py`

**Interfaces:**
- Consumes: Readiness Task 1、E-A `project_chapter`、`NarrativeDirector.propose`、`ContractLifecycleCoordinator`、`WriterAdmissionService.pre_admit`、`ContextCompiler.compile/finalize_admission`。
- Produces: `ChapterProductionOrchestrator.start/advance/resume/inspect`；推进至 `ADMITTED`，每次只跨一个副作用边界。

- [ ] **Step 1: 写人工暂停与调用方注入拒绝 RED**

```python
def test_start_stops_before_director_when_readiness_or_plan_not_active(orchestrator):
    view = orchestrator.start("project", 1)
    assert view.state == ChapterRunState.AWAITING_READINESS_APPROVAL
    assert writer.calls == 0
```

API 不提供 PreparedWriterRun/Baseline/approval 参数；pending revision、Reviewer/disposition、stale plan/ledger/curve 均在创建 grant 前阻断。

- [ ] **Step 2: 运行 RED 并实现依赖注入组合根**

Run: `python -m pytest tests/test_chapter_production_orchestrator_prewrite.py -q`
Expected: FAIL。Orchestrator 构造函数接受真实 owner 类型/Protocol，但不读取其私有文件。

- [ ] **Step 3: 锁内 authority_state_hash**

每步锁内 exact 重读 readiness、plan/projection/ledger/curve、contract pointer/baseline/approval/reviewer/rules/dispositions；hash 只保存 refs，不复制事实。释放锁前追加 checkpoint。

- [ ] **Step 4: 两阶段 Admission 正路径/漂移负测**

pre_admit→真实 Context fingerprint→finalize；compile 后 plan/ledger/contract 漂移时 token 不签发。重复 advance 返回同 checkpoint。

- [ ] **Step 5: Gate、复审、提交**

Run: `python -m pytest tests/test_project_authority_transaction.py tests/test_chapter_run_checkpoint.py tests/test_chapter_run_checkpoint_store.py tests/test_chapter_production_orchestrator_prewrite.py tests/test_contract_lifecycle_initial.py tests/test_writer_admission.py tests/test_context_compiler.py -q`
Expected: PASS。

```bash
git add creative_os/domains/chapter_production_orchestrator.py tests/test_chapter_production_orchestrator_prewrite.py
git commit -m "feat: 编排章节写作前权威门禁"
```

### Task 5: Writer prepared/receipt 与 staged artifact 恢复

**Files:**
- Modify: `creative_os/domains/chapter_run_checkpoint.py`
- Modify: `creative_os/domains/chapter_production_orchestrator.py`
- Modify: `creative_os/novel_continuation_runner.py`
- Create: `creative_os/domains/writer_execution_reconciliation.py`
- Create: `creative_os/domains/writer_execution_authority_store.py`
- Create: `tests/test_chapter_writer_execution_recovery.py`
- Create: `tests/test_writer_execution_authority_store.py`
- Modify: `tests/test_writer_production_exit_architecture.py`
- Modify: `tests/assets/writer_production_exits_v1.json`

**Interfaces:**
- Consumes: `prepare_continuation_run`, `continue_one_chapter(prepared: PreparedWriterRun, client: ContinuationClient | None)`, final Admission token。
- Produces: `WriterExecutionIntent`, `WriterExecutionReceipt`, `WriterExecutionReconciliationDecision`, staged artifact ref；唯一 owner `WriterExecutionAuthorityStore.append_intent/append_local_receipt/append_reconciliation_decision/load_exact/recover` 及对应 `*_locked(lock_context, ...)`；`prepare_writer(run_id)`；`record_reconciliation_decision(run_id, decision_id)`。Ambiguous 恢复不接受裸 receipt。

- [ ] **Step 1: 写无 prepared/错误 token/ambiguous RED**

```python
def test_ambiguous_result_never_reinvokes_writer(orchestrator, fake_writer):
    orchestrator.advance_to_writer_prepared(run_id)
    fake_writer.raise_after_side_effect = True
    assert orchestrator.advance(run_id).state == ChapterRunState.AMBIGUOUS_EXTERNAL_RESULT
    orchestrator.resume(run_id)
    assert fake_writer.calls == 1
```

- [ ] **Step 2: 实现 prepared intent 后释放锁调用**

Intent exact 绑定 request/task/projection/context/token run、attempt、idempotency key；调用后重新加锁重读 authority，生成本地 MAC `WriterExecutionReceipt`，可附带但不信任可选 provider metadata，以兼容现有 `ContinuationClient.complete()` 的 string/TimedCompletion 返回。未知结果只允许人工追加 `WriterExecutionReconciliationDecision`，其 ID 绑定 actor/reason/provider request ID/provider result hash/previous authority hash；resume 锁内 exact 重读 decision，禁止调用方传裸 receipt。

`WriterExecutionAuthorityStore` 是 intent、本地 receipt、reconciliation decision 的唯一 owner，使用 exact schema、canonical chain/head/journal、可信句柄、file/dir fsync 与 Task 1 lock-aware 方法。覆盖重启、篡改、并发、所有 write/replace/fsync/unlink fault；checkpoint 不保存这些 payload。

- [ ] **Step 3: staged/final 边界**

Writer 只产生 staged artifact；现有受保护 promotion 仍是唯一 final sink。更新出口 JSON manifest/AST 测试，禁止新模型/写文件 sink 绕过。

- [ ] **Step 4: 六类无效 token 零副作用参数测试**

no token、grant、旧 token、wrong authority/context/run/project/chapter 以及篡改 Prepared task/projection 均不得调用 client、写 staged/final 或追加 receipt。

- [ ] **Step 5: Gate、复审、提交**

Run: `python -m pytest tests/test_project_authority_transaction.py tests/test_chapter_run_checkpoint.py tests/test_chapter_run_checkpoint_store.py tests/test_chapter_production_orchestrator_prewrite.py tests/test_writer_execution_authority_store.py tests/test_chapter_writer_execution_recovery.py tests/test_writer_run_continuation.py tests/test_writer_production_exit_architecture.py -q`
Expected: PASS。

```bash
git add creative_os/domains/chapter_run_checkpoint.py creative_os/domains/chapter_production_orchestrator.py creative_os/domains/writer_execution_reconciliation.py creative_os/domains/writer_execution_authority_store.py creative_os/novel_continuation_runner.py tests/assets/writer_production_exits_v1.json tests/test_writer_execution_authority_store.py tests/test_chapter_writer_execution_recovery.py tests/test_writer_production_exit_architecture.py
git commit -m "feat: 增加写作执行回执与恢复"
```

### Task 6: Orchestrator 权威 Engagement Review 阶段

**Files:**
- Modify: `creative_os/domains/chapter_production_orchestrator.py`
- Create: `tests/test_orchestrated_engagement_review.py`

**Interfaces:**
- Consumes: A `EngagementReviewer.review`, `OpeningCheckpointReviewService`, `ReaderEngagementStore.append_engagement_review/load_exact`；真实 staged artifact、active plan、Ledger head、Curve、Context。
- Produces: checkpoint `ENGAGEMENT_REVIEWED` 或 `ENGAGEMENT_REVIEW_BLOCKED`；不接受调用方 Review 参数。

- [ ] **Step 1: 写临时 Review 注入/BLOCKED/幂等 RED**

```python
def test_orchestrator_builds_and_reloads_authoritative_engagement_review(orchestrator):
    view = orchestrator.advance(writer_completed_run)
    assert view.state == ChapterRunState.ENGAGEMENT_REVIEWED
    assert engagement_store.load_exact("engagement_review", view.review_id,
                                       view.review_hash).status == "passed"
```

公开 advance/resume 不接受 `EngagementReviewResult`；错误 artifact/plan/ledger/curve/context、BLOCKED review 都不得进入 Hard Gate。

- [ ] **Step 2: 实现锁内 owner 调用和 exact 重读**

Orchestrator 从 checkpoint refs exact 重读所有输入，调用 Reviewer owner，追加 review 后再按 ID/hash exact 重读，绑定新 authority_state_hash。重复 resume 复用同一 record；partial append 关闭重开后恢复，不重复 review。

- [ ] **Step 3: 1/3/6/10 人工 opening checkpoint**

适用章节自动 review PASS 后仍停在人工记录等待态；exact 重读 A 的 `OpeningCheckpointReviewRecord/Decision` 后才能追加 `ENGAGEMENT_REVIEWED`。自动 review、文学评分或 Fulfillment 不能替代。

- [ ] **Step 4: 累计回归、复审、提交**

Run: `python -m pytest tests/test_project_authority_transaction.py tests/test_orchestrated_engagement_review.py tests/test_chapter_run_checkpoint.py tests/test_chapter_run_checkpoint_store.py tests/test_chapter_production_orchestrator_prewrite.py tests/test_chapter_writer_execution_recovery.py tests/test_engagement_review.py -q`
Expected: PASS。

```bash
git add creative_os/domains/chapter_production_orchestrator.py tests/test_orchestrated_engagement_review.py
git commit -m "feat: 编排权威吸引力审查"
```

### Task 7: Web Novel Hard Gate 与人工文学质量 Review

**Files:**
- Create: `creative_os/domains/web_novel_quality.py`
- Create: `creative_os/domains/web_novel_quality_store.py`
- Create: `tests/test_web_novel_quality.py`
- Create: `tests/test_web_novel_quality_store.py`
- Modify: `creative_os/domains/chapter_production_orchestrator.py`

**Interfaces:**
- Consumes: staged artifact metadata、Chapter Contract、Baseline/State、E-A EngagementReview。
- Produces: `HardGateVerdict`, `WebNovelHardGateResult`, `HumanReadingQualityReview`; `WebNovelQualityGate.evaluate(inputs)`；`WebNovelQualityStore.append_hard_result/append_human_review/load_exact/recover` 及对应 `*_locked(lock_context, ...)`。

- [ ] **Step 1: 写 hard/soft 分离 RED**

```python
def test_human_high_score_cannot_override_unknown_hard_evidence():
    hard = gate.evaluate(inputs(exact_evidence=()))
    assert hard.status == HardGateStatus.BLOCKED
    assert coordinator.can_promote(hard, excellent_human_review()) is False
```

覆盖主动选择/代价、Arc 推进、冲突升级、期待生命周期、状态变化、因果 hook、一致性、拖沓/旁观/突兀 payoff/重复功能。

- [ ] **Step 2: 实现确定性 Gate**

UNKNOWN 为 blocking；只接受结构化 exact evidence 与版本化 semantic asset，不用关键词、不调用模型自评。

- [ ] **Step 3: 人工文学 Review 严格模型**

绑定 artifact/context/contract/ruleset hash；六项评分、逐项理由、disposition。E-A EngagementReview、Fulfillment、Consistency verdict 均不能代替它。

- [ ] **Step 4: 实现质量权威追加式 Store**

Hard result 与人工 Review 使用 canonical exact envelope/head/journal、可信句柄/no-follow、file/dir fsync 和项目锁；人工记录绑定 reviewed hash、ruleset、previous head、actor/time/reason/decision hash。覆盖关闭重开、并发、篡改和每个 I/O fault；checkpoint 只引用 record ID/hash，不能冒充 Review。

- [ ] **Step 5: Orchestrator 暂停/晋升接线**

Hard PASS 后停在 `AWAITING_QUALITY_REVIEW`；人工 APPROVED 后才调用受保护 promotion。失败 artifact 保持 staged，不覆盖 final。

- [ ] **Step 6: Gate、复审、提交**

Run: `python -m pytest tests/test_project_authority_transaction.py tests/test_chapter_run_checkpoint.py tests/test_chapter_run_checkpoint_store.py tests/test_chapter_production_orchestrator_prewrite.py tests/test_chapter_writer_execution_recovery.py tests/test_orchestrated_engagement_review.py tests/test_web_novel_quality.py tests/test_web_novel_quality_store.py tests/test_narrative_semantics.py tests/test_engagement_review.py tests/test_writer_production_exit_architecture.py -q`
Expected: PASS。

```bash
git add creative_os/domains/web_novel_quality.py creative_os/domains/web_novel_quality_store.py creative_os/domains/chapter_production_orchestrator.py tests/test_web_novel_quality.py tests/test_web_novel_quality_store.py
git commit -m "feat: 增加网文质量双轨门禁"
```

### Task 8: Fulfillment 接入生产成功判定

**Files:**
- Modify: `creative_os/domains/chapter_production_orchestrator.py`
- Modify: `creative_os/domains/contract_fulfillment.py`
- Create: `creative_os/domains/contract_fulfillment_reviewer.py`
- Create: `tests/test_orchestrated_fulfillment.py`

**Interfaces:**
- Consumes: `ContractFulfillmentStore.append/active_records`, `ContractFulfillmentEvaluator.evaluate`, final artifact metadata 与结构化 exact evidence。
- Produces: `ContractFulfillmentReviewer.append_verified_records(contract, artifact, evidence) -> tuple[ContractFulfillmentEvidenceRecord, ...]`；checkpoint `FULFILLMENT_RECORDED`；`FulfillmentAuthorityBinding`。

- [ ] **Step 1: 写 incomplete/stale/错误工件 RED**

```python
def test_state_candidates_not_created_until_fulfillment_is_exact(orchestrator):
    view = orchestrator.advance(run_with_stale_fulfillment)
    assert view.state == ChapterRunState.FULFILLMENT_INCOMPLETE
    assert state_compiler.calls == 0
```

- [ ] **Step 2: 实现真实 Reviewer owner 追加**

Quality APPROVED 后 Orchestrator 锁内 exact 重读 final artifact metadata、合同全部叶和结构证据，调用 `ContractFulfillmentReviewer` 逐项 append verification/realization。Reviewer 只能写真实 `ContractFulfillmentStore`，每条 evidence exact 绑定 source ID/version/hash/asserted value；禁止测试预置 active records 冒充闭环。

- [ ] **Step 3: 关闭重开后重读再 evaluate**

销毁 Reviewer/Store，重建 `ContractFulfillmentStore`，重读 active records 后调用 Evaluator。只有 final artifact 的 verification+realization 闭合且无 stale record 才追加 binding/checkpoint；不改冻结合同或审批记录。

- [ ] **Step 4: supersede/部分追加/零重复测试**

覆盖 verification 已写而 realization 失败、同记录重复、异内容冲突、supersede、错误 artifact/source/hash/asserted value。恢复后补齐缺项但不重复已有记录；重复 resume 零新 record，篡改 final metadata 阻断。

- [ ] **Step 5: 累计 Gate、复审、提交**

Run: `python -m pytest tests/test_project_authority_transaction.py tests/test_chapter_run_checkpoint.py tests/test_chapter_run_checkpoint_store.py tests/test_chapter_production_orchestrator_prewrite.py tests/test_chapter_writer_execution_recovery.py tests/test_orchestrated_engagement_review.py tests/test_web_novel_quality.py tests/test_web_novel_quality_store.py tests/test_orchestrated_fulfillment.py tests/test_contract_fulfillment.py tests/test_contract_fulfillment_store.py -q`
Expected: PASS。

```bash
git add creative_os/domains/chapter_production_orchestrator.py creative_os/domains/contract_fulfillment.py creative_os/domains/contract_fulfillment_reviewer.py tests/test_orchestrated_fulfillment.py
git commit -m "feat: 将合同兑现接入章节生产"
```

### Task 9: Expectation 与 State 审批、物化、下一 Baseline

**Files:**
- Create: `creative_os/domains/state_change_approval.py`
- Create: `creative_os/domains/state_change_authority_store.py`
- Modify: `creative_os/domains/novel_chapter_memory.py`
- Modify: `creative_os/domains/novel_state_store.py`
- Modify: `creative_os/domains/chapter_production_orchestrator.py`
- Create: `tests/test_orchestrated_state_materialization.py`
- Create: `tests/test_state_change_authority_store.py`

**Interfaces:**
- Consumes: E-A transition compiler/materializer；`compile_chapter_candidates`, `materialize_active_state`, `BaselineManifest`。
- Produces: `StateChangeDecisionRecord`, `StateMaterializationReceipt`; `StateChangeAuthorityStore.append_decision/append_receipt/load_exact/recover` 及对应 `*_locked(lock_context, ...)`; `StateChangeApprovalService.approve/reject/materialize`; next Baseline binding。

- [ ] **Step 1: 写未审批不物化 RED**

```python
def test_pending_expectation_or_state_decision_blocks_next_baseline(orchestrator):
    view = orchestrator.advance(run_after_fulfillment)
    assert view.state in {ChapterRunState.AWAITING_EXPECTATION_TRANSITION_APPROVAL,
                          ChapterRunState.AWAITING_STATE_APPROVAL}
    assert baseline_store.records_for_next_chapter() == ()
```

- [ ] **Step 2: 实现严格 decision/receipt**

State decision exact 绑定 candidate/final/contract/fulfillment/ruleset/previous head、actor/time/reason/decision hash；只有 APPROVED Memory item 可物化。“待人工补充”和 generic candidate 不自动 ACTIVE。

- [ ] **Step 3: 实现 State decision/receipt 权威 Store**

canonical exact envelope/head/journal、可信句柄/no-follow、file/dir fsync、项目锁；decision 与 materialization receipt 均追加保存并 exact 重读。覆盖并发、篡改、重启和各 I/O fault；checkpoint 只能引用 ID/hash。

- [ ] **Step 4: 顺序接线与恢复**

先物化 E-A Ledger transitions，再 State；exact 重读 snapshots 后构建下一 BaselineManifest。Ledger/State 任一步 partial failure 关闭重开后幂等补齐，不产生双 snapshot。

- [ ] **Step 5: drift/冲突/上一章门禁**

旧 Ledger head、candidate hash、final hash、State merge conflict 阻断；下一章 start 必须观察上一章 `CHAPTER_COMMITTED` 和 exact next baseline。

- [ ] **Step 6: 累计 Gate、复审、提交**

Run: `python -m pytest tests/test_project_authority_transaction.py tests/test_chapter_run_checkpoint.py tests/test_chapter_run_checkpoint_store.py tests/test_chapter_production_orchestrator_prewrite.py tests/test_chapter_writer_execution_recovery.py tests/test_orchestrated_engagement_review.py tests/test_web_novel_quality.py tests/test_web_novel_quality_store.py tests/test_orchestrated_fulfillment.py tests/test_orchestrated_state_materialization.py tests/test_state_change_authority_store.py tests/test_novel_chapter_memory.py tests/test_novel_state_store.py tests/test_expectation_ledger.py tests/test_contract_baseline.py -q`
Expected: PASS。

```bash
git add creative_os/domains/state_change_approval.py creative_os/domains/state_change_authority_store.py creative_os/domains/novel_chapter_memory.py creative_os/domains/novel_state_store.py creative_os/domains/chapter_production_orchestrator.py tests/test_orchestrated_state_materialization.py tests/test_state_change_authority_store.py
git commit -m "feat: 闭环章节状态审批与下一基线"
```

### Task 10: 正式 CLI 与旧入口收口

**Files:**
- Create: `creative_os/novel_production_cli.py`
- Modify: `scripts/continue_novel.py`
- Modify: `scripts/run_llm_writer_pilot.py`
- Create: `tests/test_novel_production_cli.py`
- Modify: `tests/test_writer_production_exit_architecture.py`
- Modify: `tests/assets/writer_production_exits_v1.json`

**Interfaces:**
- Consumes: `ChapterProductionOrchestrator.start/advance/resume/inspect`, readiness/engagement status。
- Produces: `main(argv) -> int`; formal commands `readiness`, `engagement status`, `start`, `advance`, `resume`, `status`。

- [ ] **Step 1: 写参数迁移 RED**

```python
def test_legacy_force_and_direct_writer_paths_are_rejected(monkeypatch):
    assert main(["resume", "--force"]) == 2
    assert direct_writer.calls == 0
```

- [ ] **Step 2: 实现正式 CLI 和薄兼容层**

`--target-chinese-chars` 要求合同 revision；`--promote-draft` 只 resume；`--chapters` 顺序 start 且上一章 committed 后才继续；`--force` 拒绝；`--local-repair` 创建新 attempt。

- [ ] **Step 3: AST/manifest 冻结出口**

扫描所有 model client、promotion/publish、staged/final write/open/replace/copy 定义与调用；internal sink 唯一 caller 为验证 token 的公开 wrapper。CLI/compat scripts 禁止导入 `_impl`、guard 或直接 Writer client。

- [ ] **Step 4: Gate、复审、提交**

Run: `python -m pytest tests/test_novel_production_cli.py tests/test_writer_production_exit_architecture.py tests/test_writer_run_continuation.py -q`
Expected: PASS。

```bash
git add creative_os/novel_production_cli.py scripts/continue_novel.py scripts/run_llm_writer_pilot.py tests/test_novel_production_cli.py tests/test_writer_production_exit_architecture.py tests/assets/writer_production_exits_v1.json
git commit -m "feat: 统一逐章生产命令入口"
```

### Task 11: Fake Writer 十章完整闭环

**Files:**
- Create: `tests/fakes/fake_chapter_writer.py`
- Create: `tests/fakes/phase_e_owner_registry.py`
- Create: `creative_os/domains/chapter_production_owner_registry.py`
- Create: `tests/test_phase_e_fake_ten_chapters.py`
- Create: `tests/test_phase_e_restart_gate.py`

**Interfaces:**
- Consumes: Tasks 0–10 public APIs and E-A public APIs。
- Produces: deterministic `FakeChapterArtifact(metadata, structured_evidence)`；十章离线验收报告 fixture。

- [ ] **Step 1: 写“禁止预制十份 run/projection”架构 RED**

AST/spy 证明每章只在上一章 committed 后调用 `project_chapter`、Context compile、pre/final admission；测试对象中不存在十元素 PreparedWriterRun/projection 列表。

- [ ] **Step 2: 实现十个差异化非正文 fake artifact**

每章仅提供 metadata、结构化 choice/cost/arc/conflict/expectation/state/hook evidence 和稳定 artifact hash；不包含小说段落，不调用模型。

- [ ] **Step 3: 实现 1–10 章场景矩阵**

依次覆盖 opening/readiness 等待、合同审批、3/6/10 payoff、Context 崩溃、ambiguous receipt、Plan/Ledger/Curve/Baseline drift、Fulfillment supersede、Expectation transition、State materialize、下一 Baseline。

- [ ] **Step 4: 注册并机械验证全部持久 owner**

生产组合根 `chapter_production_owner_registry.py` 导出实际 owner descriptors，不由测试维护常量。必须包含：`reader_engagement`, `production_readiness`, `chapter_checkpoint`, `contract_records`, `contract_lifecycle_pointer`, `writer_execution_authority`, `writer_reconciliation`, `staged_artifact`, `final_artifact`, `promotion_receipt`, `web_novel_quality`, `contract_fulfillment`, `state_change_authority`, `memory`, `novel_state`, `baseline`, `writer_admission`。

测试从生产 registry 读取集合，并以 AST + 版本化写路径/出口 manifest 反向扫描所有 authority directory、staged/final write、promotion receipt、model call owner；扫描结果必须与 registry 完全相等。禁止测试常量与测试 factory 自证完整性，新增 sink/owner 未注册即失败。

- [ ] **Step 5: 每章关闭重开全部 owner**

每章结束销毁并按 registry 重建 Engagement、Readiness、Checkpoint、ContractRecordStore、Lifecycle/pointer、Writer execution/reconciliation、staged artifact、final artifact/promotion receipt、Quality Review、Fulfillment、State decision/receipt、Memory/State、Baseline、Admission；从磁盘恢复后才开始下一章。spy 断言每个 owner 每章恰好 close/reopen 一次。

- [ ] **Step 6: 幂等与安全矩阵**

所有 pause 重复 resume 零副作用；无/旧/错误 token、错误 fingerprint/run/authority hash 无 Writer/final/ledger/state 写入；篡改各 Store、journal、head、artifact 均阻断。

- [ ] **Step 7: Gate、独立复审、提交**

Run: `python -m pytest tests/test_phase_e_fake_ten_chapters.py tests/test_phase_e_restart_gate.py -q`

Run: `python -m pytest tests/test_writer_production_exit_architecture.py tests/test_contract_record_store.py tests/test_reader_engagement_store.py tests/test_contract_fulfillment_store.py -q`

Expected: PASS；报告明确十次真实重建、模型调用为零、正文输出为零。

```bash
git add creative_os/domains/chapter_production_owner_registry.py tests/fakes/fake_chapter_writer.py tests/fakes/phase_e_owner_registry.py tests/test_phase_e_fake_ten_chapters.py tests/test_phase_e_restart_gate.py
git commit -m "test: 验证十章逐章生产闭环"
```

### Task 12: E-D 授权边界、文档与 Phase E 最终 Gate

**Files:**
- Modify: `creative_os/production_validation.py`
- Create: `tests/test_phase_e_real_validation_boundary.py`
- Modify: `README.md`
- Modify: `docs/novel-production-roadmap.md`
- Modify: `docs/superpowers/plans/2026-08-22-phase-e-chapter-production-orchestration.md`

**Interfaces:**
- Consumes: complete offline orchestration APIs。
- Produces: `RealCalibrationRequest`, `RealCalibrationGate.evaluate(project_root, chapter_range) -> CalibrationAuthorizationView`；不执行模型。

- [ ] **Step 1: 写停止/授权 RED**

```python
def test_real_calibration_stops_without_explicit_authority_and_human_approvals(gate):
    view = gate.evaluate(project_root, range(7, 9))
    assert view.state == "awaiting_external_authorization"
    assert model_client.calls == 0
```

9–16 章在 7–8 校准三项结论未全部 PASS 时阻断；`force`、模型自评、批量自动继续无效。

- [ ] **Step 2: 实现只读 Gate/验收入口**

重读真实 lifecycle pointer、contract/engagement/readiness/checkpoint authority，精确核对 context/review/runtime event fingerprint；返回授权所需缺项，不调用 Writer。

- [ ] **Step 3: 更新直接相关文档**

完整覆盖设计 §19，但只修改本阶段直接相关章节：

- README：brief/schema 与 readiness 填写规则，明确《文明升阶》空 genre/logline 阻断；
- Narrative Director/Chapter Contract 文档：v3 engagement projection/obligation 与 v2 adapter 阻断边界；
- Engagement 运维文档：Plan/Ledger/Curve、Expectation/Foreshadow 分离、人工 transition；
- CLI 文档：正式命令、旧参数迁移、无直达 Writer；
- Orchestrator 文档：完整状态机、稳定错误码、人工 readiness/contract/opening/quality/expectation/state 审批步骤；
- Store 运维文档：Engagement/Readiness/Checkpoint/WriterExecution/Quality/Fulfillment/State 的备份、严格重读、journal 恢复与灾难处理；
- Writer 安全文档：版本化出口 manifest、AST 反向扫描、staged/final/promotion receipt 边界；
- roadmap：E-A→E-B/C→E-D 顺序、Reader Feedback/Performance 延后；
- 计划状态：仅记录 commits/tests/reviews，不混入无关文档清理。

- [ ] **Step 4: 运行最终 Gate**

Run: `python -m pytest tests/test_phase_e_real_validation_boundary.py tests/test_production_validation.py tests/test_phase_e_fake_ten_chapters.py tests/test_phase_e_restart_gate.py tests/test_writer_production_exit_architecture.py -q`

Run: `python -m pytest -q`

Run: `git diff --check`

Expected: 全绿；敏感信息扫描无 token/key；未调用模型、未生成正文。

- [ ] **Step 5: 三结论与独立最终复审**

分别输出：工程可生产、结构符合网文、人工阅读质量。Fake Gate 只能证明前两项的离线结构与机制，不能伪称真实人工阅读质量；E-D 保持等待授权。

- [ ] **Step 6: 计划自审与提交**

执行 spec coverage、占位符扫描、type/name consistency、E-A Gate 依赖、每 Task 独立全绿、`git diff --check`；未跟踪计划用 `git diff --no-index --check NUL <path>`。

```bash
git add creative_os/production_validation.py tests/test_phase_e_real_validation_boundary.py README.md docs/novel-production-roadmap.md docs/superpowers/plans/2026-08-22-phase-e-chapter-production-orchestration.md
git commit -m "docs: 完成逐章生产离线验收"
```

## Review Closure Mapping

| 复审意见 | 闭环位置 |
|---|---|
| 实际 `ENGAGEMENT_REVIEWED` 编排 | Task 6 owner 调用、权威追加/exact 重读、BLOCKED/幂等/重启、opening 人工记录 |
| Readiness/Quality/State 权威 Store | Task 2 `ProductionReadinessStore`、Task 7 `WebNovelQualityStore`、Task 9 `StateChangeAuthorityStore` |
| Fulfillment 真实生产追加 | Task 8 `ContractFulfillmentReviewer` 从 final exact evidence 追加、重开再 evaluate、partial/supersede/零重复 |
| 可执行 A Exit Gate | Task 0 机械清单和 fail-before-write 测试 |
| Fake 十章 owner 完整重建 | Task 11 生产 owner registry、AST/写路径反扫与逐章 close/reopen spy |
| Orchestrator 累计回归 | Tasks 5–9 的 Gate 命令累计 checkpoint/prewrite/recovery/review/quality/fulfillment/state tests |
| Ambiguous 人工对账 | Task 5 `WriterExecutionAuthorityStore` + `WriterExecutionReconciliationDecision`，本地 MAC receipt 与 exact binding |
| 统一事务锁/部分 checkpoint 恢复 | Task 1 `ProjectAuthorityTransaction/LockContext`、lock identity、跨进程与 operation ID 恢复 |
| 设计 §19 文档覆盖 | Task 12 Step 3 的八类直接相关文档更新 |

## Plan Self-Review Results

- **未来类型：** Task 0 只消费 A Gate；Readiness、Checkpoint、Review、Quality、Fulfillment、State 类型均在首次使用的同 Task 或此前 Task 定义。
- **签名一致：** Orchestrator 只接 public owner ID/hash，不接受临时 Review、裸 receipt、PreparedWriterRun 或权威事实对象。
- **独立全绿：** Tasks 5–9 的 Gate 累计运行 transaction/checkpoint/prewrite/recovery 及所有已接入 Orchestrator 测试。
- **阶段依赖：** A Gate 每次 exact 重算，非 PASS 在 Readiness/run 文件创建前失败；B 没有 A 的 schema/store/planning 实现任务。
- **范围：** E-D 仅授权入口；无 UI、多 Agent、Style Reference、第二事实源、真实模型或正文生成。

## Phase E-B/C Exit Gate

- Phase E-A Exit Gate 仍为 PASS，任何 Plan/Ledger/Curve stale 都能使生产 fail-closed。
- Tasks 0–12 全部独立复审 PASS，定向与全量测试全绿。
- 十章逐章真实重建 Store/Context/Prepared run；模型调用与正文生成均为零。
- Readiness、合同、Admission、Engagement/质量、Fulfillment、Expectation/State、下一 Baseline 全链 exact 绑定。
- CLI/AST/manifest 证明所有生产出口只能经 Orchestrator 与最终 token。
- E-D 仅停在显式授权入口：先 7–8 章校准，三结论全 PASS 后才可申请 9–16 章。
- `git diff --check`、placeholder/type/name/敏感信息/架构扫描全部通过。
