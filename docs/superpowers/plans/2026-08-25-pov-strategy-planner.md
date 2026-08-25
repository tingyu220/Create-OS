# POV Strategy Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个无事实主权、证据绑定且可失效的 POVStrategyPlanner，使系统在下一章合同形成前推荐 POV、主角是否出场、备选与风险，并在第24–26章状态下自然推荐第27章回到林子轩。

**Architecture:** 新增独立 `pov_strategy` 纯决策域：InputAssembler 从权威状态装配不可变输入，Planner 按功能适配/能动性/后果承接排序，CandidateReviewer 产生标准风险，Adapter 只把被选候选映射进现有 Narrative Director proposal。候选只保存为 runtime 审计工件，不进入 Memory、Context 或 Writer；唯一正式 POV 真值仍是获批 `ChapterContract.pov_plan`。

**Tech Stack:** Python 3.11+、标准库 `dataclasses/json/hashlib/pathlib`、现有 `JsonMemoryStore`/Narrative Director/Continuation/Runtime、pytest。

**Spec:** `docs/superpowers/specs/2026-08-25-pov-strategy-planner-design.md`

## Global Constraints

- 不使用 POV 百分比、固定轮换、章节号特判；连续次数只能触发复核，不能直接决定推荐。
- Planner 无事实主权、无合同激活权限、无 Writer 调用权限、无正文输出字段。
- 唯一正式 POV 真值是人工批准的 `NarrativeDecision.chapter_contract.pov_plan`。
- 候选必须绑定 `source_id/source_version/source_content_hash/locator/assertion` 并携带输入指纹。
- 候选不得保存为 `MemoryItem`，不得被 `MemoryRetriever`、Context 或 Writer Prompt 消费。
- 任一权威来源、策略、目标章节或章节需求变化必须使候选 stale；禁止静默回退到主角 POV。
- 每个任务按 RED→GREEN 独立全绿后才能进入下一任务；禁止引用尚未由前序任务定义的类型。
- 文件按职责拆分；新增领域文件建议不超过 300 行，接线文件只做薄适配，不扩张成第二 Director。
- 执行时不得生成小说正文或调用真实模型。
- 本计划中的提交命令仅供未来获批实施时逐任务使用；本轮不得执行提交、推送、合并或建 PR。

## File Map

| File | Responsibility |
|---|---|
| `creative_os/domains/pov_strategy_model.py` | 不可变输入、候选、证据、风险、覆盖与结果模型 |
| `creative_os/domains/pov_strategy_codec.py` | 规范化 JSON、hash、严格 codec 与篡改检测 |
| `creative_os/domains/pov_strategy_policy.py` | 项目参数、默认值、禁止比例/轮换配置校验 |
| `creative_os/domains/pov_strategy_input.py` | 从正式章节、活动合同、Profile、状态快照装配输入 |
| `creative_os/domains/pov_strategy_planner.py` | 无 IO 的资格过滤、排序、推荐与节奏展望 |
| `creative_os/domains/pov_strategy_review.py` | 六类 POV 风险及证据充分性检查 |
| `creative_os/domains/pov_strategy_adapter.py` | 候选到 `PointOfViewPlan` 骨架/Director 输入的薄适配 |
| `creative_os/domains/pov_strategy_selection.py` | 人工采纳推荐、备选或覆盖的审计与 stale 校验 |
| `creative_os/runtime/pov_strategy_store.py` | runtime 审计工件追加、读取、过期；绝不进入 Memory |
| `creative_os/domains/pov_strategy_recompute.py` | 成稿物化后失效旧候选并为下一章重算 |
| `creative_os/pov_strategy_shadow.py` | 只读影子模式入口与报告 |
| `creative_os/pov_strategy_admission.py` | 生产候选门禁与 Writer Admission 前置检查 |
| `scripts/inspect_pov_strategy.py` | 影子模式 CLI，不生成合同/正文 |
| `tests/fixtures/pov_strategy/` | 第24–26章验收夹具与境外事故反例 |

---

### Task 1: 领域模型与严格 Codec

**Files:**
- Create: `creative_os/domains/pov_strategy_model.py`
- Create: `creative_os/domains/pov_strategy_codec.py`
- Test: `tests/test_pov_strategy_model.py`
- Test: `tests/test_pov_strategy_codec.py`

**Interfaces:**
- Consumes: 仅标准库；不依赖任何后续任务。
- Produces: `EvidenceRef`、`StateRef`、`ConsequenceRef`、`MainlineCapability`、`RecentPOVEntry`、`CharacterPressure`、`StorylineState`、`ChapterNeeds`、`POVStrategyInput`、`SupportingAgencyBoundary`、`MainlineChangeProposal`、`POVOption`、`RhythmOutlook`、`POVRisk`、`POVStrategyCandidateSet`、`HumanPOVOverride`、`POVSelectionRecord`、`POVStrategyAuditRecord`；`encode_candidate_set(value: POVStrategyCandidateSet) -> str`、`decode_candidate_set(content: str) -> POVStrategyCandidateSet`、`fingerprint_input(value: POVStrategyInput) -> str`。

- [ ] **Step 1: 写模型与 codec 的失败测试**

