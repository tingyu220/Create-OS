# Novel Domain Package V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有分散的小说能力收敛为可加载、可执行、可验证的 Novel Domain 单章生产闭环。

**Architecture:** 新增薄层 `NovelDomainService` 组合现有 Narrative、State、Publication 服务，不建立第二事实源；先扩充 Scene/Chapter 领域不变量，再实现统一 Reviewer、Compiler 和 Lesson Candidate。所有 Canon 写入继续走审批与证据校验。

**Tech Stack:** Python 3.11+、dataclasses、pytest、现有 JSON/JSONL Store 与 SHA-256 内容寻址。

**Spec:** `docs/superpowers/specs/2026-08-30-novel-domain-package-v1-design.md`

## Global Constraints

- 《文明升阶》仅作为回归样本，不得在通用领域代码中硬编码作品名称、人物或章节号。
- 不修改通用 Project、Task、Workflow、Knowledge 核心对象语义。
- 不建立与 Narrative Contract、EvidenceRef、StateChange 平行的第二事实源。
- 所有缺证、冲突、未审批输入必须失败关闭。
- 先写失败测试，再写最小实现；每个任务独立通过测试后再进入下一任务。
- 本计划不包含提交和推送；提交前必须向用户确认，Commit Message 使用中文。

---

### Task 1: Novel Domain 能力目录与稳定入口

**Files:**
- Create: `creative_os/domains/novel_capabilities.py`
- Create: `creative_os/domains/novel_domain_service.py`
- Modify: `creative_os/domains/novel.py`
- Test: `tests/test_novel_domain_service.py`

**Interfaces:**
- Consumes: `NovelDomainPackage`、现有 Narrative/State 服务实例。
- Produces: `NovelCapabilityCatalog`、`NovelDomainService.capabilities()`。

- [ ] **Step 1: 写失败测试**

```python
def test_novel_domain_exposes_executable_capabilities():
    service = NovelDomainService.for_testing()
    assert service.capabilities().names == (
        "chapter_planning", "writer_admission", "draft_writing", "draft_review",
        "approved_compile", "lesson_candidate",
    )
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest -q tests/test_novel_domain_service.py::test_novel_domain_exposes_executable_capabilities`

Expected: FAIL，提示 `NovelDomainService` 尚不存在。

- [ ] **Step 3: 实现不可变能力目录与构造注入**

```python
@dataclass(frozen=True, slots=True)
class NovelCapabilityCatalog:
    names: tuple[str, ...]

class NovelDomainService:
    def __init__(self, planner, admission, writer, reviewer, compiler, lesson_builder):
        self._planner = planner
        self._admission = admission
        self._writer = writer
        self._reviewer = reviewer
        self._compiler = compiler
        self._lesson_builder = lesson_builder

    def capabilities(self) -> NovelCapabilityCatalog:
        return NovelCapabilityCatalog((
            "chapter_planning", "writer_admission", "draft_writing", "draft_review",
            "approved_compile", "lesson_candidate",
        ))
```

- [ ] **Step 4: 运行领域基础测试**

Run: `pytest -q tests/test_novel_domain.py tests/test_novel_domain_service.py`

Expected: PASS。

### Task 2: Scene 叙事目的、必要信息与闭合契约

**Files:**
- Modify: `creative_os/domains/narrative_decision.py`
- Modify: `creative_os/domains/narrative_codec.py`
- Modify: `creative_os/domains/narrative_director.py`
- Test: `tests/test_novel_scene_contract.py`
- Modify Test: `tests/test_narrative_codec.py`

**Interfaces:**
- Consumes: 现有 `SceneContract`、`ScenePlan`、Narrative Codec。
- Produces: `SceneClosure` 与带 `narrative_purpose`、`essential_information`、`emotional_change` 的 `SceneContract`。

- [ ] **Step 1: 写缺少叙事目的与必要信息时失败的测试**

```python
def test_scene_contract_requires_purpose_information_and_closure():
    scene = complete_scene(
        narrative_purpose="",
        essential_information=(),
        closure=SceneClosure(False, False, False, False),
    )
    with pytest.raises(NarrativeValidationError):
        scene.validate()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest -q tests/test_novel_scene_contract.py`

Expected: FAIL，提示字段或类型不存在。

- [ ] **Step 3: 增加模型与严格校验**

```python
@dataclass(frozen=True, slots=True)
class SceneClosure:
    goal_addressed: bool
    conflict_advanced: bool
    choice_made: bool
    outcome_recorded: bool

    @property
    def complete(self) -> bool:
        return all((self.goal_addressed, self.conflict_advanced,
                    self.choice_made, self.outcome_recorded))
```

`SceneContract.validate()` 必须拒绝空 `narrative_purpose`、空 `essential_information`、空 `emotional_change` 和未闭合 Scene。

