# Narrative Director + Chapter Contract Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 原位升级唯一的 `NarrativeDecision/ChapterContract`，建立经权威持久化记录证明、可恢复且不可绕过的合同审批、冻结、Writer 准入、成稿证据、修订与迁移闭环。

**Architecture:** `NarrativeDecisionCodec` 将输入规范化为 v2；合同业务版本使用不可变物理键，current pointer 是唯一活动真源。审批、Baseline、Reviewer 与 disposition 存入独立追加式权威记录仓；Lifecycle 与 WriterAdmission 每次从该仓精确重读。Writer 只消费冻结投影与签名 token，成稿证据由另一追加式 Store 处理。

**Tech Stack:** Python 3.11+、冻结 dataclass/StrEnum、JSON/JSONL、SHA-256 canonical JSON、pytest、标准库锁、同目录临时文件 `Path.replace()`。

**Spec:** `docs/superpowers/specs/2026-08-20-narrative-director-chapter-contract-approval-design.md`

## Global Constraints

- 原位升级现有 `NarrativeDecision/ChapterContract`；禁止平行合同、平行 Director 或第二合同真源。
- `contract_version` 是唯一业务版本；`vMMMM`、pointer 版本、合同版本相等；v2 合同 `MemoryItem.version == 1`。
- `EvidenceRef` 可表达 `intent|non_applicability|verification|realization|decision`；冻结合同只允许前两种，`decision` 仅存在外部审批/裁决记录。
- `MemoryEvidence` 仅是信封来源；数组逐元素绑定精确 `field_path`。
- 所有错误 fail-closed；记录缺失、篡改、陈旧、unknown、undetermined、未裁决 warning 均阻断 Writer 和正文晋升。
- 所有 Writer/晋升/发布入口只消费 `AdmittedContractProjection + admission_token`，不得直读 ACTIVE 合同。
- `WriterAdmissionToken` 只能在真实 Context 已编译并取得 fingerprint 后签发；Context 编译前仅可持有短时 `AdmissionGrant`，grant 不能调用 Writer/晋升/发布。
- Phase A 包含 v0001、pointer、权威记录仓、首次激活/恢复及所有生产出口；Phase C 只扩展 replacement/CAS。
- 每个任务结束时本任务测试及所列回归必须全部 PASS；提交命令仅为建议，本计划不提交、不推送。

## File responsibility map

- `contract_issue.py`：公共 `ContractIssue/EvidenceCheck`。
- `narrative_evidence.py`：`EvidenceLocator/EvidenceRef` 唯一定义及完整性校验。
- `narrative_decision.py`：唯一正式 v2 合同值对象，只引用 EvidenceRef。
- `narrative_codec.py`：正式 v1/v2 codec 与 canonical hash。
- `narrative_causality.py`：因果路径与候选裁决。
- `contract_baseline.py`：BaselineManifest/fingerprint。
- `contract_approval.py`：审批结构、覆盖路径与重审集合。
- `contract_preflight.py`：schema、字段、intent/N/A、因果预检。
- `contract_review.py`：ReviewerResult、规则绑定、disposition。
- `contract_record_store.py`：Baseline、Approval、Reviewer、disposition 权威追加式 Store。
- `contract_lifecycle.py`：物理键、pointer、激活/恢复及后续 CAS。
- `writer_admission.py`：两阶段准入；`pre_admit` 只签短时 grant，`finalize_admission` 才签最终 token；只读权威 Store。
- `context_compiler.py`、`novel_continuation.py`：冻结投影 Context 与合同排重。
- `novel_continuation_runner.py`、`llm_writer.py`：全部正文生产/晋升出口。
- `contract_fulfillment*.py`：追加式成稿证据与完成推导。
- `contract_revision.py`：RevisionRequest 与旧 run 受限继续授权。
- `narrative_replay_*`、`legacy_narrative_adapter.py`：回放/迁移，不取得正式合同主权。

## Dependency graph

```text
A1 issue+evidence -> A2 model+codec -> A3 causality -> A5 preflight
A1+A2 -> A4 baseline+approval
A2 -> A6 storage primitives
A1+A2+A4 -> A7 reviewer -> A8 authoritative record store
A5+A6+A8 -> A9 initial activation/recovery
A3+A4+A7+A8+A9 -> A10 pre-admit grant -> A11 real Context fingerprint -> A10 finalize token -> A12 all production exits
A12 -> B13-B14 -> C15-C17 -> D18-D20
```

---

## Phase A — 不可绕过的最小写前闭环

### Task 1: 公共 Issue 与 EvidenceRef 唯一类型

**Files:** Create `creative_os/domains/contract_issue.py`, `creative_os/domains/narrative_evidence.py`; Test `tests/test_contract_issue.py`, `tests/test_narrative_evidence.py`。

**Interfaces:** Consumes: 无。Produces: `EvidenceCheck`；`ContractIssue(code,severity,blocking,field_path,evidence_checks,repair_hint)`；`EvidenceRole/EvidenceLocator/EvidenceRef`；`EvidenceIntegrityValidator.validate(ref, expected_field_path) -> tuple[ContractIssue,...]`。