```python
def test_candidate_model_has_no_prose_or_contract_activation_fields():
    fields = {field.name for field in dataclasses.fields(POVStrategyCandidateSet)}
    assert "draft" not in fields
    assert "body" not in fields
    assert "memory_status" not in fields

def test_candidate_codec_rejects_modified_input_fingerprint():
    encoded = encode_candidate_set(candidate_set())
    payload = json.loads(encoded)
    payload["input_fingerprint"] = "0" * 64
    with pytest.raises(POVStrategyCodecError, match="fingerprint"):
        decode_candidate_set(json.dumps(payload, ensure_ascii=False))
```

- [ ] **Step 2: 验证 RED**

Run: `python -m pytest -q tests/test_pov_strategy_model.py tests/test_pov_strategy_codec.py`

Expected: collection FAIL，提示 `creative_os.domains.pov_strategy_model` 不存在。

- [ ] **Step 3: 实现最小不可变模型与规范化 codec**

```python
@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source_id: str
    source_version: str
    source_content_hash: str
    locator: str
    assertion: str

@dataclass(frozen=True, slots=True)
class POVStrategyInput:
    project_id: str
    target_chapter: int
    assembled_at: str
    policy_version: str
    recent_pov_history: tuple[RecentPOVEntry, ...]
    protagonist_load: ProtagonistLoad
    character_pressures: tuple[CharacterPressure, ...]
    arc_state: ArcState
    storyline_states: tuple[StorylineState, ...]
    unclaimed_consequences: tuple[ConsequenceRef, ...]
    chapter_needs: ChapterNeeds
    evidence: tuple[EvidenceRef, ...]
    baseline_fingerprint: str = ""

def fingerprint_input(value: POVStrategyInput) -> str:
    payload = dataclass_to_primitive(replace(value, baseline_fingerprint=""))
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
```

所有 `validate()` 明确检查正整数章节、64位十六进制 hash、非空 stable ID、唯一候选 ID、`horizon_chapters in {3,4}`，以及输出不含正文/审批状态字段。Codec 使用 `schema_version=1`，拒绝未知字段、缺字段、枚举外值和内容 hash 篡改。

- [ ] **Step 4: 验证 GREEN 与既有合同模型回归**

Run: `python -m pytest -q tests/test_pov_strategy_model.py tests/test_pov_strategy_codec.py tests/test_narrative_decision.py`

Expected: PASS；既有 `PointOfViewPlan` 序列化测试保持通过。

- [ ] **Step 5: 建议提交（未来实施时执行）**

```powershell
git add creative_os/domains/pov_strategy_model.py creative_os/domains/pov_strategy_codec.py tests/test_pov_strategy_model.py tests/test_pov_strategy_codec.py
git commit -m "新增POV策略领域模型与严格编解码"
```

---

### Task 2: 项目级 Policy 与非法比例/轮换阻断

**Files:**
- Create: `creative_os/domains/pov_strategy_policy.py`
- Test: `tests/test_pov_strategy_policy.py`

**Interfaces:**
- Consumes: Task 1 的模型枚举和 `POVStrategyValidationError`。
- Produces: `POVStrategyPolicy(version, history_window, cold_start_minimum, absence_review_after, monopoly_review_after, blocking_risks, protagonist_id, eligible_pov_ids)`；`load_pov_strategy_policy(project_root: Path) -> POVStrategyPolicy`。

- [ ] **Step 1: 写 Policy RED 测试**

```python
@pytest.mark.parametrize("illegal", [
    {"protagonist_ratio": 0.7},
    {"pov_rotation": ["lin-zixuan", "lin-zhenghong"]},
    {"history_window": 11},
])
def test_policy_rejects_ratio_rotation_and_invalid_window(tmp_path, illegal):
    write_policy(tmp_path, illegal)
    with pytest.raises(POVStrategyPolicyError):
        load_pov_strategy_policy(tmp_path)
```

- [ ] **Step 2: 验证 RED**

Run: `python -m pytest -q tests/test_pov_strategy_policy.py`

Expected: FAIL，提示 loader 未定义。

- [ ] **Step 3: 实现严格白名单参数**

```python
ALLOWED_KEYS = {
    "version", "history_window", "cold_start_minimum", "absence_review_after",
    "monopoly_review_after", "blocking_risks", "protagonist_id", "eligible_pov_ids",
}

def load_pov_strategy_policy(project_root: Path) -> POVStrategyPolicy:
    payload = read_optional_json(project_root / ".creative_os" / "pov_strategy_policy.json")
    unknown = set(payload) - ALLOWED_KEYS
    if unknown:
        raise POVStrategyPolicyError(f"unsupported policy keys: {sorted(unknown)}")
    return POVStrategyPolicy.from_mapping(payload).validated()
```

默认窗口为8且只允许6–10；absence/monopoly 是“开始复核”阈值，Policy API 不暴露评分权重或推荐比例。

- [ ] **Step 4: GREEN 与反机械轮换回归**

Run: `python -m pytest -q tests/test_pov_strategy_policy.py tests/test_pov_strategy_model.py`

Expected: PASS。

- [ ] **Step 5: 建议提交**

```powershell
git add creative_os/domains/pov_strategy_policy.py tests/test_pov_strategy_policy.py
git commit -m "增加POV项目策略与机械轮换阻断"
```

---

