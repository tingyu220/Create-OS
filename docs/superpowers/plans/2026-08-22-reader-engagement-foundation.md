# Reader Engagement Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可版本化、可恢复、人工激活的四层 Reader Engagement 权威基础，并向 Readiness、Director 与 Context 提供冻结投影。

**Architecture:** Planning Service 只产生候选 Plan，人工审批后由独立 authority store 激活；Expectation Ledger、Curve 和 Review 各有窄模型与追加式持久化。Director 与 Context 只消费按 plan/version/hash、ledger head 和 curve hash 冻结的 Chapter projection，不拥有或修改 engagement 事实。

**Tech Stack:** Python 3.12、frozen dataclasses/StrEnum、canonical JSON/SHA-256、现有 no-follow authority I/O 与项目锁、pytest。

**Spec:** `docs/superpowers/specs/2026-08-22-phase-e-web-novel-production-quality-gate-design.md`

## Global Constraints

- 本计划只覆盖 Phase E-A；全部 Gate 通过前禁止执行 Phase E-B/C/D。
- 只复用 `creative_os.domains.narrative_evidence.EvidenceRef`；不得定义包装类、子类或第二 EvidenceRef。
- 不生成小说正文、不调用模型、不自动审批、不接入真实 Reader Feedback/Performance。
- Writer、Director、Orchestrator 均不得直接写 Expectation Ledger；人工决定和 exact evidence 是唯一物化通道。
- Volume 不适用必须显式 N/A 和非空理由；UNKNOWN 一律阻断。
- 所有持久化严格 canonical、exact schema、SHA-256、追加式、幂等、可重启、篡改拒绝。
- 不新增通用历史库、CAS 平台、第二事实源、大 Agent、UI、Style Reference 或无关重构。
- Windows 命令使用 PowerShell 7.6.4；每 Task 定向测试、相关回归和独立复审通过后才能提交下一 Task。
- 每个提交仅包含该 Task 文件，使用中文 Commit Message；不得推送、合并或创建 PR。

## File Structure

- `creative_os/domains/reader_engagement_model.py`：严格领域模型，不含 I/O。
- `creative_os/domains/reader_engagement_codec.py`：v1 canonical JSON codec。
- `creative_os/domains/reader_engagement_store.py`：Plan/Ledger/Curve/Review/decision 追加式权威存储与恢复。
- `creative_os/domains/reader_engagement_planning.py`：候选构建、人工激活和冻结投影组合服务。
- `creative_os/domains/engagement_curve.py`：跨章张弛确定性规则。
- `creative_os/domains/engagement_review.py`：规划兑现 Review 与 transition candidate compiler。
- `creative_os/domains/reader_engagement_migration.py`：旧项目只读迁移审计，不推断状态。
- `creative_os/domains/reader_engagement_gate.py`：Phase E-A 每次 exact 重算的非持久化 Exit Gate result。
- `creative_os/domains/narrative_director.py`：消费冻结 ChapterEngagementProjection。
- `creative_os/memory/context_compiler.py`：将冻结 projection 作为 Knowledge 和 fingerprint 输入。
- `tests/test_reader_engagement_*.py`：按边界拆分的模型、Store、Planning、Curve、Review、Director/Context 测试。

---

### Task 1: 四层 Engagement 与全部跨任务权威记录模型/codec

**Files:**
- Create: `creative_os/domains/reader_engagement_model.py`
- Create: `creative_os/domains/reader_engagement_codec.py`
- Create: `tests/test_reader_engagement_model.py`
- Create: `tests/test_reader_engagement_codec.py`

**Interfaces:**
- Consumes: `creative_os.domains.narrative_evidence.EvidenceRef`。
- Produces: `EngagementScope`, `ExpectationState`, `EngagementAction`, `EngagementIntensity`, `EngagementStatus`, `EngagementReviewStatus`, `EngagementDecisionDisposition`, `OpeningCheckpointDisposition`, `VolumeEngagement`, `OpeningEngagementProfile`, `EngagementPlan`, `ExpectationRecord`, `ExpectationTransition`, `EngagementCurve`, `EngagementCurveEntry`, `EngagementObligation`, `ChapterEngagementProjection`, `EngagementAuthorityRecord`, `EngagementStoreSnapshot`, `PlanDecisionRecord`, `PlanActivationRecord`, `ExpectationTransitionCandidate`, `ExpectationTransitionDecision`, `EngagementReviewResult`, `OpeningCheckpointReviewRecord`, `OpeningCheckpointReviewDecision`; `ReaderEngagementCodec.encode/decode`。Task 2 起 Store registry 只接受本 Task 已定义 schema，Task 3 不重复定义这些类型。

