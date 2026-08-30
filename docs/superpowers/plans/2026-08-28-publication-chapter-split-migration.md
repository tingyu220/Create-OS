# 《文明升阶》发布版拆章迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 冻结已发布第1—4章，将现有第5—32章按戏剧节点迁移为3000—4500中文字符的新连续发布版，并重建可恢复、不可混读的逐章权威链。

**Architecture:** 新增独立的发布版迁移域，使用 canonical Manifest、不可变源快照、候选拆分计划和单一活动版 pointer 管理迁移。内容批次先写入隔离目标版，全部完成后才在项目权威锁内一次性激活；Narrative Director、Writer Admission、Review、Fulfillment 和 State 继续复用现有实现，不建立第二事实源。

**Tech Stack:** Python 3.12、dataclasses、canonical JSON/JSONL、SHA-256、pytest、现有 Creative OS authority stores 与 production composition root。

**Spec:** `docs/superpowers/specs/2026-08-28-publication-chapter-split-migration-design.md`

## Global Constraints

- 第1—4章正文、编号和迁移前 SHA-256 必须保持不变。
- 迁移源仅为当前第5—32章；不得生成原第32章结局之后的新剧情。
- 新章目标3000—4500中文字符；5000为软上限；5500为硬上限；低于2500必须有人工批准的短章理由。
- 切点必须位于完整戏剧节点，禁止按字符数机械切割。
- 旧资料必须先复制、后哈希验证；禁止删除、移动或覆盖。
- 任何源片段必须恰好进入一个目标章或进入带理由的 `omissions`。
- 每个新章独立重建 POV、Chapter Contract、Approval、Context、Admission、Review、Quality、Fulfillment、State 与 next Baseline。
- 迁移批次不得提前暴露给生产入口；仅全部完成后切换活动版 pointer。
- 所有 Windows 命令通过动态解析的 PowerShell 7+ 执行。
- 当前工作树包含既有未提交改动；只修改本计划列出的精确路径，不清理 `.bak/.pytest-tmp/.t`。
- 本目标不暂存、不提交、不推送、不合并；每个 Task 的最后一步是状态与 diff 检查，不执行 Git commit。

---

### Task 1: 发布版迁移领域模型与严格 Codec

**Files:**
- Create: `creative_os/domains/publication_migration_model.py`
- Create: `creative_os/domains/publication_migration_codec.py`
- Test: `tests/test_publication_migration_model.py`

**Interfaces:**
- Consumes: 标准库 `dataclass`、`Enum`、`hashlib.sha256`。
- Produces: `SourceFragment`, `MigrationOmission`, `PublicationChapterEntry`, `PublicationLengthPolicy`, `PublicationChapterMigrationManifest`, `MigrationCheckpoint`, `ManifestStatus`, `encode_manifest(manifest) -> str`, `decode_manifest(payload) -> PublicationChapterMigrationManifest`, `manifest_hash(manifest) -> str`。

- [ ] **Step 1: 写领域不变量 RED 测试**

```python
def test_manifest_rejects_duplicate_source_fragment_consumption():
    fragment = SourceFragment(5, 1, 20, "a" * 64)
    with pytest.raises(ValueError, match="duplicate_source_fragment"):
        PublicationChapterMigrationManifest.build(
            migration_id="civilization-v1-to-publication-v2",
            frozen_through_chapter=4,
            source_chapter_range=(5, 32),
            entries=(entry(5, fragment), entry(6, fragment)),
            omissions=(),
        )
```

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/test_publication_migration_model.py`

Expected: FAIL，迁移领域模块不存在。

- [ ] **Step 3: 实现精简不可变模型与 canonical Codec**

```python
@dataclass(frozen=True)
class PublicationLengthPolicy:
    target_min: int = 3000
    target_max: int = 4500
    soft_max: int = 5000
    hard_max: int = 5500
    short_min: int = 2500

@dataclass(frozen=True)
class SourceFragment:
    source_chapter: int
    paragraph_start: int
    paragraph_end: int
    source_text_hash: str