### Task 3: InputAssembler 权威状态装配

**Files:**
- Create: `creative_os/domains/pov_strategy_input.py`
- Test: `tests/test_pov_strategy_input.py`

**Interfaces:**
- Consumes: `POVStrategyPolicy`、Task 1 全部输入模型；现有 `load_active_narrative_decision(project_root, chapter_number)`、`load_active_narrative_profile(project_root)`、`compact_active_snapshots(project_root, max_chars=6000)`、正式章节目录。
- Produces: `assemble_pov_strategy_input(project_root: str | Path, target_chapter: int, chapter_needs: ChapterNeeds, policy: POVStrategyPolicy) -> POVStrategyInput`；错误 `POVStrategyInputError(code, missing_fields)`。

- [ ] **Step 1: 写权威来源、冷启动和指纹 RED 测试**

```python
def test_assembler_uses_only_final_chapters_active_contracts_and_active_snapshots(project):
    write_rejected_contract(project, chapter=9, pov="intruder")
    value = assemble_pov_strategy_input(project, 10, needs(), policy())
    assert all(item.primary_owner != "intruder" for item in value.recent_pov_history)

def test_assembler_marks_cold_start_without_fabricating_six_chapters(project_with_three_chapters):
    value = assemble_pov_strategy_input(project_with_three_chapters, 4, needs(), policy())
    assert len(value.recent_pov_history) == 3
    assert value.protagonist_load.cold_start is True
```

- [ ] **Step 2: 验证 RED**

Run: `python -m pytest -q tests/test_pov_strategy_input.py`

Expected: FAIL，InputAssembler 不存在。

- [ ] **Step 3: 实现来源适配器和后果承接判定**

```python
def assemble_pov_strategy_input(project_root, target_chapter, chapter_needs, policy):
    root = Path(project_root)
    history = _recent_formal_pov_history(root, target_chapter, policy.history_window)
    snapshots = _active_story_snapshots(root)
    consequences = _unclaimed_consequences(history, snapshots)
    value = POVStrategyInput(
        project_id=root.name,
        target_chapter=target_chapter,
        policy_version=policy.version,
        recent_pov_history=history,
        protagonist_load=_protagonist_load(history, consequences, policy.protagonist_id),
        character_pressures=_character_pressures(snapshots),
        arc_state=_active_arc(root),
        storyline_states=_storyline_states(snapshots),
        unclaimed_consequences=consequences,
        chapter_needs=chapter_needs,
        evidence=_dedupe_evidence((*_evidence_from_history(history), *_evidence_from_snapshots(snapshots), *_evidence_from_needs(chapter_needs))),
    )
    return replace(value, baseline_fingerprint=fingerprint_input(value)).validated()
```

草稿、candidate/rejected Memory、旧 Planner 工件不得进入输入；缺 Arc 核心问题或章节功能返回 `missing_pov_strategy_input`，不猜默认值。

- [ ] **Step 4: GREEN、重启确定性和篡改负测**

Run: `python -m pytest -q tests/test_pov_strategy_input.py tests/test_novel_state_store.py tests/test_narrative_memory.py`

Expected: PASS；同一磁盘状态重建输入指纹相同，修改来源内容但不更新 hash 时抛 `unverifiable_pov_evidence`。

- [ ] **Step 5: 建议提交**

```powershell
git add creative_os/domains/pov_strategy_input.py tests/test_pov_strategy_input.py
git commit -m "实现POV策略权威输入装配"
```

---

### Task 4: Planner 纯决策、资格过滤与非冻结节奏

**Files:**
- Create: `creative_os/domains/pov_strategy_planner.py`
- Test: `tests/test_pov_strategy_planner.py`

**Interfaces:**
- Consumes: `POVStrategyInput`、`POVStrategyPolicy`。
- Produces: `POVStrategyPlanner.plan(input: POVStrategyInput, policy: POVStrategyPolicy) -> POVStrategyCandidateSet`；内部纯函数 `eligible_options(input) -> tuple[POVOption, ...]`、`rank_options(options, input) -> tuple[POVOption, ...]`。

- [ ] **Step 1: 写功能适配优先与非比例 RED 测试**

```python
def test_planner_prefers_character_who_can_change_required_state_not_rotation_order():
    value = input_with(history=("a", "b", "a"), function="阻断现场事故")
    result = POVStrategyPlanner().plan(value, policy())
    assert result.recommended.primary_owner == "engineer"

def test_planner_outlook_does_not_freeze_future_character_or_chapter():
    result = POVStrategyPlanner().plan(input_value(), policy())
    assert result.rhythm_outlook.horizon_chapters in {3, 4}
    assert not hasattr(result.rhythm_outlook, "chapter_assignments")
```

- [ ] **Step 2: 验证 RED**

Run: `python -m pytest -q tests/test_pov_strategy_planner.py`

Expected: FAIL，Planner 未定义。

- [ ] **Step 3: 实现离散排序与无候选阻断**