- [ ] 写失败测试：五种 role、issue 必填字段、证据八元组去重、同 excerpt 不同路径、hash/version/locator/assertion 漂移、拒绝以 `MemoryEvidence` 代替 EvidenceRef。
- [ ] 运行 `python -m pytest tests/test_contract_issue.py tests/test_narrative_evidence.py -v`；预期 FAIL：模块不存在。
- [ ] 最小实现：冻结类型；locator 仅允许四种设计值；通过注入的 source resolver 校验 hash、定位和 assertion。
- [ ] 重跑并加 `tests/test_memory_model.py`；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/contract_issue.py creative_os/domains/narrative_evidence.py tests/test_contract_issue.py tests/test_narrative_evidence.py && git commit -m "feat: 统一合同问题与字段证据类型"`

### Task 2: 原位 v2 模型与完整 NarrativeDecisionCodec

**Files:** Modify `creative_os/domains/narrative_decision.py`, `tests/test_narrative_director.py`, `tests/test_narrative_memory.py`; Create `creative_os/domains/narrative_codec.py`; Test `tests/test_narrative_decision.py`, `tests/test_narrative_codec.py`。

**Interfaces:** Consumes: Task 1 types。Produces: 原位 `NarrativeDecision(contract_id,contract_version,...)`、`ChapterContract(chapter_id,...)`、`ChoiceStatus/NullablePlan/OptionalCandidateResolution`；`NarrativeDecisionCodec.decode/decode_v1/decode_v2/encode_v2/content_hash`。

- [ ] 写失败测试：choice 三态、N/A 互斥、id/version、唯一字段命名、冻结合同接受 intent/N/A 且拒绝其他 role；v1 fixture 规范化为不准入 v2；v2 round-trip；未知 schema/state 拒绝。
- [ ] 运行 `python -m pytest tests/test_narrative_decision.py tests/test_narrative_codec.py tests/test_narrative_director.py tests/test_narrative_memory.py -v`；预期 FAIL：v2/codec 缺失。
- [ ] 最小实现：保留正式类名；`from_json/to_json` 委托 codec；v1 证据标 `legacy_unclassified` 且不成为有效 binding；canonical JSON 紧凑排序并 SHA-256。
- [ ] 重跑上一步命令；预期全部 PASS，不遗留 v1 fixture 失败。
- [ ] 建议提交：`git add creative_os/domains/narrative_decision.py creative_os/domains/narrative_codec.py tests/test_narrative_decision.py tests/test_narrative_codec.py tests/test_narrative_director.py tests/test_narrative_memory.py && git commit -m "feat: 原位升级章节合同并统一版本编解码"`

### Task 3: 因果路径与可选候选 fail-closed

**Files:** Create `creative_os/domains/narrative_causality.py`; Test `tests/test_narrative_causality.py`。

**Interfaces:** Consumes: Task 1 `ContractIssue`、Task 2 contract/candidate。Produces: `CAUSAL_FIELD_PATHS_V1`、`CausalAnalysisResult`、`CausalDependencyAnalyzer.analyze(candidate,profile,fact_snapshots,previous_chapter,change_requests)`。

- [ ] 写失败测试：全 causal path；yes+known 且入正式字段、no+rule/human decision、undetermined、分析异常、外层 arc/pressure 变化。
- [ ] 运行 `python -m pytest tests/test_narrative_causality.py -v`；预期 FAIL：模块不存在。
- [ ] 最小实现：仅显式直接引用规则自动裁决，其余 undetermined；异常转换为 Task 1 blocking issue。
- [ ] 运行 `python -m pytest tests/test_narrative_causality.py tests/test_narrative_decision.py -v`；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/narrative_causality.py tests/test_narrative_causality.py && git commit -m "feat: 增加叙事因果闭包分析"`

### Task 4: BaselineManifest 与专项审批策略

**Files:** Create `creative_os/domains/contract_baseline.py`, `creative_os/domains/contract_approval.py`; Test `tests/test_contract_baseline.py`, `tests/test_contract_approval.py`。

**Interfaces:** Consumes: Tasks 1–2。Produces: `BaselineEntry/BaselineManifest.build`；`ApprovalStatus/ApprovalItem/ContractApprovalRecord`；`ContractApprovalPolicy.required_items/covered_paths/required_reapprovals`。

