# 作者式动态叙事控制层实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不接入网文示例库的前提下，为 Creative OS 增加可版本化的叙事状态、章节 Director、叙事审核门禁和可追溯回放接口。

**Architecture:** `Knowledge` 继续作为事实真源，Novel Domain 内新增 `NarrativeState` 及其事件投影；Director 只输出已结构化的章节决策，Planner/Writer 消费已审批决策，Reviewer 只报告问题，Compiler 继续负责已审批结果的事实更新。历史通过追加事件保留，运行时只构建当前叙事投影。

**Tech Stack:** Python 3.11+、标准库 `dataclasses`/`enum`/`json`、pytest；不新增第三方依赖，不引入图数据库或网文示例库。

**Spec:** `docs/superpowers/specs/2026-08-18-authorial-narrative-control-design.md`

## Global Constraints

- `Knowledge` 是事实真源；叙事层不能覆盖事实。
- Narrative 对象只存在于 Novel Domain，不修改 Foundation 通用 State 的职责。
- Writer 不得自行改纲；Reviewer 不得静默改写；已审批章节合同不可静默覆盖。
- 情绪、场景数量和高潮间隔只能作为判断依据，不实现固定配额。
- 回放验证完成前不生成第 7 章、不接入网文示例库、不做远程提交或推送。
- 保留现有 `CAPABILITY/Research.md` 未提交修改。

---

### Task 1: 建立 Narrative Domain 数据模型

**Files:**
- Create: `creative_os/domains/narrative.py`
- Modify: `creative_os/domains/novel.py`
- Test: `tests/test_narrative_model.py`
- Test: `tests/test_novel_domain.py`

**Interfaces:**
- `NarrativeState`：聚合 `StoryContract`、`ScaleState`、`ReaderState`、`ChapterContract`、`AgencyEntry`、`ForeshadowLifecycle` 和 `OutlineChange`。
- `NarrativeState.validate() -> None`：验证必填标识、枚举值、目标字数为正数，以及章节决策的主动选择字段完整。
- `ChapterContract.freeze() -> ChapterContract`：返回不可变语义的副本；已冻结合同不能通过普通更新方法修改。
- `NovelDomainPackage` 新增 Narrative schema 名称和叙事规则。

- [ ] **Step 1: Write the failing tests**

```python
def test_chapter_contract_requires_choice_cost_and_reader_change():
    contract = ChapterContract(chapter_id="c1", functions=["推进主线"])
    with pytest.raises(NarrativeValidationError):
        contract.validate()

def test_frozen_chapter_contract_rejects_mutation():
    contract = valid_chapter_contract("c1").freeze()
    with pytest.raises(NarrativeStateError):
        contract.replace(functions=["关系变化"])

def test_novel_domain_exposes_narrative_objects_and_rules():
    domain = NovelDomainPackage()
    assert "ChapterContract" in domain.schema
    assert "reader_state_tracking" in domain.rules_for("review")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_narrative_model.py tests/test_novel_domain.py -v`

Expected: FAIL because the narrative module, contract API, and domain entries do not exist.

- [ ] **Step 3: Implement the minimal model**

Use focused frozen dataclasses for value objects and explicit `replace()` methods that reject frozen contracts. Use `StrEnum` for `ArcPhase`, `ForeshadowState`, `OutlineChangeStrategy`, and `OutlineChangeStatus`. Do not store manuscript text in `NarrativeState`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_narrative_model.py tests/test_novel_domain.py -v`

Expected: PASS.

---

### Task 2: 实现追加事件与当前投影

**Files:**
- Create: `creative_os/domains/narrative_store.py`
- Test: `tests/test_narrative_store.py`

**Interfaces:**
- `NarrativeEvent(event_id: str, kind: str, source: str, payload: dict[str, object], version: int)`。
- `NarrativeStore.append(event: NarrativeEvent) -> NarrativeState`：追加事件并返回新投影；事件版本必须连续。
- `NarrativeStore.snapshot() -> NarrativeState`：返回当前状态副本。
- `NarrativeStore.events() -> list[NarrativeEvent]`：按版本返回事件历史。
- `NarrativeStore.propose_change(change: OutlineChange) -> None`、`approve_change(change_id: str) -> NarrativeState`。

- [ ] **Step 1: Write the failing tests**

```python
def test_append_updates_projection_and_keeps_event_history():
    store = NarrativeStore(initial_state=empty_narrative_state())
    state = store.append(chapter_approved_event("c1"))
    assert state.chapter_contract.chapter_id == "c1"
    assert [event.version for event in store.events()] == [1]

def test_out_of_order_event_is_rejected_without_mutating_state():
    store = NarrativeStore(initial_state=empty_narrative_state())
    store.append(chapter_approved_event("c1", version=1))
    with pytest.raises(NarrativeEventError):
        store.append(chapter_approved_event("c2", version=3))
    assert len(store.events()) == 1