```python
DIMENSIONS = (
    "chapter_function_fit", "mainline_agency", "consequence_ownership",
    "arc_relevance", "information_legitimacy", "continuity_pressure",
    "scene_technology_fit",
)

class POVStrategyPlanner:
    def plan(self, input, policy):
        input.validate_fingerprint()
        options = tuple(option for option in _build_options(input) if _is_eligible(option))
        if not options:
            raise POVStrategyPlanningError("no_viable_pov_candidate")
        ranked = tuple(sorted(options, key=_explainable_rank_key, reverse=True))
        return _candidate_set(input, ranked[0], ranked[1:3], _rhythm_outlook(input)).validated()
```

`_is_eligible` 同时要求功能、独立目标、阻力、选择边界、代价来源、直接状态改变、信息权限和转换理由；不使用浮点概率、百分比或章节号。

- [ ] **Step 4: GREEN 与确定性回归**

Run: `python -m pytest -q tests/test_pov_strategy_planner.py tests/test_pov_strategy_policy.py tests/test_pov_strategy_model.py`

Expected: PASS；相同输入重复100次输出 JSON 完全相同（除由调用者注入的 `generated_at`）。

- [ ] **Step 5: 建议提交**

```powershell
git add creative_os/domains/pov_strategy_planner.py tests/test_pov_strategy_planner.py
git commit -m "实现POV策略纯决策与资格排序"
```

---

### Task 5: CandidateReviewer 六类风险

**Files:**
- Create: `creative_os/domains/pov_strategy_review.py`
- Test: `tests/test_pov_strategy_review.py`

**Interfaces:**
- Consumes: `POVStrategyInput`、`POVStrategyCandidateSet`、`POVStrategyPolicy`。
- Produces: `review_pov_strategy(input: POVStrategyInput, candidates: POVStrategyCandidateSet, policy: POVStrategyPolicy) -> tuple[POVRisk, ...]`、`assert_pov_strategy_admissible(input: POVStrategyInput, candidates: POVStrategyCandidateSet, policy: POVStrategyPolicy) -> None`；阻断错误 `POVStrategyReviewBlockedError`。

- [ ] **Step 1: 为六个风险逐一写 RED 参数测试**

```python
@pytest.mark.parametrize("fixture_name,expected", [
    ("absence_unresolved", "protagonist_absence_unresolved"),
    ("monopoly", "protagonist_pov_monopoly"),
    ("supporting_no_agency", "supporting_pov_without_agency"),
    ("cannot_serve", "pov_cannot_serve_chapter_function"),
    ("report_only", "supporting_outcome_only_reported_to_protagonist"),
    ("transition_no_reason", "pov_transition_without_arc_reason"),
])
def test_reviewer_emits_required_risk(fixture_name, expected):
    input, candidates = review_fixture(fixture_name)
    assert expected in {risk.code for risk in review_pov_strategy(input, candidates, policy())}
```

- [ ] **Step 2: 验证 RED**

Run: `python -m pytest -q tests/test_pov_strategy_review.py`

Expected: FAIL，Reviewer 未定义。

- [ ] **Step 3: 实现确定性风险与证据要求**

每个风险构造器必须返回非空 `evidence_refs` 和具体 explanation；`supporting_outcome_only_reported_to_protagonist` 只在主线变化类型为空/`report` 时触发，不能因正文未生成而误判。Policy 的 `blocking_risks` 只决定是否阻断，不改变风险是否存在。

- [ ] **Step 4: GREEN 与合理例外测试**

Run: `python -m pytest -q tests/test_pov_strategy_review.py tests/test_pov_strategy_planner.py`

Expected: PASS；连续主角 POV 有明确 Arc 必要选择时不报 monopoly；连续配角 POV 面临境外即时事故时不因次数本身报 absence blocking。

- [ ] **Step 5: 建议提交**

```powershell
git add creative_os/domains/pov_strategy_review.py tests/test_pov_strategy_review.py
git commit -m "增加POV候选六类风险审查"
```

---

### Task 6: Director 薄适配与 v2 合同一致性

**Files:**
- Create: `creative_os/domains/pov_strategy_adapter.py`
- Modify: `creative_os/domains/narrative_director.py`
- Test: `tests/test_pov_strategy_adapter.py`
- Modify: `tests/test_narrative_director.py`

**Interfaces:**
- Consumes: `POVOption`、现有 `PointOfViewPlan`/`SupportingAgencyContract`/`NarrativeDecision`/`DirectorInput`。
- Produces: `pov_plan_from_option(option: POVOption, agencies: tuple[SupportingAgencyContract, ...]) -> PointOfViewPlan`；`NarrativeDirector.propose(input: DirectorInput, proposal: NarrativeDecision, pov_candidate: POVOption | None = None) -> NarrativeDecision` 保持默认参数兼容。

- [ ] **Step 1: 写适配与不一致 RED 测试**

```python
def test_director_rejects_candidate_owner_missing_from_scene_viewpoints():
    proposal = proposal_with_pov("engineer", scene_viewpoint="protagonist")
    with pytest.raises(NarrativeDirectorBlockedError, match="POV candidate"):
        director.propose(input, proposal, pov_candidate=engineer_option())

def test_adapter_requires_complete_agency_contract():
    with pytest.raises(NarrativeValidationError):
        pov_plan_from_option(engineer_option(), agencies=())
```

- [ ] **Step 2: 验证 RED**

Run: `python -m pytest -q tests/test_pov_strategy_adapter.py tests/test_narrative_director.py`

Expected: FAIL，adapter/参数未定义。