class ManifestStatus(str, Enum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    REBUILT = "rebuilt"
    VERIFIED = "verified"
    ACTIVATED = "activated"
```

Codec 必须拒绝未知字段、非 canonical hash、倒序段落、非连续目标章号和重复来源片段；业务 hash 不包含 `manifest_hash` 自身。

- [ ] **Step 4: 补 codec/hash/往返/篡改测试并运行 GREEN**

Run: `python -m pytest -q tests/test_publication_migration_model.py`

Expected: PASS。

- [ ] **Step 5: 检查本任务边界**

Run: `git diff --check -- creative_os/domains/publication_migration_model.py creative_os/domains/publication_migration_codec.py tests/test_publication_migration_model.py`

Expected: exit 0；不暂存、不提交。

### Task 2: 追加式 Manifest、Checkpoint 与活动版 Pointer Store

**Files:**
- Create: `creative_os/runtime/publication_migration_store.py`
- Test: `tests/test_publication_migration_store.py`

**Interfaces:**
- Consumes: Task 1 的 manifest/codec/hash 类型。
- Produces: `PublicationMigrationStore(root: Path)`, `append_manifest(manifest) -> str`, `load_exact(migration_id, manifest_hash)`, `append_checkpoint(checkpoint)`, `recover(migration_id)`, `load_active_edition()`, `activate_verified_manifest(manifest_hash, lock_context)`。

- [ ] **Step 1: 写追加链、重启和篡改 RED 测试**

```python
def test_store_reopens_verified_manifest_and_rejects_tampered_chain(tmp_path):
    store = PublicationMigrationStore(tmp_path)
    digest = store.append_manifest(approved_manifest())
    reopened = PublicationMigrationStore(tmp_path)
    assert reopened.load_exact("civilization-v1-to-publication-v2", digest).status is ManifestStatus.APPROVED
    tamper_first_jsonl_record(tmp_path / ".creative_os/publication_migration/manifests.jsonl")
    with pytest.raises(PublicationMigrationIntegrityError):
        PublicationMigrationStore(tmp_path).recover("civilization-v1-to-publication-v2")
```

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/test_publication_migration_store.py`

Expected: FAIL，Store 不存在。

- [ ] **Step 3: 实现 JSONL hash-chain、head、journal 与 pointer CAS**

物理目录固定为 `.creative_os/publication_migration/`；每条 envelope 包含 `sequence`、`previous_hash`、`payload_hash`、`envelope_hash`。pointer 只允许指向 `VERIFIED` manifest，激活在调用方提供的 `ProjectAuthorityTransaction` 锁内执行。

- [ ] **Step 4: 覆盖幂等、冲突、部分写、崩溃点和跨进程恢复**

Run: `python -m pytest -q tests/test_publication_migration_store.py`

Expected: PASS；pointer 不暴露 candidate/rebuilt 状态。

- [ ] **Step 5: 检查本任务边界**

Run: `git diff --check -- creative_os/runtime/publication_migration_store.py tests/test_publication_migration_store.py`

Expected: exit 0；不暂存、不提交。

### Task 3: 冻结基线、不可变源快照与完整覆盖清单

**Files:**
- Create: `creative_os/domains/publication_source_snapshot.py`
- Test: `tests/test_publication_source_snapshot.py`

**Interfaces:**
- Consumes: 项目 `production/final_chapters/chapter_NNN.md`、Task 1 `SourceFragment`。
- Produces: `build_source_snapshot(project_root, 4, range(5, 33)) -> SourceEditionSnapshot`, `verify_snapshot(snapshot)`, `copy_verified_source_archive(snapshot, target_root) -> ArchiveReceipt`。

- [ ] **Step 1: 写冻结哈希与备份完整性 RED 测试**

```python
def test_snapshot_freezes_1_to_4_and_archives_5_to_32_without_mutation(project_fixture):
    before = hashes(project_fixture, range(1, 33))
    snapshot = build_source_snapshot(project_fixture, 4, range(5, 33))
    receipt = copy_verified_source_archive(snapshot, project_fixture)
    assert receipt.verified_file_count == 28
    assert hashes(project_fixture, range(1, 33)) == before
```

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/test_publication_source_snapshot.py`

Expected: FAIL，snapshot 服务不存在。

- [ ] **Step 3: 实现逐文件 SHA-256、段落定位与复制后重读校验**

归档路径固定为 `.creative_os/publication_migration/source_editions/<source_edition_id>/`。使用复制，不使用移动；目标已存在且 hash 不同必须报 `archive_conflict`。

- [ ] **Step 4: 增加冻结章漂移、源章漂移、缺章、归档篡改测试**

Run: `python -m pytest -q tests/test_publication_source_snapshot.py`

Expected: PASS。

- [ ] **Step 5: 检查本任务边界**

Run: `git diff --check -- creative_os/domains/publication_source_snapshot.py tests/test_publication_source_snapshot.py`

Expected: exit 0；不暂存、不提交。

### Task 4: 戏剧单元拆分 Planner 与人工审批记录

**Files:**
- Create: `creative_os/domains/publication_split_planner.py`
- Create: `creative_os/runtime/publication_split_approval_store.py`
- Test: `tests/test_publication_split_planner.py`

**Interfaces:**
- Consumes: `SourceEditionSnapshot`、旧活动 Chapter Contract、POV、ScenePlan、正文段落。
- Produces: `DramaticUnit`, `SplitPlanCandidate`, `plan_source_chapters(snapshot, contracts)`, `SplitPlanApprovalStore.append_decision(candidate_hash, actor, reason, approved)`。

- [ ] **Step 1: 写禁止机械切割与因果闭包 RED 测试**

```python
def test_split_planner_rejects_boundary_inside_open_dialogue_or_unresolved_choice():
    candidate = candidate_with_cut_after_opening_quote()
    issues = PublicationSplitPlanner().review(candidate)
    assert {issue.code for issue in issues} >= {"cut_inside_dialogue", "dramatic_unit_incomplete"}
```

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/test_publication_split_planner.py`

Expected: FAIL。

- [ ] **Step 3: 实现 Planner 纯决策与审批 Store**

`DramaticUnit` 必须包含 `function`、`conflict`、`choice_or_discovery`、`state_shift`、`ending_hook`、`source_fragments`、`estimated_chinese_chars`。Planner 只输出候选，不写正文、不激活 Manifest。

- [ ] **Step 4: 测试人工审批 hash binding、stale、重启与候选篡改**

Run: `python -m pytest -q tests/test_publication_split_planner.py`

Expected: PASS。

- [ ] **Step 5: 检查本任务边界**

Run: `git diff --check -- creative_os/domains/publication_split_planner.py creative_os/runtime/publication_split_approval_store.py tests/test_publication_split_planner.py`

Expected: exit 0；不暂存、不提交。

### Task 5: 长度、切点、钩子与内容覆盖 Review

**Files:**
- Create: `creative_os/domains/publication_length_review.py`
- Create: `creative_os/runtime/publication_length_disposition_store.py`
- Test: `tests/test_publication_length_review.py`
- Test: `tests/test_publication_length_disposition_store.py`

**Interfaces:**
- Consumes: `PublicationLengthPolicy`, `SplitPlanCandidate`, 目标正文、Manifest entry。
- Produces: `PublicationChapterReview`, `PublicationIssue`, `review_publication_chapter(entry, text, policy)`, `verify_source_coverage(snapshot, entries, omissions)`，以及写后 `PublicationLengthDispositionStore`。长度例外必须绑定目标正文与 policy 的写后权威决定，不得复用写前 `SplitPlanApprovalStore` 审批。

- [ ] **Step 1: 写硬上限、短章理由、重复消费和静默遗漏 RED 测试**

```python
def test_review_blocks_hard_limit_and_unmapped_source_paragraph():
    review = review_publication_chapter(entry(), "文" * 5501, PublicationLengthPolicy())
    assert "chapter_length_hard_limit" in review.blocking_codes
    with pytest.raises(SourceCoverageError, match="unmapped_source_fragment"):
        verify_source_coverage(snapshot_with_three_paragraphs(), entries_covering_first_two(), ())
```

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/test_publication_length_review.py`

Expected: FAIL。

- [ ] **Step 3: 实现确定性长度与覆盖 Gate**

字符统计只计 `\u4e00-\u9fff`；5001—5500要求绑定人工 disposition；低于2500要求 `short_chapter_reason` 和审批；章末必须是完整句并有合同 ending hook 的正文证据。

- [ ] **Step 4: 增加高潮后重复证明、截断句尾、顺序颠倒负测**

Run: `python -m pytest -q tests/test_publication_length_review.py`

Expected: PASS。

- [ ] **Step 5: 检查本任务边界**

Run: `git diff --check -- creative_os/domains/publication_length_review.py tests/test_publication_length_review.py`

Expected: exit 0；不暂存、不提交。

### Task 6: 隔离目标版工作区与迁移编排 Service

**Files:**
- Create: `creative_os/domains/publication_migration_service.py`
- Test: `tests/test_publication_migration_service.py`

**Interfaces:**
- Consumes: Tasks 1—5、`ProjectAuthorityTransaction`、现有 authority composition root。
- Produces: `PublicationMigrationService.snapshot()`, `approve_plan()`, `rebuild_content_batch()`, `rebuild_authority_batch()`, `verify_batch()`, `activate()`。

- [ ] **Step 1: 写目标版不暴露与恢复 RED 测试**

```python
def test_rebuilt_batch_is_invisible_until_whole_manifest_activation(project_fixture):
    service = migration_service(project_fixture)
    service.rebuild_content_batch(batch_id="source-005-010")
    assert active_final_chapter(project_fixture, 5) == original_chapter_005(project_fixture)
    assert target_edition_chapter(project_fixture, 5).exists()
```

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/test_publication_migration_service.py`

Expected: FAIL。

- [ ] **Step 3: 实现阶段编排与 checkpoint 恢复**

目标版固定写入 `.creative_os/publication_migration/target_editions/civilization-publication-v2/`。每一步精确重读 Store，不接受调用方临时 manifest 冒充已批准对象。

- [ ] **Step 4: 增加批次部分写、重复执行、输入漂移和错误 edition 测试**

Run: `python -m pytest -q tests/test_publication_migration_service.py`

Expected: PASS。

- [ ] **Step 5: 检查本任务边界**

Run: `git diff --check -- creative_os/domains/publication_migration_service.py tests/test_publication_migration_service.py`

Expected: exit 0；不暂存、不提交。

### Task 7: 活动 Edition 绑定生产入口与旧版防混读

**Files:**
- Create: `creative_os/domains/publication_edition.py`
- Modify: `creative_os/novel_continuation_runner.py`
- Modify: `creative_os/domains/writer_admission.py`
- Modify: `creative_os/domains/chapter_production_owner_registry.py`
- Modify: `tests/assets/writer_production_exits_v1.json`
- Test: `tests/test_publication_edition_admission.py`

**Interfaces:**
- Consumes: `PublicationMigrationStore.load_active_edition()`。
- Produces: `ActivePublicationEdition`, edition-bound Context/Admission/Writer token，生产出口 edition 验证。

- [ ] **Step 1: 写旧版混读与旧 token RED 测试**

```python
def test_writer_rejects_token_bound_to_historical_edition(after_activation):
    old_token = token_for_edition("source-v1")
    with pytest.raises(WriterAdmissionError, match="stale_publication_edition"):
        continue_one_chapter(prepared_run(old_token, edition="target-v2"))
```

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/test_publication_edition_admission.py`

Expected: FAIL，token 尚未绑定 edition。

- [ ] **Step 3: 将 edition id/hash 纳入 Context、Admission 和出口验证**

活动 edition 来自 pointer 唯一真源；无迁移 pointer 的旧项目使用显式 `legacy-default` 兼容投影。生产入口不得接受调用方传入 edition 覆盖权威读取结果。

- [ ] **Step 4: 参数化测试 Context、Writer、Promotion、final sink 全部出口**

Run: `python -m pytest -q tests/test_publication_edition_admission.py tests/test_writer_admission.py tests/test_production_exit_manifest.py`

Expected: PASS；旧版路径在激活后全部 fail-closed。

- [ ] **Step 5: 检查本任务边界**

Run: `git diff --check -- creative_os/domains/publication_edition.py creative_os/novel_continuation_runner.py creative_os/domains/writer_admission.py creative_os/domains/chapter_production_owner_registry.py tests/assets/writer_production_exits_v1.json tests/test_publication_edition_admission.py`

Expected: exit 0；不暂存、不提交。

### Task 8: 迁移 CLI 与机械安全扫描

**Files:**
- Create: `scripts/migrate_publication_chapters.py`
- Create: `creative_os/assets/publication_migration_exits_v1.json`
- Test: `tests/test_publication_migration_cli.py`

**Interfaces:**
- Consumes: `PublicationMigrationService`。
- Produces: `inspect`, `snapshot`, `plan`, `approve-plan`, `rebuild-content`, `rebuild-authority`, `verify-batch`, `verify-all`, `activate` 子命令。

- [ ] **Step 1: 写未审批执行和一键绕过 RED 测试**

```python
def test_cli_cannot_activate_candidate_or_combine_approve_and_activate(cli):
    assert cli("activate", "--migration-id", "m1").returncode != 0
    assert "--approve-and-activate" not in cli("--help").stdout
```

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/test_publication_migration_cli.py`

Expected: FAIL。

- [ ] **Step 3: 实现显式阶段 CLI 与出口清单**

CLI 只接收 project root、migration id、batch id 和 actor/reason；审批与激活必须是不同调用。JSON 出口清单列出所有写正文、写 pointer 和切换 edition 的符号。

- [ ] **Step 4: 增加 AST 扫描，证明写入口与清单完全一致**

Run: `python -m pytest -q tests/test_publication_migration_cli.py`

Expected: PASS。

- [ ] **Step 5: 检查本任务边界**

Run: `git diff --check -- scripts/migrate_publication_chapters.py creative_os/assets/publication_migration_exits_v1.json tests/test_publication_migration_cli.py`

Expected: exit 0；不暂存、不提交。

### Task 9: 第5—10章拆分规划、轻度重写与批次权威链

**Files:**
- Create: `projects/文明升阶/.creative_os/publication_migration/plans/source_005_010.json`
- Create: `projects/文明升阶/.creative_os/publication_migration/target_editions/civilization-publication-v2/final_chapters/chapter_NNN.md`（NNN 为批准后的首批连续目标章号）
- Create: `projects/文明升阶/.creative_os/publication_migration/target_editions/civilization-publication-v2/.creative_os/`（首批逐章 contracts/reviews/quality/fulfillment/state 权威记录）
- Test: `tests/test_civilization_publication_batch_005_010.py`

**Interfaces:**
- Consumes: Tasks 1—8，旧第5—10章正文与权威记录。
- Produces: 经人工批准的首批 SplitPlan、目标正文、Manifest entries、闭环权威记录。

- [ ] **Step 1: 用 CLI 生成候选并输出逐章切点审计**

Run: `python scripts/migrate_publication_chapters.py plan --project-root projects/文明升阶 --migration-id civilization-publication-v2 --source-start 5 --source-end 10`

Expected: 只生成 candidate；原第1—32章 hash 不变。

- [ ] **Step 2: 人工审阅每个单元的冲突、选择、状态变化与钩子后批准计划**

Run: `python scripts/migrate_publication_chapters.py approve-plan --project-root projects/文明升阶 --migration-id civilization-publication-v2 --batch-id source-005-010 --actor human-owner --reason "批准第5至10章戏剧节点拆分"`

Expected: append-only decision 与 candidate hash 精确绑定。

- [ ] **Step 3: 重建正文，删除重复说明并补最少必要承接/钩子**

本批必须保持第5章从已发布第4章自然接入；不得改变父母身份、龙渊项目、短信、神经代价、联邦会议、普通人切面和全球公布的既有因果顺序。

- [ ] **Step 4: 逐章重建权威链并关闭重开 Store 验证**

Run: `python scripts/migrate_publication_chapters.py rebuild-authority --project-root projects/文明升阶 --migration-id civilization-publication-v2 --batch-id source-005-010`

Expected: 本批每章 Review issues 为空，Fulfillment fulfilled，State materialized。

- [ ] **Step 5: 运行首批 Gate**

Run: `python -m pytest -q tests/test_civilization_publication_batch_005_010.py`

Expected: PASS；第1—4章哈希不变；目标章无硬上限违规；源片段覆盖完整。

### Task 10: 第11—18章拆分规划、轻度重写与批次权威链

**Files:**
- Create: `projects/文明升阶/.creative_os/publication_migration/plans/source_011_018.json`
- Create: `projects/文明升阶/.creative_os/publication_migration/target_editions/civilization-publication-v2/final_chapters/chapter_NNN.md`（NNN 紧接 Task 9 末章）
- Create: `projects/文明升阶/.creative_os/publication_migration/target_editions/civilization-publication-v2/.creative_os/`（第二批逐章权威记录）
- Test: `tests/test_civilization_publication_batch_011_018.py`

**Interfaces:**
- Consumes: Task 9 末章 next Baseline、旧第11—18章。
- Produces: 第二批 Manifest entries 与闭环权威链。

- [ ] **Step 1: 生成并审阅本批候选计划**

Run: `python scripts/migrate_publication_chapters.py plan --project-root projects/文明升阶 --migration-id civilization-publication-v2 --source-start 11 --source-end 18`

Expected: 候选保持余波、老周泵组、双重密钥、两条路线、宇的来历、周远秘密、朋友现身和境外校验的顺序。

- [ ] **Step 2: 批准 candidate hash，不接受自动审批**

Run: `python scripts/migrate_publication_chapters.py approve-plan --project-root projects/文明升阶 --migration-id civilization-publication-v2 --batch-id source-011-018 --actor human-owner --reason "批准第11至18章戏剧节点拆分"`

Expected: PASS。

- [ ] **Step 3: 重建正文与章末钩子**

重点压缩重复解释，保留冷却泵组、七镜面段、宇的不确定自我认知、朋友投影与境外有限互信的 Canon 边界。

- [ ] **Step 4: 重建本批逐章权威链**

Run: `python scripts/migrate_publication_chapters.py rebuild-authority --project-root projects/文明升阶 --migration-id civilization-publication-v2 --batch-id source-011-018`

Expected: 全部目标章从上一章物化 Baseline 顺序构建。

- [ ] **Step 5: 运行第二批 Gate**

Run: `python -m pytest -q tests/test_civilization_publication_batch_011_018.py`

Expected: PASS；国际线不共享完整密钥，不新增组织或宇宙事实。

### Task 11: 第19—26章拆分规划、轻度重写与批次权威链

**Files:**
- Create: `projects/文明升阶/.creative_os/publication_migration/plans/source_019_026.json`
- Create: `projects/文明升阶/.creative_os/publication_migration/target_editions/civilization-publication-v2/final_chapters/chapter_NNN.md`（NNN 紧接 Task 10 末章）
- Create: `projects/文明升阶/.creative_os/publication_migration/target_editions/civilization-publication-v2/.creative_os/`（第三批逐章权威记录）
- Test: `tests/test_civilization_publication_batch_019_026.py`

**Interfaces:**
- Consumes: Task 10 末章 next Baseline、旧第19—26章。
- Produces: 第三批 Manifest entries 与闭环权威链。

- [ ] **Step 1: 生成并审阅本批候选计划**

Run: `python scripts/migrate_publication_chapters.py plan --project-root projects/文明升阶 --migration-id civilization-publication-v2 --source-start 19 --source-end 26`

Expected: 候选显式携带第19、20、22章既有连续性裁决及第24—26章配角 POV。

- [ ] **Step 2: 批准本批计划**

Run: `python scripts/migrate_publication_chapters.py approve-plan --project-root projects/文明升阶 --migration-id civilization-publication-v2 --batch-id source-019-026 --actor human-owner --reason "批准第19至26章戏剧节点拆分"`

Expected: PASS。

- [ ] **Step 3: 重建正文并锁定关键 Canon**

第19章人为袭击、RC-7为利用手段；第20章无遗产仓库；第22章倒计时七年；第23章未成功点火；第24—26章保持配角独立改变工程、社会与国际状态。

- [ ] **Step 4: 重建本批逐章权威链**

Run: `python scripts/migrate_publication_chapters.py rebuild-authority --project-root projects/文明升阶 --migration-id civilization-publication-v2 --batch-id source-019-026`

Expected: POV Planner 每章重算，不按固定比例轮换。

- [ ] **Step 5: 运行第三批 Gate**

Run: `python -m pytest -q tests/test_civilization_publication_batch_019_026.py`

Expected: PASS；关键禁入事实全部无命中。

### Task 12: 第27—32章拆分规划、轻度重写与批次权威链

**Files:**
- Create: `projects/文明升阶/.creative_os/publication_migration/plans/source_027_032.json`
- Create: `projects/文明升阶/.creative_os/publication_migration/target_editions/civilization-publication-v2/final_chapters/chapter_NNN.md`（NNN 紧接 Task 11 末章）
- Create: `projects/文明升阶/.creative_os/publication_migration/target_editions/civilization-publication-v2/.creative_os/`（第四批逐章权威记录）
- Test: `tests/test_civilization_publication_batch_027_032.py`

**Interfaces:**
- Consumes: Task 11 末章 next Baseline、旧第27—32章。
- Produces: 最后一批 Manifest entries、闭环权威链与迁移后最终 Baseline。

- [ ] **Step 1: 生成并审阅本批候选计划**

Run: `python scripts/migrate_publication_chapters.py plan --project-root projects/文明升阶 --migration-id civilization-publication-v2 --source-start 27 --source-end 32`

Expected: 原第28、29章分别建议三单元，其余按完整戏剧节点决定，不预设最终总章数。

- [ ] **Step 2: 批准本批计划**

Run: `python scripts/migrate_publication_chapters.py approve-plan --project-root projects/文明升阶 --migration-id civilization-publication-v2 --batch-id source-027-032 --actor human-owner --reason "批准第27至32章戏剧节点拆分"`

Expected: PASS。

- [ ] **Step 3: 重建正文并锁定最终 Canon 边界**

保留可信计算、共同点火、指数1.0、技术目录受控开放、光冕主观体验和无署名肯定；禁止提前完成亚光速/冬眠应用、确认外部发送者或新增下一任务坐标。

- [ ] **Step 4: 重建本批逐章权威链**

Run: `python scripts/migrate_publication_chapters.py rebuild-authority --project-root projects/文明升阶 --migration-id civilization-publication-v2 --batch-id source-027-032`

Expected: 最终章 State materialized；只产生“下一章待规划”，不存在新剧情正文。

- [ ] **Step 5: 运行第四批 Gate**

Run: `python -m pytest -q tests/test_civilization_publication_batch_027_032.py`

Expected: PASS。

### Task 13: 全书 Manifest 闭包、活动版原子切换与接续状态

**Files:**
- Modify: `projects/文明升阶/.creative_os/publication_migration/` 下最终 Manifest、checkpoint、pointer
- Modify: `projects/文明升阶/production/reports/continuation_readiness.md`
- Test: `tests/test_civilization_publication_activation.py`

**Interfaces:**
- Consumes: Tasks 9—12 全部 verified batches。
- Produces: `ACTIVATED` Manifest、唯一活动 target edition、历史 source edition、迁移后 readiness。

- [ ] **Step 1: 写全书激活前联合验证**

Run: `python scripts/migrate_publication_chapters.py verify-all --project-root projects/文明升阶 --migration-id civilization-publication-v2`

Expected: 目标章号从5连续；所有来源段落恰好消费或显式省略；第1—4章 hash 不变；所有权威链闭环。

- [ ] **Step 2: 运行激活崩溃矩阵测试**

Run: `python -m pytest -q tests/test_civilization_publication_activation.py -k "before_pointer or after_pointer or reopen or stale_token or mixed_edition"`

Expected: PASS；任何恢复只暴露一个完整 edition。

- [ ] **Step 3: 在项目权威锁内激活目标版**

Run: `python scripts/migrate_publication_chapters.py activate --project-root projects/文明升阶 --migration-id civilization-publication-v2 --actor human-owner --reason "批准发布版拆章迁移激活"`

Expected: pointer 指向 verified target edition；源版保持原文件和哈希。

- [ ] **Step 4: 关闭并重开全部 Store 后核对生产读取路径**

Run: `python -m pytest -q tests/test_civilization_publication_activation.py`

Expected: PASS；Context、Admission、Writer、Promotion 只读取新活动版。

- [ ] **Step 5: 核对 readiness**

Expected: readiness 指向迁移后最终章的下一章“待规划”；该章正文和合同不存在。

### Task 14: 最终内容、工程与安全 Gate

**Files:**
- Create: `projects/文明升阶/production/reports/publication_chapter_split_migration_audit.md`
- Modify: `docs/novel-production-roadmap.md`
- Test: `tests/test_civilization_publication_migration_final_gate.py`

**Interfaces:**
- Consumes: activated Manifest、全部新正文与权威记录。
- Produces: 最终审计报告与可机械重复的验收测试。

- [ ] **Step 1: 写最终要求映射测试**

```python
def test_publication_migration_final_gate(project_root):
    assert frozen_hashes(project_root, range(1, 5)) == manifest_frozen_hashes(project_root)
    assert all(2500 <= chapter.chinese_chars <= 5500 for chapter in active_unpublished_chapters(project_root))
    assert no_source_fragment_is_lost_or_duplicated(project_root)
    assert all_authority_chains_are_closed(project_root)
    assert not next_unwritten_chapter(project_root).exists()
```

- [ ] **Step 2: 运行最终定向 Gate**

Run: `python -m pytest -q tests/test_civilization_publication_migration_final_gate.py`

Expected: PASS。

- [ ] **Step 3: 编写审计报告**

报告必须列出旧章到新章映射、每章字数、切点理由、删改摘要、Canon 断言、POV、场景、钩子、权威 hash 和例外审批；结论区分别评价连续性、追读节奏、配角能动性和剩余风险。

- [ ] **Step 4: 运行全量工程验证**

Run: `python -m pytest -q`

Run: `python -m compileall -q creative_os scripts`

Run: `git diff --check`

Expected: 全部 exit 0；仅允许既有 skip 和行尾转换 warning。

- [ ] **Step 5: 运行安全与 Git 状态核对**

Run: `git diff --cached --name-only`

Expected: 无输出。

Run: `git log -1 --oneline`

Expected: HEAD 与迁移前一致；未提交、推送或合并。

## Final Exit Gate

只有同时满足以下条件才可宣称目标完成：

1. 第1—4章逐文件 SHA-256 与迁移前一致；
2. 旧第5—32章源版归档完整且可重读；
3. 新发布版从第5章开始连续，每章符合长度策略或具备有效例外；
4. Manifest 证明源片段无静默遗漏、无重复消费、顺序未颠倒；
5. 每章拥有独立戏剧闭包和章末钩子；
6. 重大 Canon 和原第32章结局边界保持；
7. 每章完整权威链关闭重开后仍成立；
8. 生产入口只读取新活动 edition；
9. 下一章仅为待规划，不存在正文或合同；
10. 全量测试、compileall、AST/出口扫描、whitespace 和 Git 状态检查通过；
11. 未删除旧资料，未暂存、提交、推送或合并。