def test_outline_change_requires_approval_before_application():
    store = NarrativeStore(initial_state=empty_narrative_state())
    store.propose_change(valid_outline_change("change-1"))
    assert store.snapshot().outline_changes[0].status == OutlineChangeStatus.PROPOSED
    store.approve_change("change-1")
    assert store.snapshot().outline_changes[0].status == OutlineChangeStatus.APPLIED
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `pytest tests/test_narrative_store.py -v`

Expected: FAIL because the event store does not exist.

- [ ] **Step 3: Implement event application and copy-on-read**

Use an in-memory store first. Apply only known event kinds: `chapter_approved`, `reader_state_updated`, `agency_recorded`, `foreshadow_advanced`, and `outline_change_proposed`. Reject unknown kinds and non-contiguous versions. Never expose mutable internal lists.

- [ ] **Step 4: Run the focused tests**

Run: `pytest tests/test_narrative_store.py -v`

Expected: PASS.

---

### Task 3: 将叙事投影接入 Context

**Files:**
- Modify: `creative_os/engine/context.py`
- Test: `tests/test_context_model.py`
- Test: `tests/test_narrative_context.py`

**Interfaces:**
- `Context.narrative: NarrativeState | None`：保持默认值 `None`，兼容现有 V1 调用方。
- `ContextBuilder.build(..., narrative: NarrativeState | None = None) -> Context`。
- Context 大小估算必须包含叙事投影序列化后的字符数，并继续执行 `max_chars` 限制。

- [ ] **Step 1: Write the failing tests**

```python
def test_context_carries_narrative_projection_without_full_history():
    context = ContextBuilder().build(
        user_input="规划下一章",
        task=task_for("t-narrative"),
        state=state_for("t-narrative"),
        retrieved=[],
        domain=NovelDomainPackage(),
        narrative=small_narrative_state(),
    )
    assert context.narrative.chapter_contract.chapter_id == "c1"
    assert context.narrative_history_size == 0

def test_existing_context_calls_remain_compatible():
    context = existing_context_call_without_narrative()
    assert context.narrative is None
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/test_context_model.py tests/test_narrative_context.py -v`

Expected: FAIL because `Context` has no narrative projection fields.

- [ ] **Step 3: Implement optional projection input**

Add only the current projection, never the event history. Estimate size using a deterministic JSON-like representation of the projection. Keep all existing domain and task boundary checks unchanged.

- [ ] **Step 4: Run focused and regression tests**

Run: `pytest tests/test_context_model.py tests/test_narrative_context.py tests/test_v1_pipeline.py -v`

Expected: PASS.

---

### Task 4: 实现结构化 Director 契约

**Files:**
- Create: `creative_os/capability/director.py`
- Test: `tests/test_director.py`

**Interfaces:**
- `DirectorInput(novel_state, narrative_state, recent_chapters, user_request, target_chinese_chars)`。
- `DirectorDecision(status, chapter_contract, scene_constraints, risks, change_proposal)`。
- `NarrativeDirector.propose(input: DirectorInput) -> DirectorDecision`。
- `DirectorDecision.status` 取 `proposed|blocked`；阻塞时必须携带可读风险，不返回可执行章节合同。

- [ ] **Step 1: Write the failing tests**

```python
def test_director_returns_auditable_chapter_contract_without_manuscript():
    decision = NarrativeDirector().propose(valid_director_input())
    assert decision.status == "proposed"
    assert decision.chapter_contract.target_chinese_chars == 3000
    assert not hasattr(decision, "manuscript")

def test_director_blocks_when_core_choice_is_missing():
    decision = NarrativeDirector().propose(input_without_protagonist_choice())
    assert decision.status == "blocked"
    assert "choice" in " ".join(decision.risks)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/test_director.py -v`

Expected: FAIL because the Director contract does not exist.

- [ ] **Step 3: Implement proposal validation**

The first Director is a deterministic contract builder/validator, not a prose model. It may copy an explicitly supplied proposed decision into a validated result, but it must not invent missing facts, alter `Knowledge`, or generate manuscript text. Target length is passed through and validated as a positive integer.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_director.py -v`

Expected: PASS.

---

### Task 5: 增加叙事审核门禁

**Files:**
- Create: `creative_os/capability/narrative_review.py`
- Test: `tests/test_narrative_review.py`

**Interfaces:**
- `NarrativeReviewIssue(code, message, severity, evidence)`。
- `NarrativeReviewReport(passed, issues)`。
- `NarrativeReviewer.review(contract: ChapterContract, recent: list[ChapterContract], prose: str = "") -> NarrativeReviewReport`。

- [ ] **Step 1: Write the failing tests**

```python
def test_review_rejects_missing_agency_cost_and_reader_change():
    report = NarrativeReviewer().review(incomplete_contract(), [])
    assert not report.passed
    assert {issue.code for issue in report.issues} >= {"missing_agency_cost", "missing_reader_change"}