- [ ] **Step 3: 实现薄接线**

Director 只校验：candidate owner/presence 与 `PointOfViewPlan` 相同；owner 是至少一个 Scene viewpoint；SupportingAgency actor 和 mainline change 完整；TechnologyPlan 有现场行动时 owner 具备对应 capability。不得在 Director 内重新排序候选或读取状态。

- [ ] **Step 4: GREEN 与 v1/v2 兼容回归**

Run: `python -m pytest -q tests/test_pov_strategy_adapter.py tests/test_narrative_director.py tests/test_narrative_decision.py`

Expected: PASS；不传 `pov_candidate` 的既有调用保持行为不变。

- [ ] **Step 5: 建议提交**

```powershell
git add creative_os/domains/pov_strategy_adapter.py creative_os/domains/narrative_director.py tests/test_pov_strategy_adapter.py tests/test_narrative_director.py
git commit -m "接入POV候选与叙事导演一致性校验"
```

---

### Task 7: 合同选择审计、stale 与人工覆盖

**Files:**
- Create: `creative_os/domains/pov_strategy_selection.py`
- Create: `creative_os/runtime/pov_strategy_store.py`
- Test: `tests/test_pov_strategy_selection.py`
- Test: `tests/test_pov_strategy_store.py`

**Interfaces:**
- Consumes: Task 1 的 `POVStrategyCandidateSet/HumanPOVOverride/POVSelectionRecord`、`POVStrategyInput`、现有合同审批 actor 语义。
- Produces: `select_recommendation(candidates: POVStrategyCandidateSet, current_input: POVStrategyInput, *, actor: str) -> POVSelectionRecord`、`select_alternative(candidate_id: str, candidates: POVStrategyCandidateSet, current_input: POVStrategyInput, *, actor: str) -> POVSelectionRecord`、`select_override(override: HumanPOVOverride, candidates: POVStrategyCandidateSet, current_input: POVStrategyInput, *, actor: str) -> POVSelectionRecord`、`validate_selection_fresh(selection: POVSelectionRecord, current_input: POVStrategyInput) -> None`；`POVStrategyAuditStore.append_candidate(value: POVStrategyCandidateSet) -> POVStrategyAuditRecord`、`set_status(candidate_id: str, status: str, *, actor: str) -> POVStrategyAuditRecord`、`read(candidate_id: str) -> POVStrategyAuditRecord`。

- [ ] **Step 1: 写 stale、重启、篡改、覆盖 RED 测试**

```python
def test_selection_becomes_stale_when_source_changes():
    selection = select_recommendation(candidates, input, actor="tingyu")
    changed = replace(input, target_chapter=input.target_chapter + 1)
    with pytest.raises(POVSelectionError, match="stale_pov_strategy_candidate"):
        validate_selection_fresh(selection, changed)

def test_human_override_requires_mainline_change_transition_reason_and_evidence():
    with pytest.raises(POVSelectionError, match="pov_override_insufficient_evidence"):
        select_override(empty_override(), input, actor="tingyu")
```

- [ ] **Step 2: 验证 RED**

Run: `python -m pytest -q tests/test_pov_strategy_selection.py tests/test_pov_strategy_store.py`

Expected: FAIL，selection/store 未定义。

- [ ] **Step 3: 实现追加式审计而非 Memory**

审计目录固定 `.creative_os/runtime/pov_strategy/`；每个 JSON 包含 candidate content hash、input fingerprint、`proposed/selected/expired/superseded`、human actor 和时间。Store 构造函数只接受 filesystem root，不接受 `JsonMemoryStore`，模块不得 import `creative_os.memory.store`。

- [ ] **Step 4: GREEN 与进程重启测试**

Run: `python -m pytest -q tests/test_pov_strategy_selection.py tests/test_pov_strategy_store.py tests/test_memory_retriever.py`

Expected: PASS；重建 Store 后选中记录一致；手工修改 JSON/hash 必须抛篡改错误；MemoryRetriever 看不到工件。

- [ ] **Step 5: 建议提交**

```powershell
git add creative_os/domains/pov_strategy_selection.py creative_os/runtime/pov_strategy_store.py tests/test_pov_strategy_selection.py tests/test_pov_strategy_store.py
git commit -m "增加POV选择审计与人工覆盖校验"
```

---

### Task 8: 状态物化后失效与下一章重算

**Files:**
- Create: `creative_os/domains/pov_strategy_recompute.py`
- Modify: `creative_os/novel_continuation_runner.py`
- Test: `tests/test_pov_strategy_recompute.py`
- Modify: `tests/test_narrative_continuation.py`

**Interfaces:**
- Consumes: `POVStrategyAuditStore`、`assemble_pov_strategy_input`、`POVStrategyPlanner.plan`、现有 `save_chapter_candidates(project_root, chapter_number)`。
- Produces: `on_chapter_materialized(project_root: Path, chapter_number: int, next_needs: ChapterNeeds | None = None) -> RecomputeResult(expired_ids, next_candidate_id | None)`。

- [ ] **Step 1: 写物化顺序 RED 测试**

```python
def test_materialization_expires_old_candidate_before_next_recompute(project):
    result = on_chapter_materialized(project, 26, next_needs=needs_for_27())
    assert result.expired_ids == ("pov-strategy-026",)
    assert audit_store(project).read("pov-strategy-026").status == "expired"
    assert result.next_candidate_id is not None
```