- [ ] 写失败测试：manifest 稳定 fingerprint 与漂移；full 不可 N/A；专项 status/reason/human actor/time；非法 N/A、冲突、精确覆盖及重审集合。
- [ ] 运行 `python -m pytest tests/test_contract_baseline.py tests/test_contract_approval.py -v`；预期 FAIL。
- [ ] 最小实现：decision evidence 只在外部 ApprovalItem；policy 使用不可变路径表；fingerprint 为 sorted entries canonical hash。
- [ ] 加 `tests/test_memory_approval.py` 重跑；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/contract_baseline.py creative_os/domains/contract_approval.py tests/test_contract_baseline.py tests/test_contract_approval.py && git commit -m "feat: 增加合同基线与专项审批策略"`

### Task 5: ContractPreflightValidator

**Files:** Create `creative_os/domains/contract_preflight.py`; Modify `creative_os/domains/narrative_director.py`, `tests/test_narrative_director.py`; Test `tests/test_contract_preflight.py`。

**Interfaces:** Consumes: Tasks 1–4。Produces: `PreflightResult`、`ContractPreflightValidator.validate(candidate,sources,causal_result)`；Director 只产 candidate。

- [ ] 写失败测试：逐字段 unknown、数组逐元素 intent、N/A reason/evidence、Task/Director 同值与冲突、choice partial/unknown、causal 未决/失败、精确 issue。
- [ ] 运行 `python -m pytest tests/test_contract_preflight.py tests/test_narrative_director.py -v`；预期 FAIL。
- [ ] 最小实现：聚合 schema/字段/证据/N/A/因果；内部异常均转 blocking；Director 不审批/持久化。
- [ ] 加 evidence/causality 测试重跑；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/contract_preflight.py creative_os/domains/narrative_director.py tests/test_contract_preflight.py tests/test_narrative_director.py && git commit -m "feat: 建立章节合同预检门禁"`

### Task 6: 不可变物理存储与 pointer 原语

**Files:** Modify `creative_os/memory/store.py`, `creative_os/domains/narrative_memory.py`; Create `creative_os/domains/contract_lifecycle.py`; Test `tests/test_contract_storage.py`; Modify `tests/test_memory_store.py`。

**Interfaces:** Consumes: Task 2 codec/hash。Produces: `ContractPointer`、`physical_key`、`create_initial_candidate/load_current/read_pointer`；本任务不激活。

- [ ] 写失败测试：v0001、key/version/content/MemoryItem.version 一致；同 hash 重复写幂等、异 hash 拒绝；pointer 三字段；读取只认 pointer。
- [ ] 运行 `python -m pytest tests/test_contract_storage.py tests/test_memory_store.py -v`；预期 FAIL。
- [ ] 最小实现：不可变 item；pointer 路径 `.creative_os/memory/contracts/pointers/contract-current-NNN.json`，同目录原子 replace；合同不调用通用 `save_revision()`。
- [ ] 加 narrative_memory 回归；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/memory/store.py creative_os/domains/narrative_memory.py creative_os/domains/contract_lifecycle.py tests/test_contract_storage.py tests/test_memory_store.py && git commit -m "feat: 增加不可变合同存储与当前指针原语"`

### Task 7: ReviewerResult 与人工 disposition

**Files:** Create `creative_os/domains/contract_review.py`; Modify `creative_os/domains/narrative_review.py`, `tests/test_narrative_review.py`; Test `tests/test_contract_review.py`。

**Interfaces:** Consumes: Tasks 1,2,4。Produces: `ReviewIssue(issue_id,canonical_issue_hash,code,severity,blocking,requires_human_disposition,field_path,evidence_checks,evidence_hash,repair_hint)`；`PrewriteReviewerResult(result_id,contract_id,contract_version,contract_content_hash,baseline_fingerprint,ruleset_version,semantic_asset_versions,issues,result_hash)`；`ReviewIssueDisposition(issue_id,canonical_issue_hash,issue_code,field_path,evidence_hash,status,reason,actor,decided_at,reviewer_result_id,reviewer_result_hash)`；`validate_reviewer_gate`。

- [ ] 写失败测试：missing/stale result；所有绑定漂移；high 阻断；warning/`requires_human_disposition` 只接受同时匹配 reviewer result id/hash、issue id/canonical hash、code、field_path、evidence hash 的人工 accepted/resolved；同 code 不同路径或证据不得串用 disposition；无 blocking warning/需人工 issue 时空 disposition 集合合法；精确 choice issue。
- [ ] 运行 `python -m pytest tests/test_contract_review.py tests/test_narrative_review.py -v`；预期 FAIL。
- [ ] 最小实现：`canonical_issue_hash` 覆盖 code/severity/blocking/requires_human_disposition/field_path/evidence_checks；`evidence_hash` 覆盖 canonical evidence checks；result hash 覆盖全部绑定与 canonical issues；disposition 强制上述逐 issue 绑定及 human actor/reason/time。
- [ ] 加 replay 回归重跑；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/contract_review.py creative_os/domains/narrative_review.py tests/test_contract_review.py tests/test_narrative_review.py && git commit -m "feat: 增加版本化预写审阅与人工裁决"`

### Task 8: 权威合同记录 Store

**Files:** Create `creative_os/domains/contract_record_store.py`; Test `tests/test_contract_record_store.py`。

**Interfaces:** Consumes: Task 4 Baseline/Approval、Task 7 Reviewer/disposition。Produces: `ContractRecordStore.save_baseline/save_approval/save_reviewer_result/save_disposition`；每类 `load(record_id)`；`find_exact(contract_id,contract_version,contract_hash,baseline_fingerprint,ruleset_version=None)`；`recover()`。