- [ ] **Step 4: 扩充 Codec 并验证往返不丢字段**

Run: `pytest -q tests/test_novel_scene_contract.py tests/test_narrative_codec.py`

Expected: PASS，encode/decode 后新字段完全一致。

### Task 3: Chapter Boundary 与碎章准入

**Files:**
- Create: `creative_os/domains/novel_chapter_boundary.py`
- Create: `creative_os/domains/novel_chapter_planner.py`
- Test: `tests/test_novel_chapter_boundary.py`
- Test: `tests/test_novel_chapter_planner.py`

**Interfaces:**
- Consumes: 完整 `ScenePlan`、目标字数区间、前后章节状态。
- Produces: `ChapterBoundaryAssessment`、`ChapterPlanResult`。

- [ ] **Step 1: 写三个真实失败模式测试**

```python
@pytest.mark.parametrize("dialogue_closed,dramatic_unit_closed,code", [
    (False, True, "dialogue_cut"),
    (True, False, "dramatic_unit_incomplete"),
    (False, False, "fragment_chapter"),
])
def test_boundary_rejects_incomplete_units(dialogue_closed, dramatic_unit_closed, code):
    result = assess_boundary(boundary(dialogue_closed, dramatic_unit_closed))
    assert code in result.blocking_codes
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest -q tests/test_novel_chapter_boundary.py tests/test_novel_chapter_planner.py`

Expected: FAIL，边界模型尚不存在。

- [ ] **Step 3: 实现边界评估与 Planner 失败关闭**

`ChapterPlanResult.approved` 仅在 Scene 顺序连续、每个 Scene 闭合、章节出口状态存在且边界无阻断问题时为真。字数只作为约束之一，不能覆盖戏剧单元闭合。

- [ ] **Step 4: 添加《文明升阶》匿名化回归夹具**

从旧第29章问答碎片、第35章谈判中段、第40章未完成选择中提取不含作品专名的最小夹具，分别期望 `fragment_chapter`、`dramatic_unit_incomplete`、`dialogue_cut`。

- [ ] **Step 5: 运行测试**

Run: `pytest -q tests/test_novel_chapter_boundary.py tests/test_novel_chapter_planner.py`

Expected: PASS。

### Task 4: 统一 Novel Reviewer

**Files:**
- Create: `creative_os/domains/novel_review_model.py`
- Create: `creative_os/domains/novel_reviewer.py`
- Test: `tests/test_novel_reviewer.py`

**Interfaces:**
- Consumes: Draft、Chapter Contract、ScenePlan、相关 State 与前后章边界。
- Produces: `NovelReviewResult(issues, blocking_codes, passed)`。

- [ ] **Step 1: 写重复长段、弱边界和人物漂移测试**

```python
def test_reviewer_blocks_duplicate_long_paragraph():
    result = reviewer.review(request_with_duplicate_paragraph(length=80))
    assert "duplicate_long_paragraph" in result.blocking_codes

def test_reviewer_blocks_character_state_drift_without_evidence():
    result = reviewer.review(request_with_unsupported_character_change())
    assert "character_state_drift" in result.blocking_codes
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest -q tests/test_novel_reviewer.py`

Expected: FAIL，Reviewer 尚不存在。

- [ ] **Step 3: 实现证据化问题模型和首批规则**

每个 `NovelReviewIssue` 必须包含非空 `evidence`、明确 `scope` 与 `repair_kind`；阻断问题使 `passed=False`。

- [ ] **Step 4: 运行测试**

Run: `pytest -q tests/test_novel_reviewer.py tests/test_narrative_review.py tests/test_publication_length_review.py`

Expected: PASS。

### Task 5: 通过稿编译为 Canon/State 候选

**Files:**
- Create: `creative_os/domains/novel_compile_model.py`
- Create: `creative_os/domains/novel_compiler.py`
- Test: `tests/test_novel_compiler.py`

**Interfaces:**
- Consumes: `NovelReviewResult(passed=True)`、正文内容哈希、现有 `StateChange` 与 EvidenceRef。
- Produces: `NovelCompileResult(canon_patches, state_changes, next_task_input, fingerprint)`。

- [ ] **Step 1: 写未通过审查不得编译的测试**

```python
def test_compiler_rejects_unapproved_draft():
    with pytest.raises(NovelCompileError, match="review_not_passed"):
        compiler.compile(request(review=failed_review()))
```

- [ ] **Step 2: 写通过稿生成有证据候选的测试**

```python
def test_compiler_emits_evidence_bound_candidates():
    result = compiler.compile(request(review=passed_review()))
    assert result.fingerprint
    assert all(change.evidence for change in result.state_changes)
    assert result.next_task_input.previous_chapter_hash == request().content_hash
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest -q tests/test_novel_compiler.py`

Expected: FAIL，Compiler 尚不存在。