- [ ] **Step 2: 验证 RED**

Run: `python -m pytest -q tests/test_pov_strategy_recompute.py tests/test_narrative_continuation.py`

Expected: FAIL，hook 未定义。

- [ ] **Step 3: 实现幂等 hook**

Runner 在正式章节写入且 `save_chapter_candidates` 成功之后调用 hook。`next_needs is None` 时只过期、不猜章节功能、不生成候选；重复调用不重复追加。重算失败不得回滚已正式物化章节，只记录 `recompute_failed` 并阻止下一章 Director 使用旧候选。

- [ ] **Step 4: GREEN 与崩溃重启回归**

Run: `python -m pytest -q tests/test_pov_strategy_recompute.py tests/test_narrative_continuation.py tests/test_novel_state_store.py`

Expected: PASS；模拟过期成功/重算前崩溃，重启后保持旧候选 expired 并可安全重算。

- [ ] **Step 5: 建议提交**

```powershell
git add creative_os/domains/pov_strategy_recompute.py creative_os/novel_continuation_runner.py tests/test_pov_strategy_recompute.py tests/test_narrative_continuation.py
git commit -m "接入章节物化后的POV策略重算"
```

---

### Task 9: Context 与 Writer 强隔离

**Files:**
- Modify: `creative_os/domains/novel_continuation.py`
- Modify: `creative_os/novel_continuation_runner.py`
- Test: `tests/test_pov_strategy_writer_isolation.py`

**Interfaces:**
- Consumes: 现有 `ContinuationTask.narrative_contract` 和获批 `PointOfViewPlan`；不得消费 Planner 类型。
- Produces: 无新领域接口；加入 `is_pov_strategy_artifact(item_or_knowledge) -> bool` 的局部过滤辅助函数。

- [ ] **Step 1: 写候选泄漏 RED 测试**

```python
def test_context_and_writer_prompt_exclude_planner_alternatives_and_outlook(project):
    write_runtime_candidate(project, alternative="foreign-engineer", outlook="chapter-28")
    task, context = build_next_chapter(project, require_narrative_contract=True)
    prompt = capture_writer_prompt(project)
    assert "foreign-engineer" not in prompt
    assert "chapter-28" not in prompt
    assert task.narrative_contract.chapter_contract.pov_plan.primary_owner in prompt
```

- [ ] **Step 2: 验证 RED**

Run: `python -m pytest -q tests/test_pov_strategy_writer_isolation.py`

Expected: FAIL，若 runtime 工件被测试检索器注入则出现泄漏断言。

- [ ] **Step 3: 实现双层隔离**

MemoryRetriever 本就不扫描 runtime；Context 额外拒绝 kind/tag/id 为 `pov_strategy_candidate` 的输入；Writer Prompt 只从 `narrative_contract.chapter_contract.pov_plan` 构建，不导入 Planner 模块。加入 import 依赖断言，防止未来反向耦合。

- [ ] **Step 4: GREEN 与 Writer 回归**

Run: `python -m pytest -q tests/test_pov_strategy_writer_isolation.py tests/test_narrative_continuation.py tests/test_novel_continuation.py`

Expected: PASS；Writer 仍收到获批 POV/Agency/Scene/Technology 合同。

- [ ] **Step 5: 建议提交**

```powershell
git add creative_os/domains/novel_continuation.py creative_os/novel_continuation_runner.py tests/test_pov_strategy_writer_isolation.py
git commit -m "隔离POV候选与写作上下文"
```

---

### Task 10: 迁移兼容与只读影子模式

**Files:**
- Create: `creative_os/pov_strategy_shadow.py`
- Create: `scripts/inspect_pov_strategy.py`
- Test: `tests/test_pov_strategy_shadow.py`
- Test: `tests/test_inspect_pov_strategy_script.py`

**Interfaces:**
- Consumes: InputAssembler、Policy、Planner、CandidateReviewer、AuditStore。
- Produces: `run_pov_strategy_shadow(project_root, target_chapter, chapter_needs) -> ShadowRunResult`；CLI `python scripts/inspect_pov_strategy.py --project-root PATH --chapter-needs FILE --no-write`。

- [ ] **Step 1: 写无副作用和 v1 兼容 RED 测试**

```python
def test_shadow_mode_does_not_create_contract_memory_or_final_chapter(v1_project):
    before = snapshot_tree(v1_project)
    result = run_pov_strategy_shadow(v1_project, 7, needs())
    assert result.status in {"candidate", "blocked"}
    assert no_new_contract_or_final_chapter(before, snapshot_tree(v1_project))
```

- [ ] **Step 2: 验证 RED**

Run: `python -m pytest -q tests/test_pov_strategy_shadow.py tests/test_inspect_pov_strategy_script.py`

Expected: FAIL，shadow/CLI 不存在。

- [ ] **Step 3: 实现影子入口**

`--no-write` 只输出 JSON 到 stdout；默认影子模式只写 runtime 审计工件。遇到 v1 合同时从正式章节实际出场和可用合同字段读取历史，不修改 v1 文件；输入不足返回结构化 blocked，不生成默认推荐。

