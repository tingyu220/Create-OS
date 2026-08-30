# Production Mainline Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Phase E 权威生产编排、场景/技术与 POV 门禁、第 7–26 章生产事实以及第 2 章修复整合为可从第 27 章继续生产的单一主线。

**Architecture:** 以 `codex/narrative-director-contract-approval` 的 Phase E 权威链为集成基线，通过显式合并保留分支历史；冲突代码按“Phase E 生命周期拥有生产权，Scene/Technology/POV 作为合同与 Admission 的附加阻断条件”组合。项目产物必须先通过一致性审计，再重建第 27 章 Readiness，历史 hash 记录不得人工改写冒充有效。

**Tech Stack:** Python 3.12、pytest、dataclasses、canonical JSON/JSONL、Git worktree。

**Spec:** `docs/superpowers/specs/2026-08-22-phase-e-web-novel-production-quality-gate-design.md`、`docs/superpowers/specs/2026-08-24-scene-and-technology-gates-design.md`、`docs/superpowers/specs/2026-08-25-pov-strategy-planner-design.md`

## Global Constraints

- Phase E Orchestrator、Admission、Context、Reviewer 与 State materialization 保持唯一生产入口。
- Chapter Contract 新生产只接受 schema v2，并同时验证 Scene、Technology、POV 与 SupportingAgency。
- 不修改已有 append-only 记录；失效记录通过新审计、修订或重新物化处理。
- 不生成第 27 章正文，不调用真实模型，不推送、不合并到其他长期分支。
- 临时文件、锁文件、`.bak`、`.pytest-tmp`、`.t` 不进入版本控制。

---

### Task 1: 合并三条已批准历史

**Files:**
- Modify: Git history on `codex/production-mainline-integration`
- Test: `tests/`

**Interfaces:**
- Consumes: Phase E HEAD `96d9894`、内容/POV HEAD `1693bb8`、第 2 章修复 `acaaa24`
- Produces: 保留三条父系来源的集成工作树与显式冲突清单

- [ ] **Step 1: 验证 Phase E 基线**

Run: `python -m pytest -q`
Expected: PASS，且合并前工作树干净。

- [ ] **Step 2: 合并内容/POV 分支并保留冲突状态**

Run: `git merge --no-ff --no-commit codex/legacy-novel-continuation`
Expected: 仅共同修改的 Narrative/Continuation/Runner/Validation 文件出现冲突；新增 POV 文件与章节产物进入索引。

- [ ] **Step 3: 记录冲突文件并禁止整文件偏向任一侧**

Run: `git diff --name-only --diff-filter=U`
Expected: 每个冲突文件逐段组合，禁止使用全局 `--ours` 或 `--theirs` 覆盖生产代码。

- [ ] **Step 4: 合入第 2 章修复**

Run: `git merge --no-ff --no-commit codex/fix-chapter-002-version-conflict`
Expected: 第 2 章只保留龙渊主线，连续性测试进入索引。

### Task 2: 组合合同模型与生产门禁

**Files:**
- Modify: `creative_os/domains/narrative_decision.py`
- Modify: `creative_os/domains/narrative_director.py`
- Modify: `creative_os/domains/narrative_review.py`
- Modify: `creative_os/domains/novel_continuation.py`
- Modify: `creative_os/novel_continuation_runner.py`
- Modify: `creative_os/validation_runtime.py`
- Test: `tests/test_narrative_decision.py`
- Test: `tests/test_narrative_director.py`
- Test: `tests/test_narrative_review.py`
- Test: `tests/test_pov_strategy_admission.py`
- Test: `tests/test_phase_e_composition_root.py`

**Interfaces:**
- Consumes: Phase E `WriterAdmissionService`/Orchestrator；`ScenePlan`、`TechnologyPlan`、`PointOfViewPlan`、`SupportingAgencyContract`
- Produces: 单一 `ChapterContract` codec 与不可绕过的组合 Admission

- [ ] **Step 1: 运行冲突相关测试取得 RED**

Run: `python -m pytest tests/test_narrative_decision.py tests/test_narrative_director.py tests/test_narrative_review.py tests/test_pov_strategy_admission.py -q`
Expected: 合并未闭合前因导入、schema 或门禁缺失而 FAIL。

- [ ] **Step 2: 合并 ChapterContract 字段与 codec**

保留 Phase E 合同 identity/hash/baseline 绑定，并加入 Scene、Technology、POV、SupportingAgency 字段；v1 仅允许读取，新生产强制 v2。

- [ ] **Step 3: 合并 Director 与 Reviewer 校验**