- [ ] 写失败测试：物理键为 `baseline-{id}-vMMMM-{fingerprint}`、`approval-{id}-vMMMM-{hash}-{fingerprint}`、`review-{id}-vMMMM-{result_hash}`、`disposition-{result_id}-{issue_id}-{canonical_issue_hash}-{record_hash}`；同内容幂等/异内容拒绝；错误合同/issue/reviewer 绑定不返回；篡改拒绝；重启精确重建；prepare/write/commit 故障恢复。
- [ ] 运行 `python -m pytest tests/test_contract_record_store.py -v`；预期 FAIL。
- [ ] 最小实现：`.creative_os/memory/contract_records/{baselines,approvals,reviews,dispositions,journal}`；envelope 固定 `record_type/schema_version=1/payload_hash/payload`；append-only；journal+原子 replace；读取重算全部 hash/绑定。
- [ ] 加 baseline/approval/review/memory store 回归；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/contract_record_store.py tests/test_contract_record_store.py && git commit -m "feat: 增加合同审批与审阅权威记录仓"`

### Task 9: 首次激活与权威证明重读

**Files:** Modify `creative_os/domains/contract_lifecycle.py`, `creative_os/domains/narrative_memory.py`; Test `tests/test_contract_lifecycle_initial.py`。

**Interfaces:** Consumes: Tasks 5–8；API 只接收 id/version/hash/baseline fingerprint，不接收临时记录对象。Produces: `activate_initial(...)`、`recover_initial(contract_id)`。

- [ ] 写失败测试：未 save 的临时批准不生效；错 hash/version/baseline/ruleset、篡改记录均拒绝；只有 ReviewerResult 存在 blocking warning 或 `requires_human_disposition=true` issue 时，缺少针对该精确 issue 绑定的 disposition 才拒绝；无此类 issue 时空 disposition 不阻断；锁内重跑 Preflight/causal 时 partial/unknown、缺 intent、非法 N/A、undetermined 或 analyzer failure 即使四类记录齐全也拒绝且不创建 pointer；覆盖激活四步故障恢复、pointer 不得指缺证明合同、幂等。
- [ ] 运行 `python -m pytest tests/test_contract_lifecycle_initial.py -v`；预期 FAIL。
- [ ] 最小实现：锁内从 candidate 重算 hash，基于已持久化 baseline 来源重新执行 `ContractPreflightValidator.validate(...)` 与 `CausalDependencyAnalyzer.analyze(...)`，再用 Store exact read baseline/approval/reviewer；仅为 ReviewerResult 中 blocking warning/需人工 issue 逐一查找 exact disposition；所有 Gate 通过后才写 prepared，恢复时完整重跑同一顺序。
- [ ] 加 record/store/narrative_memory 回归；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/contract_lifecycle.py creative_os/domains/narrative_memory.py tests/test_contract_lifecycle_initial.py && git commit -m "feat: 以权威记录驱动首版合同激活"`

### Task 10: WriterAdmission 两阶段纯门禁、grant 与最终 token

**Files:** Create `creative_os/domains/writer_admission.py`; Test `tests/test_writer_admission.py`。

**Interfaces:** Consumes: current pointer、Task 8 Store、current Baseline、Preflight/causal analyzer、pending revision、`TokenSigner`。Produces: `AdmissionGrant(grant_id,project_id,chapter_id,contract_id,contract_version,contract_content_hash,baseline_fingerprint,reviewer_result_id,reviewer_result_hash,ruleset_version,semantic_asset_versions,projection,exclusions,issued_at,expires_at,signature)`；`WriterAdmissionService.pre_admit(request: PreAdmissionRequest) -> AdmissionGrant`；`WriterAdmissionService.finalize_admission(grant: AdmissionGrant, context_fingerprint: str, run_id: str) -> WriterAdmissionToken`；`validate_token(token,expected_run_id,actual_context_fingerprint)`。