- [ ] **Step 4: GREEN 与生产目录不变测试**

Run: `python -m pytest -q tests/test_pov_strategy_shadow.py tests/test_inspect_pov_strategy_script.py tests/test_narrative_memory.py`

Expected: PASS；`production/contracts`、`production/final_chapters`、`.creative_os/memory` 内容 hash 全部不变。

- [ ] **Step 5: 建议提交**

```powershell
git add creative_os/pov_strategy_shadow.py scripts/inspect_pov_strategy.py tests/test_pov_strategy_shadow.py tests/test_inspect_pov_strategy_script.py
git commit -m "增加POV策略只读影子模式"
```

---

### Task 11: 生产门禁、合同审批引用与 stale Admission

**Files:**
- Create: `creative_os/pov_strategy_admission.py`
- Modify: `creative_os/production_validation.py`
- Test: `tests/test_pov_strategy_admission.py`
- Modify: `tests/test_production_validation.py`

**Interfaces:**
- Consumes: `POVSelectionRecord`、当前 `POVStrategyInput`、活动 `NarrativeDecision`、现有 Memory 审批状态和 CandidateReviewer 结果。
- Produces: `admit_pov_strategy(selection, current_input, contract, *, approved_by: str) -> POVStrategyAdmissionResult(admitted, candidate_id, input_fingerprint, contract_hash, risks)`；错误 `POVStrategyAdmissionBlockedError(code)`。

- [ ] **Step 1: 写审批/stale/覆盖负测**

```python
@pytest.mark.parametrize("case,code", [
    ("unapproved_contract", "missing_approved_narrative_decision"),
    ("stale_selection", "stale_pov_strategy_candidate"),
    ("tampered_artifact", "unverifiable_pov_evidence"),
    ("override_without_evidence", "pov_override_insufficient_evidence"),
    ("blocking_review_risk", "pov_strategy_review_blocked"),
])
def test_admission_blocks_invalid_state(case, code):
    with pytest.raises(POVStrategyAdmissionBlockedError, match=code):
        admit_case(case)
```

- [ ] **Step 2: 验证 RED**

Run: `python -m pytest -q tests/test_pov_strategy_admission.py tests/test_production_validation.py`

Expected: FAIL，Admission 未定义。

- [ ] **Step 3: 实现生产前门禁**

顺序固定：验证工件 hash → 重装当前输入/比较 fingerprint → 验证 selection actor/覆盖证据 → 验证活动合同已人工批准 → 比较合同 `PointOfViewPlan` 与 selection → 重跑 CandidateReviewer → 返回只含审计标识的 AdmissionResult。不得把候选内容传给 Writer；现有 Writer Admission 继续只消费合同。

- [ ] **Step 4: GREEN 与旧项目渐进启用**

Run: `python -m pytest -q tests/test_pov_strategy_admission.py tests/test_production_validation.py tests/test_narrative_continuation.py`

Expected: PASS；未启用 Planner 的旧项目保持原门禁；启用项目缺 selection 时阻断，不回退默认 POV。

- [ ] **Step 5: 建议提交**

```powershell
git add creative_os/pov_strategy_admission.py creative_os/production_validation.py tests/test_pov_strategy_admission.py tests/test_production_validation.py
git commit -m "增加POV策略生产准入门禁"
```

---

### Task 12: 第24–26章→第27章验收夹具与境外事故反例

**Files:**
- Create: `tests/fixtures/pov_strategy/chapter_024_026_state.json`
- Create: `tests/fixtures/pov_strategy/overseas_incident_state.json`
- Create: `tests/test_pov_strategy_acceptance.py`

**Interfaces:**
- Consumes: Task 1–5 的公开接口；夹具只使用 stable IDs 和证据引用，不读取真实生产目录，保证测试可重复。
- Produces: 可复用验收 helper `load_pov_acceptance_fixture(name: str) -> tuple[POVStrategyInput, POVStrategyPolicy]`（定义在测试模块）。

- [ ] **Step 1: 写两个验收 RED 测试**

```python
def test_24_26_consequences_recommend_protagonist_for_27_without_chapter_special_case():
    input, policy = load_pov_acceptance_fixture("chapter_024_026_state")
    result = POVStrategyPlanner().plan(input, policy)
    assert input.target_chapter == 27
    assert result.recommended.primary_owner == "lin-zixuan"
    assert result.recommended.protagonist_present is True
    assert {ref.source_id for ref in result.recommended.evidence_refs} >= {
        "chapter-024", "chapter-025", "chapter-026"
    }

def test_immediate_overseas_incident_can_keep_supporting_pov_with_arc_reason():
    input, policy = load_pov_acceptance_fixture("overseas_incident_state")
    result = POVStrategyPlanner().plan(input, policy)
    assert result.recommended.primary_owner == "overseas-engineer"
    assert "pov_transition_without_arc_reason" not in {
        risk.code for risk in review_pov_strategy(input, result, policy)
    }
```

- [ ] **Step 2: 验证 RED 的正确原因**

Run: `python -m pytest -q tests/test_pov_strategy_acceptance.py`

Expected: 第一个测试在缺少可解析夹具时 FAIL；不得通过添加 `if target_chapter == 27` 修复。