- [ ] **Step 1: 写严格模型 RED 测试**

```python
def test_volume_requires_value_or_explicit_na_reason():
    with pytest.raises(EngagementValidationError, match="volume_unknown"):
        VolumeEngagement(objectives=(), not_applicable_reason=None)

def test_expectation_and_foreshadow_are_distinct_ids():
    record = expectation_record(foreshadow_ids=("foreshadow-1",))
    assert record.expectation_id != record.foreshadow_ids[0]

@pytest.mark.parametrize("objectives,reason", [
    ((), None), (("goal",), "not used"), ((), " "), ((True,), None),
])
def test_volume_xor_rejects_none_both_blank_and_bool(objectives, reason):
    with pytest.raises(EngagementValidationError):
        VolumeEngagement(objectives=objectives, not_applicable_reason=reason)
```

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest tests/test_reader_engagement_model.py -q`
Expected: FAIL with `ModuleNotFoundError: creative_os.domains.reader_engagement_model`。

- [ ] **Step 3: 实现 frozen/slots 模型与深度不可变校验**

```python
class ExpectationState(StrEnum):
    OPEN = "open"
    ESCALATING = "escalating"
    PAID = "paid"
    ABANDONED = "abandoned"

class EngagementReviewStatus(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"

class EngagementAction(StrEnum):
    ESTABLISH = "establish"
    ESCALATE = "escalate"
    PAY = "pay"
    WITHHOLD = "withhold"

@dataclass(frozen=True, slots=True)
class ChapterEngagementProjection:
    plan_id: str
    plan_version: int
    plan_hash: str
    ledger_head_hash: str
    curve_hash: str
    chapter_number: int
    obligations: tuple[EngagementObligation, ...]
    canonical_json: str
    projection_hash: str
```

要求字符串非空、正整数拒绝 bool、hash 为 64 位小写 hex、tuple 元素逐项严格类型、PAID/ABANDONED 为终态、Opening profile 精确包含 1/3/6/10 义务。Volume 严格 XOR：适用时 objectives 非空且 reason 为 None；N/A 时 objectives 为空且 reason 为非空非空白字符串；拒绝 both/none/UNKNOWN/bool。Evidence 字段只接受 exact `EvidenceRef`。

所有人工 decision 公共字段固定为：`reviewed_object_id`, `reviewed_object_hash`, `ruleset_version`, `ruleset_hash`, `previous_authority_hash`, `actor`, `decided_at`, `reason`, `disposition`, `decision_domain`, `decision_hash`。`PlanDecisionRecord` 额外 exact 绑定 `plan_id/plan_hash/curve_id/curve_hash` composite。`decision_hash` 由 domain-separated canonical payload 计算，任何一个 binding 变化都改变 hash。

`OpeningCheckpointReviewRecord` 还必须绑定 plan/projection/ledger/curve/contract/context/artifact/ruleset hash，保存 `continue_reading`, `reader_expectations`, `paid_expectations`, `reason`, `actor`, `reviewed_at`；其人工 `OpeningCheckpointReviewDecision` 不能由自动 `EngagementReviewResult` 代替。

- [ ] **Step 4: 写 codec RED 并实现 exact v1 codec**

```python
def test_codec_rejects_duplicate_keys_and_extra_fields():
    with pytest.raises(EngagementCodecError):
        ReaderEngagementCodec.decode('{"schema_version":1,"schema_version":1}')
```

Codec 必须拒绝重复 key、额外/缺失字段、`true` 版本、非 canonical tuple 顺序与未知枚举；encode→decode exact round-trip。

- [ ] **Step 5: 运行 Task 1 Gate**

Run: `python -m pytest tests/test_reader_engagement_model.py tests/test_reader_engagement_codec.py tests/test_narrative_evidence.py -q`
Expected: PASS；架构测试证明全仓仍只有一个 `class EvidenceRef`。

- [ ] **Step 6: 独立复审并提交**

Review: 模型不含 I/O/审批，codec 不接纳宽松 JSON，Foreshadow 未复用 Expectation 状态。

```bash
git add creative_os/domains/reader_engagement_model.py creative_os/domains/reader_engagement_codec.py tests/test_reader_engagement_model.py tests/test_reader_engagement_codec.py
git commit -m "feat: 定义读者吸引力权威模型"
```

### Task 2: Engagement Authority Store

**Files:**
- Create: `creative_os/domains/reader_engagement_store.py`
- Create: `tests/test_reader_engagement_store.py`
- Test: `tests/test_contract_fulfillment_store.py`

**Interfaces:**
- Consumes: Task 1 models/codec；复用 `contract_record_filesystem`/`contract_record_win32` 的可信句柄策略。
- Produces: `ReaderEngagementStore(project_root)`；`append_plan_candidate`, `append_plan_decision`, `append_activation`, `append_curve`, `append_expectation_candidate`, `append_expectation_decision`, `append_expectation_transition`, `append_engagement_review`, `append_opening_checkpoint_review`, `append_opening_checkpoint_decision`, `load_exact`, `active_plan`, `ledger_head`, `recover`。每个参数类型均来自 Task 1。

- [ ] **Step 1: 写 append/exact/restart RED**

```python
def test_store_restart_reads_exact_plan_curve_and_ledger(tmp_path):
    store = ReaderEngagementStore(tmp_path)
    saved = store.append_plan_candidate(plan_candidate())
    reopened = ReaderEngagementStore(tmp_path)
    assert reopened.load_exact("plan", saved.record_id, saved.content_hash) == saved
```

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest tests/test_reader_engagement_store.py -q`
Expected: FAIL because `ReaderEngagementStore` is absent。

- [ ] **Step 3: 实现小型 envelope/head/journal store**

```python
class ReaderEngagementStore:
    def load_exact(self, record_type: str, record_id: str,
                   content_hash: str) -> EngagementAuthorityRecord:
        raise NotImplementedError

    def recover(self) -> EngagementStoreSnapshot:
        raise NotImplementedError
```

记录类型使用显式 registry；records/head/journal 原始 bytes 必须等于 canonical JSON + 单个 LF。文件名绑定 record ID，sequence/previous/entry hash 形成链，项目锁覆盖 CAS。

- [ ] **Step 4: 加入篡改、部分失败、并发 RED/GREEN**

覆盖删尾、截断、重排、CRLF、空行、重复 key、symlink/reparse、祖先替换、journal 五阶段、两进程同记录幂等/异内容冲突；每个 fault point 后关闭重开并 exact recover。

加入所有 registry 类型 round-trip，尤其 Plan decision/activation、Expectation candidate/decision/transition、EngagementReview、Opening checkpoint review/decision；未知 record type/schema_version 必须拒绝，禁止 Store 先接收未来 Task 才定义的 payload。

- [ ] **Step 5: 运行 Task 2 Gate**

Run: `python -m pytest tests/test_reader_engagement_store.py tests/test_contract_fulfillment_store.py tests/test_contract_record_store.py -q`
Expected: PASS；`git diff --check` PASS。

- [ ] **Step 6: 独立复审并提交**

```bash
git add creative_os/domains/reader_engagement_store.py tests/test_reader_engagement_store.py
git commit -m "feat: 增加读者吸引力权威存储"
```

### Task 3: Expectation Ledger 人工转换物化

**Files:**
- Modify: `creative_os/domains/reader_engagement_model.py`
- Modify: `creative_os/domains/reader_engagement_store.py`
- Create: `tests/test_expectation_ledger.py`

**Interfaces:**
- Consumes: `ExpectationRecord`, `ExpectationTransition`, `ReaderEngagementStore`。
- Produces: 仅实现 Task 1 已定义类型的 `materialize_transition(candidate_id, decision_id, expected_head_hash) -> ExpectationLedgerSnapshot`，不新增或重复定义 transition/decision schema。

- [ ] **Step 1: 写状态机与人工边界 RED**

```python
def test_abandoned_requires_approved_human_reason_and_exact_evidence(store):
    candidate = transition_candidate(to_state=ExpectationState.ABANDONED, evidence=())
    with pytest.raises(EngagementAuthorityError, match="abandonment_reason_required"):
        store.materialize_transition(candidate.id, decision(reason=""), store.ledger_head().head_hash)
```

加入不存在 expectation 的 PAID、错误 from state、旧 head、旧 plan、重复同内容、重复异内容、UNKNOWN 自动回收负测。

ESTABLISH 的完整路径固定为 `ABSENT→OPEN`：candidate 携带全局唯一 expectation ID、plan binding、`previous_record_hash=None`、expected ledger head 和 exact evidence；同 ID/同 canonical 内容重放返回原 OPEN record，同 ID/异内容冲突。旧 plan/head、非 None 初始 previous hash、journal 篡改均阻断。ESCALATE/PAY/WITHHOLD/ABANDON 禁止作用于不存在记录。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest tests/test_expectation_ledger.py -q`
Expected: FAIL because transition APIs are absent。

- [ ] **Step 3: 实现 compare-and-append**

```python
def materialize_transition(self, candidate_id: str, decision_id: str,
                           expected_head_hash: str) -> ExpectationLedgerSnapshot:
    """锁内 exact 重读 candidate/decision/evidence/head 后追加一次转换。"""
```

decision 必须 APPROVED、人工 actor 与非空 reason；PAID/ABANDONED 要求 exact artifact/fulfillment evidence。允许 `OPEN→PAID`，但必须同时满足 active projection 的 PAY obligation、payoff window、冻结 Chapter Contract PAY intent 和 exact verification/realization evidence。不得修改旧 record，history 追加 previous record hash。

- [ ] **Step 4: 恢复与全局唯一性测试**

关闭重开后重放 transition 只返回同一 head；相同 transition ID 不能跨 expectation 复用；prepared→decision observed→ledger CAS→committed 任一点失败可恢复。

- [ ] **Step 5: 运行 Task 3 Gate 并复审提交**

Run: `python -m pytest tests/test_expectation_ledger.py tests/test_reader_engagement_store.py -q`
Expected: PASS。

```bash
git add creative_os/domains/reader_engagement_model.py creative_os/domains/reader_engagement_store.py tests/test_expectation_ledger.py
git commit -m "feat: 实现期待账本人工转换"
```

### Task 4: Engagement Curve 规则

**Files:**
- Create: `creative_os/domains/engagement_curve.py`
- Create: `tests/test_engagement_curve.py`

**Interfaces:**
- Consumes: `EngagementCurve`, `EngagementIntensity`, `EngagementPlan`。
- Produces: `CurveIssue(code, chapter_numbers, blocking)`；`EngagementCurveValidator.validate(plan, curve) -> tuple[CurveIssue, ...]`。每个 `EngagementCurveEntry` 必须保存 `arc_id`, `expectation_obligation_ids`, `causal_rationale`, `evidence: tuple[EvidenceRef, ...]`。

- [ ] **Step 1: 写张弛边界 RED**

```python
def test_curve_allows_recovery_low_but_blocks_long_low_and_peak_fatigue():
    assert validator.validate(plan, curve("HIGH", "LOW", "MEDIUM")) == ()
    assert codes(validator.validate(plan, curve("LOW", "LOW", "LOW", "LOW"))) == {"prolonged_low"}
    assert "peak_fatigue" in codes(validator.validate(plan, curve("PEAK", "PEAK", "PEAK")))

def test_consecutive_peaks_require_distinct_causal_obligations_and_evidence():
    assert validator.validate(plan, causally_grounded_peaks()) == ()
    assert "peak_fatigue" in codes(validator.validate(plan, ungrounded_peaks()))
```

- [ ] **Step 2: 运行 RED 并实现版本化确定性规则**

Run: `python -m pytest tests/test_engagement_curve.py -q`
Expected: FAIL；实现 `RULESET_VERSION = "engagement_curve/v1"`，阈值由具名常量定义，结果绑定 plan/version/hash 和 curve hash，不读取正文关键词。

- [ ] **Step 3: 覆盖 stale/Arc 不一致/十章后连续性**

Plan hash 错误、章节重复/断档、Curve 引用未知 Arc/Expectation、空 rationale、缺 exact EvidenceRef 阻断；有不同因果义务和 exact evidence 的连续高点允许，无因果堆峰阻断。第 11 章投影沿用第 10 章后 head，不重置曲线。

- [ ] **Step 4: 运行 Gate、复审、提交**

Run: `python -m pytest tests/test_engagement_curve.py tests/test_reader_engagement_model.py -q`
Expected: PASS。

```bash
git add creative_os/domains/engagement_curve.py tests/test_engagement_curve.py
git commit -m "feat: 增加跨章吸引力曲线门禁"
```

### Task 5: Planning Service、人工激活与冻结投影

**Files:**
- Create: `creative_os/domains/reader_engagement_planning.py`
- Create: `tests/test_reader_engagement_planning.py`

**Interfaces:**
- Consumes: `EngagementPlan`, store Task 2 APIs, curve validator。
- Produces: `EngagementPlanningInput`; `ReaderEngagementPlanningService.propose(input: EngagementPlanningInput, candidate: EngagementPlan) -> EngagementPlan`；`ReaderEngagementPlanningService.project_chapter(project_id: str, chapter_number: int) -> ChapterEngagementProjection`；窄人工入口 `PlanDecisionRecorder.record(plan_id: str, plan_hash: str, curve_id: str, curve_hash: str, actor: str, reason: str, disposition: EngagementDecisionDisposition) -> PlanDecisionRecord`；`PlanActivationService.activate_plan(plan_id: str, decision_id: str, expected_active_hash: str) -> PlanActivationRecord`。

- [ ] **Step 1: 写候选/审批/激活 RED**

```python
def test_planner_cannot_activate_without_exact_human_decision(service):
    candidate = service.propose(planning_input(), plan_candidate())
    with pytest.raises(EngagementAuthorityError, match="approval_missing"):
        service.activate_plan(candidate.plan_id, "missing")
```

- [ ] **Step 2: 运行 RED 并实现组合服务**

Run: `python -m pytest tests/test_reader_engagement_planning.py -q`
Expected: FAIL；Planning Service 只校验/保存调用方候选与生成 projection，不调用模型、不创建 decision、不签发 APPROVED。

- [ ] **Step 3: 实现统一项目锁、active pointer CAS 与 activation journal**

PlanDecisionRecorder 锁内 exact 重读 plan+curve composite 后记录人工决定。激活在 Task 2 的统一项目 authority lock 内 exact 重读 expected active pointer、Plan、Curve、与二者 ID/hash 完全一致的 PlanDecision、Ledger head及 previous authority hash，写 `prepared→activation_written→pointer_switched→committed` journal。`activation_binding_hash` 绑定全部读取结果；decision 的 plan/curve 任一漂移或 expected active hash 不一致即冲突。

故障矩阵覆盖 journal temp/write/replace/fsync、activation append、pointer replace、journal commit/unlink；每点关闭重开后 `recover_activation(plan_id)` 必须得到一个 active pointer 或保持旧 pointer，不能零/双 ACTIVE。

- [ ] **Step 4: 写 projection 与 stale RED/GREEN**

`project_chapter` 使用同一项目 authority lock，exact 重读 active pointer、Plan、activation record/binding、Ledger head、Curve，随后构建单章 projection；旧 pointer/plan/head/curve、未来十章批量 projection API、Volume UNKNOWN 全部拒绝。每次只允许单个 chapter number。

- [ ] **Step 5: Opening fixture 边界测试**

使用测试 fixture 表达 1/3/6/10 obligations；不得写入 `projects/文明升阶` 正文或自动推断项目事实。第 11 章仍从四层 plan 正常投影。

AST/能力测试证明 `ReaderEngagementPlanningService` 没有 `approve/activate/record_decision` 方法，不导入人工 decision signer/store append decision；只有 `PlanDecisionRecorder` 能追加 decision，只有 `PlanActivationService` 能切 pointer。

- [ ] **Step 6: Gate、独立复审、提交**

Run: `python -m pytest tests/test_reader_engagement_planning.py tests/test_engagement_curve.py tests/test_reader_engagement_store.py -q`
Expected: PASS。

```bash
git add creative_os/domains/reader_engagement_planning.py tests/test_reader_engagement_planning.py
git commit -m "feat: 接入吸引力计划人工激活"
```

### Task 6: Narrative Director 只消费冻结 projection

**Files:**
- Modify: `creative_os/domains/narrative_director.py`
- Modify: `creative_os/domains/narrative_decision.py`
- Modify: `creative_os/domains/narrative_codec.py`
- Modify: `creative_os/domains/contract_preflight.py`
- Modify: `creative_os/domains/contract_review.py`
- Modify: `tests/test_narrative_director.py`
- Modify: `tests/test_narrative_decision.py`
- Modify: `tests/test_narrative_codec.py`
- Modify: `tests/test_contract_preflight.py`
- Modify: `tests/test_contract_review.py`
- Create: `tests/test_narrative_director_engagement.py`

**Interfaces:**
- Consumes: `ChapterEngagementProjection` from Task 5。
- Produces: `DirectorInput.engagement_projection: ChapterEngagementProjection`；`ChapterContract.engagement_obligations: tuple[ContractEngagementObligation, ...]`，每项包含 `action`, `expectation_id`, `projection_obligation_id`, `expected_payoff_window`, `intent_evidence: tuple[EvidenceRef, ...]`；`NarrativeDecisionCodec` schema v3、Preflight、Reviewer 共同验证。

- [ ] **Step 1: 写无 projection/stale/发明期待 RED**

```python
def test_director_rejects_obligation_not_in_active_projection():
    proposal = decision_with_obligation(expectation_id="invented")
    with pytest.raises(NarrativeDirectorBlockedError, match="engagement obligation"):
        NarrativeDirector().propose(input_with_projection(), proposal)
```

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest tests/test_narrative_director_engagement.py -q`
Expected: FAIL because `DirectorInput` has no engagement projection。

- [ ] **Step 3: 扩展 ChapterContract 与 NarrativeDecisionCodec**

新增不可变 `engagement_projection_hash` 与 `engagement_obligations`，以 schema v3 编码并增加 exact round-trip/strict field tests；不得复制 Plan/Ledger 内容。既有 schema v2 必须原样 exact decode 为 v2 对象，不改变其结构或 hash。显式 `NarrativeDecisionV2ToV3Adapter.adapt(v2) -> NarrativeDecisionV3Candidate` 只能生成 `engagement_status=UNSATISFIED`、空 obligations 的候选；Phase E Director/Preflight 必须阻断，直到走正常 Planning/Director 产生满足 engagement 的 v3。

- [ ] **Step 4: Preflight 与 Reviewer RED/GREEN**

Preflight 逐 obligation 验证 action 与 projection 一致、target expectation 存在且状态允许、intent evidence exact、PAY 位于允许 payoff window、WITHHOLD 有因果理由且未越过 deadline。缺失 obligation、旧 projection hash、未知 expectation、OPEN 直接 ESCALATE/PAY 越权、deadline 冲突均产生 blocking `ContractIssue`。Reviewer 生成绑定 projection/ledger/curve/ruleset hash 的 issue，人工 disposition 不能抹去 stale authority。

- [ ] **Step 5: 运行相关回归与架构扫描**

Run: `python -m pytest tests/test_narrative_director.py tests/test_narrative_director_engagement.py tests/test_narrative_decision.py tests/test_narrative_codec.py tests/test_contract_preflight.py tests/test_contract_review.py -q`
Expected: PASS；AST 证明 Director 不导入 store 写接口或模型 client。

- [ ] **Step 6: 独立复审并提交**

```bash
git add creative_os/domains/narrative_director.py creative_os/domains/narrative_decision.py creative_os/domains/narrative_codec.py creative_os/domains/contract_preflight.py creative_os/domains/contract_review.py tests/test_narrative_director.py tests/test_narrative_director_engagement.py tests/test_narrative_decision.py tests/test_narrative_codec.py tests/test_contract_preflight.py tests/test_contract_review.py
git commit -m "feat: 让叙事导演消费冻结吸引力投影"
```

### Task 7: Context 冻结投影与 fingerprint

**Files:**
- Modify: `creative_os/memory/context_compiler.py`
- Modify: `tests/test_context_compiler.py`
- Create: `tests/test_engagement_context_projection.py`

**Interfaces:**
- Consumes: `ChapterEngagementProjection`。
- Produces: `CompileRequest.engagement_projection`; Context 中唯一 `kind="reader_engagement_projection"` Knowledge；fingerprint 绑定 projection canonical JSON/hash。

- [ ] **Step 1: 写单次注入/旧版本排除/fingerprint RED**

```python
def test_compiler_replaces_all_engagement_knowledge_with_frozen_projection():
    compiled = compiler.compile(request_with_old_engagement_items())
    assert [k.body for k in compiled.knowledge if k.kind == "reader_engagement_projection"] == [projection.canonical_json]
```

- [ ] **Step 2: 运行 RED 并实现**

Run: `python -m pytest tests/test_engagement_context_projection.py -q`
Expected: FAIL；实现严格 type、project/chapter/hash 绑定，移除全部旧 engagement Knowledge 后只注入一次。

- [ ] **Step 3: 漂移与权限架构测试**

错误 plan/ledger/curve/projection hash 阻断编译；AST 证明 ContextCompiler 与 Writer 无 Ledger store 写调用。

- [ ] **Step 4: Gate、复审、提交**

Run: `python -m pytest tests/test_context_compiler.py tests/test_engagement_context_projection.py tests/test_narrative_continuation.py -q`
Expected: PASS。

```bash
git add creative_os/memory/context_compiler.py tests/test_context_compiler.py tests/test_engagement_context_projection.py
git commit -m "feat: 将冻结吸引力投影纳入上下文"
```

### Task 8: Engagement Review 与 transition candidate compiler

**Files:**
- Create: `creative_os/domains/engagement_review.py`
- Create: `tests/test_engagement_review.py`

**Interfaces:**
- Consumes: Plan/projection/Ledger/Curve、合同 hash、Context fingerprint、artifact metadata、exact `EvidenceRef`。
- Produces: `EngagementReviewResult`; `EngagementReviewer.review(inputs: EngagementReviewInput) -> EngagementReviewResult`; `ExpectationTransitionCompiler.compile(review: EngagementReviewResult, evidence: tuple[EvidenceRef, ...]) -> tuple[ExpectationTransitionCandidate, ...]`; `OpeningCheckpointReviewService.record(review: OpeningCheckpointReviewRecord, decision: OpeningCheckpointReviewDecision) -> OpeningCheckpointReviewRecord`。

- [ ] **Step 1: 写 hard/人工边界 RED**

```python
def test_review_unknown_evidence_is_blocking_not_keyword_pass():
    result = reviewer.review(inputs(evidence=()))
    assert result.status == EngagementReviewStatus.BLOCKED
    assert "evidence_missing" in result.issue_codes
```

覆盖旧期待超期、只开新坑、payoff 频率、hook 因果、重复情绪曲线；文学质量分数、Fulfillment verdict、一致性 verdict 不能代替本 Review。

- [ ] **Step 2: 运行 RED 并实现纯求值 Review**

Run: `python -m pytest tests/test_engagement_review.py -q`
Expected: FAIL；Reviewer 不写 Store、不读正文关键词、不调用模型，UNKNOWN 为 blocking。

- [ ] **Step 3: transition compiler RED/GREEN**

Compiler 只能基于 Review 中已验证 evidence 产生 candidate；established/escalated/paid/abandoned 每项 exact 绑定 artifact/plan/ledger/contract/context。ABANDONED candidate 必须携带人工 review reason，但仍需 Task 3 decision 才能物化。

- [ ] **Step 4: Opening 1/3/6/10 人工 Review 权威链 RED/GREEN**

仅 chapter 1/3/6/10 要求 `OpeningCheckpointReviewRecord` + APPROVED decision。Service 锁内 exact 重读 plan/projection/ledger/curve/contract/context/artifact/ruleset 后追加 record/decision，再按 ID/hash exact 重读；自动 EngagementReview 即使 PASS 也不能替代。覆盖人工是否追读、期待、已兑现、理由、actor/time 的缺失，以及 restart/tamper/stale/重复幂等。

- [ ] **Step 5: Gate、独立复审、提交**

Run: `python -m pytest tests/test_engagement_review.py tests/test_expectation_ledger.py tests/test_reader_engagement_store.py tests/test_contract_fulfillment.py -q`
Expected: PASS。

```bash
git add creative_os/domains/engagement_review.py tests/test_engagement_review.py
git commit -m "feat: 增加吸引力兑现审查"
```

### Task 9: 迁移、文档与 Phase E-A 最终 Gate

**Files:**
- Create: `creative_os/domains/reader_engagement_migration.py`
- Create: `creative_os/domains/reader_engagement_gate.py`
- Create: `tests/test_reader_engagement_migration.py`
- Create: `tests/test_reader_engagement_gate.py`
- Modify: `README.md`
- Modify: `docs/novel-production-roadmap.md`
- Modify: `docs/superpowers/plans/2026-08-22-reader-engagement-foundation.md`

**Interfaces:**
- Consumes: Tasks 1–8 public APIs。
- Produces: `ReaderEngagementMigration.inspect(project_root) -> EngagementMigrationReport`; 非持久化 frozen 求值结果 `ReaderEngagementExitGateResult`; `evaluate_reader_engagement_exit_gate(project_root: Path) -> ReaderEngagementExitGateResult`。

- [ ] **Step 1: 写只读迁移 RED**

```python
def test_migration_never_infers_paid_or_abandoned_from_legacy_text(tmp_path):
    report = ReaderEngagementMigration.inspect(tmp_path)
    assert report.requires_human_plan is True
    assert report.materialized_transitions == ()
```

- [ ] **Step 2: 实现 inspect-only migration report**

报告旧 opening/brief 可映射字段、缺失权威项和人工输入要求；不自动激活、不读正文推断、不建立十章 plan。《文明升阶》opening profile 只放测试 fixture 或后续人工输入。

- [ ] **Step 3: 更新直接相关文档**

README 记录 engagement authority 入口和人工边界；roadmap 将 E-A 标为 E-B 前置。计划状态记录每 Task commit/test/review，不做大范围文档清理。

- [ ] **Step 4: 运行 Phase E-A 全量 Gate**

Run: `python -m pytest tests/test_reader_engagement_model.py tests/test_reader_engagement_codec.py tests/test_reader_engagement_store.py tests/test_expectation_ledger.py tests/test_engagement_curve.py tests/test_reader_engagement_planning.py tests/test_narrative_director_engagement.py tests/test_engagement_context_projection.py tests/test_engagement_review.py tests/test_reader_engagement_migration.py tests/test_reader_engagement_gate.py -q`

Run: `python -m pytest -q`

Run: `git diff --check`

Expected: 全绿；敏感信息扫描无 token/key；架构扫描仅一个 EvidenceRef，Writer/Director/Orchestrator 无 Ledger 写权限。

Gate evaluator 每次 exact 重读 ACTIVE Plan/activation、Ledger、Curve、单章 projection 与 store heads，并验证 schema/ruleset/architecture manifest；结果仅存在于当前调用内存，不写 Store、文件、receipt 或 authority record。计划 B 每次调用都重新求值，不能复用旧 result。

- [ ] **Step 5: 独立最终复审**

Review Gate：ACTIVE Plan + exact Ledger/Curve 可重启投影；stale/篡改/unknown fail-closed；人工 transition 唯一物化通道；Task 6–8 不复制权威事实。复审 PASS 后才允许计划 B。

- [ ] **Step 6: 自审计划并提交迁移/产品文档**

执行 spec coverage、占位符扫描、type/name consistency、A→B 依赖、每 Task 独立全绿、`git diff --check`；未跟踪计划用 `git diff --no-index --check NUL <path>`。

```bash
git add creative_os/domains/reader_engagement_migration.py creative_os/domains/reader_engagement_gate.py tests/test_reader_engagement_migration.py tests/test_reader_engagement_gate.py README.md docs/novel-production-roadmap.md
git commit -m "feat: 增加读者吸引力迁移审计"
```

- [ ] **Step 7: 单独更新并提交计划状态账本**

计划文档只记录 Tasks 1–9 的 commit/test/review 结果，不与迁移代码、README 或 roadmap 混合暂存。

```bash
git add docs/superpowers/plans/2026-08-22-reader-engagement-foundation.md
git commit -m "docs: 记录读者吸引力基础验收"
```

## Review Closure Mapping

| 复审意见 | 闭环位置 |
|---|---|
| Store 引用未来 schema | Task 1 前置全部跨任务 record/decision/activation/review 模型与 codec；Task 2 registry round-trip/unknown schema 拒绝 |
| Director→ChapterContract 缺口 | Task 6 修改 ChapterContract、NarrativeDecision codec、Preflight、Reviewer 和对应 tests |
| 1/3/6/10 人工追读权威链 | Task 1 定义 record/decision；Task 2 持久化；Task 8 exact 重读、restart/tamper/stale Gate |
| 人工 decision 完整 binding | Task 1 公共 decision 字段和 domain-separated decision hash；Tasks 3/5/8 使用 |
| activation/projection 锁、CAS、journal | Task 5 统一项目锁、四阶段 journal、各崩溃点恢复 |
| Curve 因果与 evidence | Task 1 `EngagementCurveEntry`；Task 4 有因果高点/无因果堆峰测试 |
| Volume N/A XOR | Task 1 strict model/codec 参数矩阵 |
| 无接口 stub 占位、状态账本独立 | Task 2 使用完整签名；Task 9 Step 6/7 分开提交产品变更与计划状态 |
| `ABSENT→OPEN` 建立路径 | Task 3 ESTABLISH 唯一 ID、初始 hash、幂等/冲突、stale/recovery/tamper；其他 action 不得作用于不存在记录 |
| Gate result 不持久化 | Task 9 每次 exact 重算内存 result；计划 B Task 0 每次调用，不缓存 receipt |
| NarrativeDecision v3 | Task 6 v3 codec、v2 exact decode、v2→v3 UNSATISFIED adapter 与 Preflight 阻断 |
| Plan+Curve composite decision | Task 1 decision binding；Task 5 Recorder 与 activation exact 验证 |
| Planning 无审批能力 | Task 5 拆分 Planning/DecisionRecorder/ActivationService，并用 AST/能力测试冻结 |
| `OPEN→PAID` | Task 3 要求 projection/payoff window/合同 PAY intent/exact evidence 同时成立 |
| Task 3 不重复类型 | Task 1 完整枚举/record schema；Task 3 仅 materialization |

## Plan Self-Review Results

- **未来类型：** Task 1 定义 Task 2 registry 和 Tasks 3/5/8 所需全部跨任务 record/decision/review 类型；Task 8 自有 input/service 与实现同 Task 交付。
- **签名一致：** Store append/load、Planning activation/projection、Director obligation、Review compiler 名称在生产者与消费者一致。
- **独立全绿：** 每个 Task Gate 只调用本 Task 或已完成 Task API；Task 6 同步模型/codec/Preflight/Reviewer，未把合同基础留给计划 B。
- **阶段依赖：** Task 9 提供每次 exact 重算的非持久化 Gate result；计划 B 只能调用求值，不能缓存或补建 A。
- **范围：** 无 UI、多 Agent、Style Reference、第二事实源、模型调用或正文生成。

## Phase E-A Exit Gate

- Tasks 1–9 全部独立复审 PASS，定向与全量测试全绿。
- Plan/Ledger/Curve/Review 可 exact 重读、幂等恢复、篡改拒绝。
- Director/Context 只消费冻结 projection；没有一次性十章预计算接口。
- ABANDONED/payoff/所有 transition 均有 exact evidence 与人工批准。
- `git diff --check`、placeholder/type/name/架构扫描通过。
- 只有满足以上全部条件，`2026-08-22-phase-e-chapter-production-orchestration.md` 才可开始执行。