- [ ] **Step 4: 实现纯候选编译，不直接写 Store**

Compiler 只返回不可变候选；现有审批服务负责后续写入，禁止 Compiler 自行覆盖 Snapshot。

- [ ] **Step 5: 运行测试**

Run: `pytest -q tests/test_novel_compiler.py tests/test_novel_state_model.py tests/test_narrative_memory.py`

Expected: PASS。

### Task 6: 修订经验 Lesson Candidate

**Files:**
- Create: `creative_os/domains/novel_lesson.py`
- Test: `tests/test_novel_lesson.py`

**Interfaces:**
- Consumes: 原 Draft 哈希、Review Issue、Repair 变更、Final Draft 哈希。
- Produces: `NovelLessonCandidate`，不直接修改稳定规则。

- [ ] **Step 1: 写完整因果链要求测试**

```python
def test_lesson_requires_issue_repair_and_final_evidence():
    with pytest.raises(ValueError, match="lesson_evidence_incomplete"):
        build_lesson_candidate(issue=None, repair=None, final_hash="f" * 64)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest -q tests/test_novel_lesson.py`

Expected: FAIL。

- [ ] **Step 3: 实现候选与稳定指纹**

Lesson 至少记录 `failure_code`、`context_fingerprint`、`repair_action`、`before_hash`、`after_hash`、`validation_evidence`，状态固定为 `candidate`。

- [ ] **Step 4: 运行测试**

Run: `pytest -q tests/test_novel_lesson.py`

Expected: PASS。

### Task 7: 单章闭环 Facade 与真实回归

**Files:**
- Modify: `creative_os/domains/novel_domain_service.py`
- Create: `tests/fixtures/novel_domain/civilization_regressions.json`
- Test: `tests/test_novel_domain_end_to_end.py`
- Modify: `docs/novel-production-roadmap.md`

**Interfaces:**
- Consumes: Task 1—6 的 Planner、Admission、Reviewer、Compiler、Lesson Builder。
- Produces: 可恢复的 `NovelChapterRunResult` 与 V1 回归报告。

- [ ] **Step 1: 写端到端失败关闭测试**

```python
def test_domain_service_stops_before_compile_when_review_fails():
    result = service.run_chapter(fragment_chapter_request())
    assert result.stage == "review_failed"
    assert result.compile_result is None
```

- [ ] **Step 2: 写通过路径测试**

```python
def test_domain_service_completes_approved_chapter_cycle():
    result = service.run_chapter(valid_chapter_request())
    assert result.stage == "compile_candidate_ready"
    assert result.compile_result.state_changes
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest -q tests/test_novel_domain_end_to_end.py`

Expected: FAIL，Facade 尚未组合完整闭环。

- [ ] **Step 4: 实现组合，不复制子系统逻辑**

`run_chapter()` 依次调用 Planner、Admission、Reviewer、Compiler；任何阻断结果立即返回，且保留阶段、问题和输入指纹。

- [ ] **Step 5: 运行 Novel Domain 回归集**

Run: `pytest -q tests/test_novel_domain*.py tests/test_novel_scene_contract.py tests/test_novel_chapter_*.py tests/test_novel_reviewer.py tests/test_novel_compiler.py tests/test_novel_lesson.py`

Expected: PASS。

- [ ] **Step 6: 更新路线图状态**

将 `docs/novel-production-roadmap.md` 从“第27章生产边界”更新为 Novel Domain V1 能力阶段，记录已完成能力、下一能力和《文明升阶》回归结果，不把作品进度写成领域完成度。

### Task 8: 全量验证与交付审查

**Files:**
- Modify only if failures expose defects in Task 1—7 files.

**Interfaces:**
- Consumes: 完整工作树。
- Produces: 测试证据与未提交交付状态。

- [ ] **Step 1: 运行新增测试**

Run: `pytest -q tests/test_novel_domain_service.py tests/test_novel_scene_contract.py tests/test_novel_chapter_boundary.py tests/test_novel_chapter_planner.py tests/test_novel_reviewer.py tests/test_novel_compiler.py tests/test_novel_lesson.py tests/test_novel_domain_end_to_end.py`

Expected: PASS。

- [ ] **Step 2: 运行相关回归测试**

Run: `pytest -q tests/test_narrative_codec.py tests/test_narrative_director.py tests/test_narrative_review.py tests/test_novel_state_model.py tests/test_publication_length_review.py tests/test_publication_split_planner.py`

Expected: PASS。

- [ ] **Step 3: 检查通用模块无作品硬编码**

Run: `rg -n "文明升阶|林子轩|陈景行" creative_os`

Expected: 无输出。

- [ ] **Step 4: 检查工作树并等待提交授权**

Run: `git status --short`

Expected: 仅出现本计划相关文件及用户既有改动；不提交、不推送。