Director 同时校验因果闭包、场景能力、技术角色、POV 选择与配角能动性；Reviewer 将各类问题作为精确 `ContractIssue` 输出。

- [ ] **Step 4: 合并 Admission 与 Runner**

`pre_admit`、`finalize_admission` 和生产出口继续以 Phase E 锁内权威读取为主，POV selection/stale 仅作为附加 fail-closed 条件，不新增直达 Writer 路径。

- [ ] **Step 5: 运行组合回归**

Run: `python -m pytest tests/test_narrative_decision.py tests/test_narrative_director.py tests/test_narrative_review.py tests/test_pov_strategy_admission.py tests/test_phase_e_composition_root.py -q`
Expected: PASS。

### Task 3: 审计并接纳第 7–26 章权威产物

**Files:**
- Modify: `projects/文明升阶/.creative_os/`
- Modify: `projects/文明升阶/production/contracts/`
- Modify: `projects/文明升阶/production/final_chapters/`
- Modify: `projects/文明升阶/production/reports/`
- Test: `tests/test_production_mainline_integration.py`

**Interfaces:**
- Consumes: 第 7–26 章合同、Context、Review、Memory、运行状态与最终正文
- Produces: 内容 hash、合同 hash、Context fingerprint、Review artifact hash 可机械核对的集成报告

- [ ] **Step 1: 写一致性 RED 测试**

测试必须断言：最终章节连续为 1–26；第 2 章禁入提前世界观；第 7–26 章合同均为 schema v2；第 20/22/23 章裁决保持；第 24–26 章 POV 与正文主角出场事实一致。

- [ ] **Step 2: 运行测试确认过期记录被识别**

Run: `python -m pytest tests/test_production_mainline_integration.py -q`
Expected: 对不兼容 hash、旧 schema 或错误章号明确 FAIL，而不是静默接纳。

- [ ] **Step 3: 通过权威恢复/迁移接口追加修订**

只使用现有 Store、codec、migration/recovery API；不得直接重写 append-only JSONL。无法证明的旧运行记录标记 stale，并由当前正文重建派生投影。

- [ ] **Step 4: 运行一致性测试**

Run: `python -m pytest tests/test_production_mainline_integration.py -q`
Expected: PASS。

### Task 4: 重建第 27 章 Readiness 与 POV 候选

**Files:**
- Modify: `projects/文明升阶/production/reports/continuation_readiness.md`
- Create: `projects/文明升阶/production/reports/production_mainline_integration_audit.md`
- Modify: `docs/novel-production-roadmap.md`
- Test: `tests/test_production_mainline_integration.py`

**Interfaces:**
- Consumes: 第 26 章最终状态、最新 Baseline、活动合同链、POVStrategyPlanner 当前权威输入
- Produces: `next_chapter=27` 的 readiness 与未激活 POV candidate；不产生正文或 PreparedWriterRun

- [ ] **Step 1: 写 Readiness RED 测试**

断言报告下一章为 27、引用第 26 章 exact Baseline、POV candidate 的 input fingerprint 当前有效，并且不存在第 27 章正文。

- [ ] **Step 2: 运行生产恢复与 Planner 候选流程**

使用 CompositionRoot/Director 的公开入口重读 Store，生成第 27 章候选；候选只进入审批前状态，不创建 Writer token。

- [ ] **Step 3: 更新路线图与集成审计**

路线图记录 Phase E、Scene/Technology、POV 已整合；下一生产 Gate 固定为“人工批准第 27 章合同与 POV 选择”。

- [ ] **Step 4: 运行 Readiness 测试**

Run: `python -m pytest tests/test_production_mainline_integration.py -q`
Expected: PASS。

### Task 5: 最终 Gate 与本地固化

**Files:**
- Verify: entire repository

**Interfaces:**
- Consumes: Tasks 1–4 的集成树
- Produces: 可审查的集成分支；不推送、不合并到长期分支

- [ ] **Step 1: 全量测试**

Run: `python -m pytest -q`
Expected: PASS，无失败。

- [ ] **Step 2: 编译、冲突和架构扫描**

Run: `python -m compileall -q creative_os; git grep -n '<<<<<<<\|=======\|>>>>>>>'; git diff --check`
Expected: 编译通过、无冲突标记、无 whitespace error。

- [ ] **Step 3: 检查生产出口与敏感信息**

验证 Writer/Promotion manifest 与 AST 一致；暂存项不含 `.env`、凭据、锁、备份或临时目录。

- [ ] **Step 4: 创建中文本地提交**

Run: `git commit -m "feat: 整合小说生产主线并准备第27章"`
Expected: 提交成功，工作树仅允许保留被忽略的运行时临时项。