def test_review_flags_duplicate_functions_and_repeated_time_opening():
    report = NarrativeReviewer().review(
        valid_chapter_contract("c2", functions=["追查"]),
        [valid_chapter_contract("c1", functions=["追查"])],
        prose="凌晨，雾压得很低。",
    )
    assert "duplicate_recent_function" in issue_codes(report)
    assert "repeated_time_opening" in issue_codes(report)

def test_review_does_not_change_contract_or_text():
    contract = valid_chapter_contract("c1")
    before = contract.to_dict()
    NarrativeReviewer().review(contract, [], prose="正文")
    assert contract.to_dict() == before
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/test_narrative_review.py -v`

Expected: FAIL because the review report and gates do not exist.

- [ ] **Step 3: Implement structural and narrow lexical gates**

Check contract completeness, recent function duplication, exact known time-word opening patterns, empty foreshadow actions, and missing ending shift. Do not claim semantic understanding from keyword absence; every issue must include the checked field or text prefix as evidence.

- [ ] **Step 4: Run focused tests and full regression**

Run: `pytest tests/test_narrative_review.py tests/ -q`

Expected: PASS.

---

### Task 6: 建立回放适配器与验证报告

**Files:**
- Create: `creative_os/domains/narrative_replay.py`
- Create: `tests/fixtures/narrative_replay/chapters.json`
- Create: `tests/test_narrative_replay.py`
- Create: `projects/validation_novel/design/narrative-replay-report.md`

**Interfaces:**
- `ReplayChapter(chapter_id, opening, contract, prose_source)`。
- `NarrativeReplay.load(path: Path) -> list[ReplayChapter]`：只读取显式提供的结构化回放输入。
- `NarrativeReplay.analyze(chapters: list[ReplayChapter]) -> ReplayReport`。
- `ReplayReport` 必须包含章节功能重复、时间词开头、人物主动性缺口、读者变化缺口、伏笔停滞和场景切换证据。

- [ ] **Step 1: Write the failing tests**

```python
def test_replay_reports_repeated_openings_and_functions():
    report = NarrativeReplay().analyze(load_fixture_chapters())
    assert "repeated_time_opening" in report.codes
    assert "duplicate_recent_function" in report.codes

def test_replay_refuses_missing_source_instead_of_inventing_analysis(tmp_path):
    with pytest.raises(ReplaySourceError):
        NarrativeReplay.load(tmp_path / "missing.json")
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/test_narrative_replay.py -v`

Expected: FAIL because the replay adapter and fixture schema do not exist.

- [ ] **Step 3: Implement explicit-input replay analysis**

The adapter must not infer unavailable chapter facts from memory or fabricate missing contracts. The repository currently contains no 《文明升阶》第 1 至 6 章 source files, so the fixture is a schema-level smoke fixture only; the actual novel report remains pending until those files or structured metadata are supplied in the active worktree.

- [ ] **Step 4: Run replay and regression tests**

Run: `pytest tests/test_narrative_replay.py tests/ -q`

Expected: PASS, with the report explicitly identifying whether it used fixture or production source.

- [ ] **Step 5: Produce the report from the real source when available**

Add a small `main(argv: list[str] | None = None) -> int` entry point in `creative_os/domains/narrative_replay.py` and run:

```text
python -m creative_os.domains.narrative_replay --source "D:\田雨\AI写作助手\NovelProject\Novels\文明升阶" --report "projects\validation_novel\design\narrative-replay-report.md"
```

The command records source path, chapter count, detected issues, and unknown fields without rewriting正文. If the source is absent, it exits with a clear `pending_source` result rather than claiming replay completion.

---

## Verification Matrix

| Requirement | Evidence |
|---|---|
| 多尺度剧情阶段 | `NarrativeState` tests and schema |
| 章节功能与人物主动性 | `ChapterContract` and Director tests |
| 读者预期与认知变化 | `ReaderState` validation and Reviewer tests |
| 情绪与节奏变化 | `pressure_curve` contract plus missing-change gate |
| 伏笔推进 | lifecycle enum, event application, review gate |
| 动态改纲 | proposal/approval event tests |
| 组件边界 | Context compatibility and Director no-manuscript tests |
| 第 1 至 6 章回放 | Replay report with explicit source evidence |

## Completion Gate

本计划不以“所有模型通过单元测试”替代小说回放证据。只有真实第 1 至 6 章资料进入回放适配器，并生成带来源的报告后，才能宣称回放验证完成。回放之前不生成第 7 章。