- [ ] 写失败测试：`pre_admit` 重读 pointer/contract/baseline/approval/reviewer/精确 dispositions 并重跑 Preflight/causal；Store 缺/错/篡改、baseline/rules 漂移、审批冲突、causal 未决、pending revision 均不返回 grant；grant 短时签名且不含 context_fingerprint/run_id、不可当 Writer token；`finalize_admission` 对过期/伪造 grant、空 context/run、pointer/contract/baseline 漂移拒绝，并再次 exact read；最终 token 才绑定实际 context fingerprint/run id；mock 证明只用 Store，不接受临时记录参数。
- [ ] 运行 `python -m pytest tests/test_writer_admission.py -v`；预期 FAIL。
- [ ] 最小实现：`pre_admit` 按 current→contract hash→current baseline→Store exact→Preflight/causal→review gate→pending 顺序返回冻结 projection/exclusions 和短时 grant；`finalize_admission` 再验 grant 时效/签名及 current 四项绑定，之后把调用方提供的真实 context fingerprint 与 run id 纳入最终 HMAC token；本模块不编译 Context、不调用 Writer，禁止在 Context 生成前签发 `WriterAdmissionToken`。
- [ ] 加 record/lifecycle 回归；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/writer_admission.py tests/test_writer_admission.py && git commit -m "feat: 增加纯Writer准入与签名令牌"`

### Task 11: Context 冻结投影与排重

**Files:** Modify `creative_os/memory/context_compiler.py`, `creative_os/domains/novel_continuation.py`, `tests/test_narrative_continuation.py`; Test `tests/test_context_compiler.py`。

**Interfaces:** Consumes: Task 10 `AdmissionGrant.projection`、`AdmissionGrant.exclusions: tuple[ContextExclusion,...]`。Produces: `CompileRequest.contract_projection/exclusions`、`ContinuationTask.contract_projection`、`build_next_chapter(...,grant: AdmissionGrant) -> tuple[ContinuationTask,CompiledContext]`；真实 `CompiledContext.fingerprint` 供 `finalize_admission(grant, context.fingerprint, run_id)` 使用。

- [ ] 写失败测试：只接受有效未过期 grant；只注入一次 grant projection；同 key/version 和同章其他版本均排除；实际 fingerprint 绑定 projection/exclusion；编译本身不产生最终 token；AST 禁止 continuation 导入/调用 active loader 或 `finalize_admission`。
- [ ] 运行 `python -m pytest tests/test_context_compiler.py tests/test_narrative_continuation.py -v`；预期 FAIL：仍直读并重复注入。
- [ ] 最小实现：检索后、size/fingerprint 前排除；Knowledge 只由 projection 构造；删除 `narrative_contract` 字段。
- [ ] 运行 `python -m pytest tests/test_context_compiler.py tests/test_narrative_continuation.py tests/test_memory_retriever.py -v`；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/memory/context_compiler.py creative_os/domains/novel_continuation.py tests/test_context_compiler.py tests/test_narrative_continuation.py && git commit -m "feat: 使用冻结投影编译去重Context"`

### Task 12: 全部 Writer、晋升与发布出口

**Files:** Create `tests/assets/writer_production_exits_v1.json`, `tests/test_writer_production_exit_architecture.py`; Modify `creative_os/novel_continuation_runner.py`, `creative_os/llm_writer.py`, `tests/test_narrative_continuation.py`, `tests/test_llm_writer.py`; Test `tests/test_writer_admission_e2e.py`, `tests/test_phase_a_contract_restart.py`。

**Interfaces:** Consumes: Task 10 `pre_admit/finalize_admission/validate_token`，Task 11 `build_next_chapter(...,grant)` 与实际 `CompiledContext.fingerprint`。Produces: 编排 API `prepare_continuation_run(request,run_id) -> PreparedWriterRun(task,context,projection,token)` 严格执行 `pre_admit -> build real Context -> finalize_admission`；生产出口 `continue_one_chapter(prepared: PreparedWriterRun, client)`、`promote_passing_draft(prepared: PreparedWriterRun)`、`run_llm_writer_pilot(prepared: PreparedWriterRun, client)` 只接受内含最终 token 的 prepared run，并在副作用前以实际 `prepared.context.fingerprint/run_id` 验证；任何出口均不接受 grant。