- [ ] **Step 3: 写完整夹具并仅调整通用规则所需证据**

24–26夹具明确三项未承接状态：工程冻结、普通家庭复工规则、七地校验结果均改变林子轩知识/选择条件；第27章功能为“整合三线后果并作出方向选择”。境外事故夹具只改变章节功能为“现场立即阻断不可逆事故”和 capability owner，保留相同三章历史，证明结果不是连续次数硬编码。

- [ ] **Step 4: GREEN、无特判源码扫描**

Run: `python -m pytest -q tests/test_pov_strategy_acceptance.py tests/test_pov_strategy_planner.py tests/test_pov_strategy_review.py`

Run: `rg -n "chapter\s*==\s*27|target_chapter\s*==\s*27|0\.6|0\.7|60%|70%|pov_rotation" creative_os/domains/pov_strategy_*.py creative_os/pov_strategy_*.py`

Expected: pytest PASS；源码扫描无输出。

- [ ] **Step 5: 建议提交**

```powershell
git add tests/fixtures/pov_strategy tests/test_pov_strategy_acceptance.py
git commit -m "增加第27章POV策略验收与事故反例"
```

---

### Task 13: 最终 Gate、AST 依赖扫描与设计映射

**Files:**
- Create: `tests/test_pov_strategy_architecture.py`
- Modify: `docs/superpowers/specs/2026-08-25-pov-strategy-planner-design.md` only if implementation reveals a verified interface correction; otherwise do not edit.

**Interfaces:**
- Consumes: 全部已实现公开接口。
- Produces: 无生产接口；只增加架构不变量与最终验收。

- [ ] **Step 1: 写 AST/依赖不变量 RED 测试**

```python
def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result

def planner_domain_files() -> list[Path]:
    return sorted(Path("creative_os/domains").glob("pov_strategy_*.py"))

def test_planner_domain_does_not_import_writer_memory_store_or_network():
    forbidden = {"creative_os.llm_writer", "creative_os.memory.store", "urllib", "requests"}
    imports = imported_modules(Path("creative_os/domains/pov_strategy_planner.py"))
    assert imports.isdisjoint(forbidden)

def test_writer_modules_do_not_import_planner_candidate_types():
    for path in [Path("creative_os/novel_continuation_runner.py"), Path("creative_os/llm_writer.py")]:
        assert "pov_strategy" not in imported_modules(path)

def test_no_pov_strategy_memory_items_can_be_created():
    assert not any("MemoryItem" in path.read_text("utf-8") for path in planner_domain_files())
```

- [ ] **Step 2: 运行架构 RED/GREEN 边界测试**

Run: `python -m pytest -q tests/test_pov_strategy_architecture.py`

Expected: 首次运行若发现反向依赖则 FAIL；只修依赖边界，不放宽断言。

- [ ] **Step 3: 运行完整负测矩阵**

Run: `python -m pytest -q tests/test_pov_strategy_selection.py tests/test_pov_strategy_store.py tests/test_pov_strategy_admission.py tests/test_pov_strategy_recompute.py -k "stale or restart or tamper or override or crash"`

Expected: PASS，覆盖 stale、重启、篡改、人工覆盖证据不足和物化后崩溃恢复。

- [ ] **Step 4: 运行全量测试和静态扫描**

Run: `python -m pytest -q`

Run: `python -m compileall -q creative_os scripts tests`

Run: `rg -n "chapter\s*==\s*27|target_chapter\s*==\s*27|protagonist_ratio|pov_rotation|60%|70%" creative_os`

Run: `git diff --check`

Expected: pytest 全绿；compileall exit 0；禁止模式扫描无输出；diff check exit 0。

- [ ] **Step 5: 核对设计映射与文件规模**

Run: `python -c "from pathlib import Path; files=list(Path('creative_os').rglob('pov_strategy*.py')); oversized=[(str(p), len(p.read_text(encoding='utf-8').splitlines())) for p in files if len(p.read_text(encoding='utf-8').splitlines()) > 300]; assert not oversized, oversized; print('pov_strategy_files', len(files))"`

人工逐项确认：输入、输出、六风险、数据流、无事实主权、stale、人工覆盖、Writer隔离、迁移、影子模式、生产门禁、27章样例和事故反例均有对应测试任务。

- [ ] **Step 6: 建议最终提交（未来获批实施时执行）**

```powershell
git add creative_os scripts tests docs/superpowers/specs/2026-08-25-pov-strategy-planner-design.md
git commit -m "完成POV策略规划器与生产门禁"
```

注意：执行者在提交前必须先向用户确认，因为项目规则要求远程仓库操作前确认；不得自动推送。

## Final Execution Gate

- 所有 Task 必须按序执行，每个 Task 的目标测试独立全绿后才允许进入下一项。
- Task 1 是唯一基础类型定义任务；Task 2–13 不得另建同义模型或引用未来类型。
- 任一失败不得通过固定比例、机械轮换、章节号特判、默认主角 POV、候选写入 Memory 或把候选注入 Writer 来规避。
- 最终必须同时通过：全量 pytest、compileall、AST 依赖测试、禁止模式扫描、stale/重启/篡改/人工覆盖/崩溃负测和 `git diff --check`。
- 不生成第27章或任何小说正文，不调用真实模型。