- [ ] 先写静态清单测试：AST 扫描 `creative_os/**/*.py` 中 `(a)` `.complete(...)`/模型 client 调用，`(b)` `promote_passing_draft` 及任何 `promote_*`/`publish_*` 定义与调用，`(c)` 路径含 `production/final_chapters` 的 `write_text/open/replace`；冻结清单 `writer_production_exits_v1.json` 明列 `creative_os.novel_continuation_runner.continue_one_chapter`、`creative_os.novel_continuation_runner.promote_passing_draft`、`creative_os.llm_writer.run_llm_writer_pilot` 及扫描出的每个 sink 的文件、symbol、line-independent AST signature、kind。测试发现清单外 sink 或清单项消失均 FAIL。
- [ ] 写参数化出口测试：以冻结清单每项为参数，无最终 token、把 grant 冒充 token、旧 token、错误 contract hash、错误实际 context fingerprint、错误 run id、重复合同注入均拒绝，`client_calls == 0` 且 final writes/promotions == 0；有效最终 token 单次执行。架构测试禁止清单外代码直接调用模型 client、晋升函数或 final 正文写 sink。
- [ ] 运行 `python -m pytest tests/test_writer_admission_e2e.py tests/test_narrative_continuation.py tests/test_llm_writer.py -v`；预期 FAIL：promotion/legacy writer 可绕过。
- [ ] 最小实现：`prepare_continuation_run` 严格执行 pre_admit→真实 Context→finalize 并返回 immutable prepared run；三个生产出口只调用 `_require_writer_admission(prepared.token,prepared.run_id,prepared.context.fingerprint)` 后执行模型、draft 晋升或 final 写入；prompt 仅用 prepared projection；删除可选门禁开关，清单外 sink 改为调用受控出口。
- [ ] 写并运行重启 Gate：candidate→保存四类权威记录→激活→关闭全部 Store→重开→`pre_admit`→用 grant 编译真实 Context→`finalize_admission(grant,context.fingerprint,run_id)`→Runner 核对实际 fingerprint 后成功；参数化篡改/移除记录、在 pre/finalize 间漂移 pointer/baseline、替换 Context fingerprint，断言 finalize/Runner 拒绝且 Writer 不调用。
- [ ] Phase A 全量：运行 `python -m pytest tests/test_contract_issue.py tests/test_narrative_evidence.py tests/test_narrative_decision.py tests/test_narrative_codec.py tests/test_narrative_causality.py tests/test_contract_baseline.py tests/test_contract_approval.py tests/test_contract_preflight.py tests/test_contract_storage.py tests/test_contract_review.py tests/test_contract_record_store.py tests/test_contract_lifecycle_initial.py tests/test_writer_admission.py tests/test_context_compiler.py tests/test_narrative_continuation.py tests/test_writer_admission_e2e.py tests/test_phase_a_contract_restart.py -v`；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/novel_continuation_runner.py creative_os/llm_writer.py tests/assets/writer_production_exits_v1.json tests/test_writer_production_exit_architecture.py tests/test_writer_admission_e2e.py tests/test_phase_a_contract_restart.py tests/test_narrative_continuation.py tests/test_llm_writer.py && git commit -m "feat: 封闭全部Writer与正文晋升出口"`

---

## Phase B — 独立成稿证据闭环

### Task 13: 追加式 Fulfillment Store

**Files:** Create `creative_os/domains/contract_fulfillment.py`, `creative_os/domains/contract_fulfillment_store.py`; Test `tests/test_contract_fulfillment_store.py`。
**Interfaces:** Consumes: verification/realization EvidenceRef 与 contract id/version/hash。Produces: `ContractFulfillmentEvidenceRecord`、Store `append/records_for/active_records/recover`。
- [ ] 写失败测试：拒绝其他 role、重复 id、跨合同 supersede/环；幂等、并发、部分写恢复、重启、旧记录不变。
- [ ] 运行 `python -m pytest tests/test_contract_fulfillment_store.py -v`；预期 FAIL：Store 不存在。
- [ ] 最小实现：追加 JSONL+journal；更正仅追加 supersedes；不写合同/审批。
- [ ] 运行 `python -m pytest tests/test_contract_fulfillment_store.py tests/test_memory_store.py -v`；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/contract_fulfillment.py creative_os/domains/contract_fulfillment_store.py tests/test_contract_fulfillment_store.py && git commit -m "feat: 增加追加式合同成稿证据存储"`

### Task 14: FulfillmentEvaluator

**Files:** Modify `creative_os/domains/contract_fulfillment.py`, `creative_os/domains/narrative_review.py`; Test `tests/test_contract_fulfillment.py`。
**Interfaces:** Consumes: frozen contract、active records、evidence validator、artifact metadata。Produces: `FulfillmentStatus/ContractFulfillmentResult/ContractFulfillmentEvaluator.evaluate`。
- [ ] 写失败测试：普通叶三角色、空字段 intent+verification+N/A、metadata、意图不算完成、旧 hash stale、supersede、合同/approval hash 不变。
- [ ] 运行 `python -m pytest tests/test_contract_fulfillment.py -v`；预期 FAIL：Evaluator 不存在。
- [ ] 最小实现：枚举确定叶/数组索引，仅推导结果；Reviewer 只追加记录。
- [ ] 运行 `python -m pytest tests/test_contract_fulfillment.py tests/test_contract_fulfillment_store.py tests/test_writer_admission_e2e.py -v`；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/contract_fulfillment.py creative_os/domains/narrative_review.py tests/test_contract_fulfillment.py && git commit -m "feat: 增加章节合同成稿闭环评估"`

---

## Phase C — 冻结后安全修订

### Task 15: RevisionRequest 与重审集合

**Files:** Create `creative_os/domains/contract_revision.py`; Modify `creative_os/domains/contract_approval.py`; Test `tests/test_contract_revision.py`。
**Interfaces:** Consumes: current/replacement、approved change request、policy。Produces: 完整 `ContractRevisionRequest` 与 canonical leaf diff。
- [ ] 写失败测试：版本+1/base hash、精确 diff、重大变更引用、post_freeze+full+专项、baseline 新 Reviewer。
- [ ] 运行 `python -m pytest tests/test_contract_revision.py -v`；预期 FAIL：RevisionRequest 不存在。
- [ ] 最小实现：Request 外置，数组稳定索引，旧合同不改。
- [ ] 运行 `python -m pytest tests/test_contract_revision.py tests/test_contract_approval.py -v`；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/contract_revision.py creative_os/domains/contract_approval.py tests/test_contract_revision.py && git commit -m "feat: 增加冻结合同修订请求与重审计算"`

### Task 16: replacement CAS、历史与恢复

**Files:** Modify `creative_os/domains/contract_lifecycle.py`, `creative_os/domains/narrative_memory.py`; Test `tests/test_contract_lifecycle_replacement.py`。
**Interfaces:** Consumes: Task 15、权威 Store、expected pointer。Produces: `create_replacement_candidate/switch_replacement/recover_switch/list_contract_versions`。
- [ ] 写失败测试：old ACTIVE+new CANDIDATE、连续版本、Store exact 重读新证明、五步故障矩阵、CAS 冲突、隔离、旧文件不变。
- [ ] 运行 `python -m pytest tests/test_contract_lifecycle_replacement.py -v`；预期 FAIL：replacement API 不存在。
- [ ] 最小实现：prepare→new ACTIVE→pointer CAS→old ARCHIVED→commit；恢复不猜测。
- [ ] 运行 `python -m pytest tests/test_contract_lifecycle_replacement.py tests/test_contract_lifecycle_initial.py tests/test_contract_record_store.py -v`；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/contract_lifecycle.py creative_os/domains/narrative_memory.py tests/test_contract_lifecycle_replacement.py && git commit -m "feat: 增加修订合同CAS切换与恢复"`

### Task 17: 旧 run 受限继续授权

**Files:** Modify `creative_os/domains/contract_revision.py`, `creative_os/domains/contract_record_store.py`, `creative_os/domains/writer_admission.py`, `creative_os/novel_continuation_runner.py`; Test `tests/test_writer_run_continuation.py`。
**Interfaces:** Produces: `WriterRunContinuationAuthorization(run_id,old_contract_id,old_contract_version,old_contract_hash,actor,reason,created_at,expires_at,status)`；Store `save/load/find_exact_continuation_authorization`；`issue_restricted_continuation_token`。
- [ ] 写失败测试：切换后旧 token 失效；授权仅指定旧 run/contract、人工追加式保存；不能用于新约/其他 run；过期/撤销；验证顺序及新受限 token。
- [ ] 运行 `python -m pytest tests/test_writer_run_continuation.py -v`；预期 FAIL：authorization 与受限 token 不存在。
- [ ] 最小实现：唯一方案为“权威授权记录签发新受限 token”；撤销追加 superseding record；token 含 authorization_id/restricted_old_run，runner 每次重查状态。
- [ ] 运行 `python -m pytest tests/test_contract_revision.py tests/test_contract_lifecycle_replacement.py tests/test_writer_run_continuation.py tests/test_writer_admission_e2e.py -v`；预期全部 PASS 且无零活动窗口。
- [ ] 建议提交：`git add creative_os/domains/contract_revision.py creative_os/domains/contract_record_store.py creative_os/domains/writer_admission.py creative_os/novel_continuation_runner.py tests/test_writer_run_continuation.py && git commit -m "feat: 增加旧写作运行受限继续授权"`

---

## Phase D — 回放迁移与语义重复

### Task 18: ReplayContractCodec 与 partial 回放

**Files:** Modify `creative_os/domains/narrative_replay_model.py`, `creative_os/domains/narrative_replay.py`, `creative_os/domains/narrative_replay_store.py`, `tests/test_narrative_replay_models.py`, `tests/test_narrative_replay.py`, `tests/test_narrative_replay_store.py`, `tests/test_narrative_review.py`; Create `creative_os/domains/narrative_replay_codec.py`; Test `tests/test_narrative_replay_codec.py`。
**Interfaces:** Produces: 独立 `ReplayContractCodec`、`ReplayedProtagonistChoice(status,missing_fields,...)`，永不返回正式合同。
- [ ] 写失败测试：v1/v2 round-trip、legacy evidence 不准入、第5章 candidate、第2–4章 partial、精确 checks、旧报告可读。
- [ ] 运行 `python -m pytest tests/test_narrative_replay_codec.py tests/test_narrative_replay_models.py tests/test_narrative_replay.py -v`；预期 FAIL：codec/status 不存在。
- [ ] 最小实现：独立分派，逐 choice 字段/数组索引生成状态和 issue。
- [ ] 运行 `python -m pytest tests/test_narrative_replay_codec.py tests/test_narrative_replay_models.py tests/test_narrative_replay.py tests/test_narrative_replay_store.py tests/test_narrative_review.py -v`；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/narrative_replay_model.py creative_os/domains/narrative_replay_codec.py creative_os/domains/narrative_replay.py creative_os/domains/narrative_replay_store.py tests/test_narrative_replay_codec.py tests/test_narrative_replay_models.py tests/test_narrative_replay.py && git commit -m "feat: 升级回放合同版本与字段证据"`

### Task 19: LegacyNarrativeAdapter 幂等迁移

**Files:** Create `creative_os/domains/legacy_narrative_adapter.py`, `creative_os/domains/narrative_migration.py`; Test `tests/test_legacy_narrative_adapter.py`, `tests/test_narrative_migration.py`。
**Interfaces:** Produces: `MigrationReport`、Adapter `adapt`、MigrationService `migrate/recover`。
- [ ] 写失败测试：三元组幂等、派生 chapter_id 记 loss、legacy evidence/N/A 待人工、旧 ACTIVE 不自动审批/pointer、部分失败复用 candidate、hash 异常隔离、完成章只回放。
- [ ] 运行 `python -m pytest tests/test_legacy_narrative_adapter.py tests/test_narrative_migration.py -v`；预期 FAIL：adapter/service 不存在。
- [ ] 最小实现：adapter 纯函数；journal 三阶段；失败不移 pointer。
- [ ] 运行 `python -m pytest tests/test_legacy_narrative_adapter.py tests/test_narrative_migration.py tests/test_narrative_codec.py tests/test_narrative_replay_codec.py -v`；预期全部 PASS。
- [ ] 建议提交：`git add creative_os/domains/legacy_narrative_adapter.py creative_os/domains/narrative_migration.py tests/test_legacy_narrative_adapter.py tests/test_narrative_migration.py && git commit -m "feat: 增加旧叙事合同幂等迁移"`

### Task 20: 版本化本地语义资产

**Files:** Create `creative_os/assets/function_semantics/v1/action_lexicon.json`, `creative_os/assets/function_semantics/v1/stop_phrases.json`, `creative_os/assets/function_semantics/v1/function_types.json`, `creative_os/assets/function_semantics/v1/entity_slots.json`, `creative_os/assets/function_semantics/v1/cases.json`, `creative_os/domains/narrative_semantics.py`; Test `tests/test_narrative_semantics.py`; Modify `creative_os/domains/narrative_progression.py`, `creative_os/domains/contract_review.py`, `tests/test_narrative_review.py`。
**Interfaces:** Produces: `FunctionSemanticKey`、`FunctionSemanticNormalizer.normalize`、`SemanticComparison(relation,evidence,asset_versions)`。
- [ ] 写失败测试：同结构 repeated blocking；合法升级 non-blocking；词典外 uncertain blocking；否定词保留；仅批准实体别名；资产版本变化使 review stale。
- [ ] 运行 `python -m pytest tests/test_narrative_semantics.py tests/test_narrative_review.py -v`；预期 FAIL：资产与 normalizer 不存在。
- [ ] 最小实现：校验五个 v1 JSON；七段比较键；无外部模型。
- [ ] 运行 Phase D 后 `python -m pytest -q`；预期全部 PASS；`rg` 确认生产入口无 active loader；`git diff --check` 退出 0。
- [ ] 建议提交：`git add creative_os/assets/function_semantics/v1 creative_os/domains/narrative_semantics.py creative_os/domains/narrative_progression.py creative_os/domains/contract_review.py tests/test_narrative_semantics.py tests/test_narrative_review.py && git commit -m "feat: 增加版本化叙事语义重复门禁"`

## Final acceptance matrix

| Gate | Tasks |
|---|---|
| 公共类型无未来引用、EvidenceRef 唯一归属 | 1–3 |
| 原位 v2、codec、每任务全绿 | 2 |
| Baseline/审批/Reviewer/disposition 权威追加式闭环 | 4、7–10 |
| 篡改、错误绑定、幂等、重启、部分写恢复 | 8–9、12 |
| 首次激活重读证明，pointer 不悬空 | 9 |
| Admission 只读 Store、Context 排重、全部生产出口 | 10–12 |
| fulfillment | 13–14 |
| replacement/CAS/旧 token/受限旧 run | 15–17 |
| replay/迁移/语义 | 18–20 |

## Plan self-review

- [x] P0/P1 与设计第 5–16 节均映射到明确任务和 Gate。
- [x] 无未决占位语句或模糊错误处理。
- [x] `ContractIssue` 在 Task 1，EvidenceRef 仅归 `narrative_evidence.py`，无未来类型引用。
- [x] 每个任务要求自身与相关回归全绿；Task 2 同步修复 v1 fixtures。
- [x] Phase A 独立完成权威证明、重启恢复与全部生产出口，B/C/D 不补建 A 的基础能力。
- [x] 两阶段 token 无循环：pre_admit 只返回 grant/projection/exclusions；Context 生成真实 fingerprint；finalize 再校验漂移并签最终 token；生产出口只接收最终 token。
- [x] disposition 精确绑定 reviewer result 与 issue id/hash/code/path/evidence hash；无 blocking warning/需人工 issue 时不要求 disposition。
- [x] 生产出口由版本化 JSON 清单和 AST 规则冻结，新增或遗漏 sink 均由架构测试判定失败。
- [x] Lifecycle/Admission 不接受调用方临时审批事实，只接受权威 Store exact read；缺证明不创建/不信任 pointer。
- [x] Preflight、Policy、Record Store、Lifecycle、Admission、Context、Runner、Fulfillment 职责分离。
- [x] 本任务只修改计划，未实现、未提交、未推送。

## Execution handoff

建议通过新 Gate 后执行：先完成 Phase A Tasks 1–12，以 Task 12 的“关闭并重开全部 Store”集成测试为硬门槛，通过后才进入 Phase B。推荐 `superpowers:subagent-driven-development`，或使用 `superpowers:executing-plans` 按 Phase 设置检查点。
