# Narrative Replay Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立章节合同、叙事状态、只读章节回放和可解释叙事审核门禁，并使用现有验证小说第 1 至 6 章完成回放验收。

**Architecture:** 在 Novel Domain 内新增独立 `narrative` 包，事实继续来自 Knowledge 和现有生产 Artifact，叙事意图以不可变值对象表达。回放层只读取既有章节与上下文，输出带证据和不确定性标记的结构化结果；Reviewer 只生成 Issue，不修改正文、Knowledge 或 Project State。

**Tech Stack:** Python 3、标准库 `dataclasses`/`enum`/`json`/`pathlib`、pytest、现有 Creative OS Foundation 与生产 Artifact。

**Spec:** `docs/superpowers/specs/2026-08-18-authorial-narrative-control-design.md`

## Global Constraints

- `Knowledge` 继续作为事实真源，Narrative State 不保存正文全文。
- 第一阶段只回放现有第 1 至 6 章，不生成或改写正文。
- 缺少证据时必须输出 `unknown`，禁止推测事实。
- Reviewer 只返回证据、严重级别和修复建议，不直接修改任何产物。
- 不修改 Foundation 通用 `State`，叙事对象全部位于 Novel Domain。
- 不引入数据库、图数据库、前端、外部模型 SDK 或新运行时依赖。
- 每个任务严格采用测试先行；每次提交使用中文 Commit Message。

## File Structure

```text
creative_os/domains/novel_narrative/
├── __init__.py       对外导出稳定接口
├── models.py         章节合同、读者状态、人物主动性、伏笔和审核问题
├── store.py          追加式事件与当前 Narrative State 投影
├── evidence.py       从生产 Artifact 提取可追溯证据
├── replay.py         单章及 1-6 章只读回放编排
└── reviewer.py       可解释叙事审核门禁

scripts/replay_narrative.py               命令行回放入口
tests/test_narrative_models.py            值对象与约束测试
tests/test_narrative_store.py             事件版本和投影测试
tests/test_narrative_evidence.py          Artifact 读取测试
tests/test_narrative_replay.py            回放与不确定性测试
tests/test_narrative_reviewer.py          叙事门禁测试
tests/test_narrative_replay_script.py     CLI 与输出文件测试
```

---

### Task 1: Narrative Domain Models

**Files:**
- Create: `creative_os/domains/novel_narrative/__init__.py`
- Create: `creative_os/domains/novel_narrative/models.py`
- Test: `tests/test_narrative_models.py`

**Interfaces:**
- Consumes: 无。
- Produces: `EvidenceRef`、`ProtagonistChoice`、`ReaderState`、`AgencyEntry`、`ForeshadowAction`、`ChapterContract`、`NarrativeIssue`、`NarrativeState`。

- [ ] **Step 1: 编写失败测试，固定最小章节合同与冻结规则**

```python
from dataclasses import FrozenInstanceError
import pytest

from creative_os.domains.novel_narrative.models import (
    ChapterContract,
    EvidenceRef,
    ProtagonistChoice,
)


def test_chapter_contract_requires_evidence_and_is_immutable():
    contract = ChapterContract(
        chapter_id="chapter_001",
        functions=("建立主角的初始困境",),
        dramatic_question="主角是否决定追查失踪事件？",
        protagonist_choice=ProtagonistChoice(
            actor="林川",
            action="决定追查",
            cost="暴露自身行踪",
            consequence="被监视者注意",
        ),
        evidence=(EvidenceRef("chapter", "final_chapters/chapter_001.md", "决定追查"),),
    )
    contract.validate()
    with pytest.raises(FrozenInstanceError):
        contract.chapter_id = "chapter_002"


def test_chapter_contract_rejects_claim_without_evidence():
    contract = ChapterContract(
        chapter_id="chapter_001",
        functions=("推进主线",),
        dramatic_question="是否继续调查？",
        protagonist_choice=None,
        evidence=(),
    )
    with pytest.raises(ValueError, match="evidence"):
        contract.validate()
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `python -m pytest -q tests/test_narrative_models.py`

Expected: FAIL，包含 `ModuleNotFoundError`。

- [ ] **Step 3: 实现不可变值对象与显式校验**

```python
@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source_type: str
    source_ref: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class ProtagonistChoice:
    actor: str
    action: str
    cost: str
    consequence: str


@dataclass(frozen=True, slots=True)
class ChapterContract:
    chapter_id: str
    functions: tuple[str, ...]
    dramatic_question: str
    protagonist_choice: ProtagonistChoice | None
    evidence: tuple[EvidenceRef, ...]
    reader_before: str = "unknown"
    reader_after: str = "unknown"
    pressure_start: str = "unknown"
    pressure_end: str = "unknown"
    ending_shift: str = "unknown"

    def validate(self) -> None:
        if not self.chapter_id or not self.functions or not self.dramatic_question:
            raise ValueError("chapter contract requires id, functions and dramatic question")
        if not self.evidence:
            raise ValueError("chapter contract requires evidence")
```

同时实现以下明确字段；集合字段统一使用 tuple，未知信息统一使用字符串 `unknown`，不允许 `Any`。

```python
@dataclass(frozen=True, slots=True)
class ReaderState:
    known: tuple[str, ...] = ()
    suspected: tuple[str, ...] = ()
    misbeliefs: tuple[str, ...] = ()
    expectations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgencyEntry:
    actor: str
    desire: str
    choice: str
    cost: str
    consequence: str
    source_chapter: str
    evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class ForeshadowAction:
    foreshadow_id: str
    action: str
    next_action: str
    source_chapter: str
    evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class NarrativeIssue:
    code: str
    severity: str
    message: str
    evidence: tuple[EvidenceRef, ...]
    repair_hint: str


@dataclass(frozen=True, slots=True)
class NarrativeState:
    project_id: str
    version: int = 0
    chapter_contracts: tuple[ChapterContract, ...] = ()
    reader_state: ReaderState = ReaderState()
    agency_ledger: tuple[AgencyEntry, ...] = ()
    foreshadow_actions: tuple[ForeshadowAction, ...] = ()
```

- [ ] **Step 4: 运行模型测试**

Run: `python -m pytest -q tests/test_narrative_models.py`

Expected: PASS。

- [ ] **Step 5: 提交模型层**

```powershell
git add creative_os/domains/novel_narrative tests/test_narrative_models.py
git commit -m "新增小说叙事状态模型"
```

---

### Task 2: Append-only Narrative Store

**Files:**
- Create: `creative_os/domains/novel_narrative/store.py`
- Modify: `creative_os/domains/novel_narrative/__init__.py`
- Test: `tests/test_narrative_store.py`

**Interfaces:**
- Consumes: `ChapterContract`、`NarrativeState`。
- Produces: `NarrativeEvent(version: int, kind: str, chapter_id: str, payload: ChapterContract)`、`NarrativeStore.append(event) -> NarrativeState`、`snapshot() -> NarrativeState`。

- [ ] **Step 1: 编写事件连续性与快照隔离测试**

```python
def test_store_rejects_non_contiguous_event_version(valid_contract):
    store = NarrativeStore(project_id="validation_novel")
    with pytest.raises(ValueError, match="version"):
        store.append(NarrativeEvent(2, "chapter_replayed", "chapter_001", valid_contract))


def test_store_projects_replayed_contract_without_exposing_mutable_state(valid_contract):
    store = NarrativeStore(project_id="validation_novel")
    state = store.append(NarrativeEvent(1, "chapter_replayed", "chapter_001", valid_contract))
    assert state.version == 1
    assert state.chapter_contracts == (valid_contract,)
    assert store.snapshot() == state
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest -q tests/test_narrative_store.py`

Expected: FAIL，缺少 `NarrativeStore`。

- [ ] **Step 3: 实现只接受已知事件的追加式 Store**

```python
KNOWN_EVENT_KINDS = frozenset({"chapter_replayed"})

def append(self, event: NarrativeEvent) -> NarrativeState:
    expected = self._state.version + 1
    if event.version != expected:
        raise ValueError(f"event version must be {expected}")
    if event.kind not in KNOWN_EVENT_KINDS:
        raise ValueError(f"unknown narrative event: {event.kind}")
    self._events = (*self._events, event)
    self._state = replace(
        self._state,
        version=event.version,
        chapter_contracts=(*self._state.chapter_contracts, event.payload),
    )
    return self.snapshot()
```

- [ ] **Step 4: 运行 Store 与模型测试**

Run: `python -m pytest -q tests/test_narrative_store.py tests/test_narrative_models.py`

Expected: PASS。

- [ ] **Step 5: 提交追加式投影**

```powershell
git add creative_os/domains/novel_narrative tests/test_narrative_store.py
git commit -m "实现叙事事件投影存储"
```

---

### Task 3: Production Artifact Evidence Reader

**Files:**
- Create: `creative_os/domains/novel_narrative/evidence.py`
- Test: `tests/test_narrative_evidence.py`

**Interfaces:**
- Consumes: `project_root: Path`、`chapter_number: int`。
- Produces: `ChapterEvidence(chapter_id, prose, contexts, reviews, knowledge, source_refs)`；入口 `load_chapter_evidence(project_root, chapter_number)`。

- [ ] **Step 1: 编写只读加载与缺失文件测试**

```python
def test_load_chapter_evidence_reads_canonical_artifacts(tmp_path):
    root = seed_chapter_artifacts(tmp_path, chapter_number=1)
    evidence = load_chapter_evidence(root, 1)
    assert evidence.chapter_id == "chapter_001"
    assert "主角" in evidence.prose
    assert evidence.source_refs[0].endswith("chapter_001.md")


def test_load_chapter_evidence_fails_when_canonical_chapter_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="chapter_001"):
        load_chapter_evidence(tmp_path, 1)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest -q tests/test_narrative_evidence.py`

Expected: FAIL，缺少证据读取器。

- [ ] **Step 3: 实现明确路径、UTF-8、无写操作的读取器**

```python
def load_chapter_evidence(project_root: str | Path, chapter_number: int) -> ChapterEvidence:
    root = Path(project_root)
    chapter_id = f"chapter_{chapter_number:03d}"
    prose_path = root / "production" / "final_chapters" / f"{chapter_id}.md"
    if not prose_path.is_file():
        raise FileNotFoundError(f"missing canonical chapter: {chapter_id}")
    chapter_root = root / "production" / chapter_id
    return ChapterEvidence(
        chapter_id=chapter_id,
        prose=prose_path.read_text(encoding="utf-8"),
        contexts=_read_json_files(chapter_root / "contexts"),
        reviews=_read_text_files(chapter_root / "reviews"),
        knowledge=_read_json_files(chapter_root / "knowledge"),
        source_refs=(str(prose_path.relative_to(root)),),
    )
```

所有目录读取按文件名排序；JSON 解码错误必须携带文件路径重新抛出 `ValueError`。

- [ ] **Step 4: 运行证据读取测试**

Run: `python -m pytest -q tests/test_narrative_evidence.py`

Expected: PASS。

- [ ] **Step 5: 提交证据读取器**

```powershell
git add creative_os/domains/novel_narrative/evidence.py tests/test_narrative_evidence.py
git commit -m "增加章节生产证据读取器"
```

---

### Task 4: Deterministic Chapter Replay

**Files:**
- Create: `creative_os/domains/novel_narrative/replay.py`
- Modify: `creative_os/domains/novel_narrative/__init__.py`
- Test: `tests/test_narrative_replay.py`

**Interfaces:**
- Consumes: `ChapterEvidence`。
- Produces: `replay_chapter(evidence: ChapterEvidence) -> ChapterContract`、`replay_range(project_root, start=1, end=6) -> tuple[ChapterContract, ...]`。

- [ ] **Step 1: 编写证据优先和 unknown 规则测试**

```python
def test_replay_marks_unproven_reader_change_unknown(minimal_evidence):
    contract = replay_chapter(minimal_evidence)
    assert contract.reader_before == "unknown"
    assert contract.reader_after == "unknown"
    assert contract.evidence


def test_replay_range_defaults_to_first_six_chapters(validation_project_root):
    contracts = replay_range(validation_project_root)
    assert [item.chapter_id for item in contracts] == [
        f"chapter_{number:03d}" for number in range(1, 7)
    ]
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest -q tests/test_narrative_replay.py`

Expected: FAIL，缺少回放接口。

- [ ] **Step 3: 实现确定性回放器**

回放只从结构化 Context、Review 和 Knowledge 中取明确字段；正文只用于定位证据摘录，不通过关键词猜测人物心理。无法形成 `ProtagonistChoice` 时设为 `None`，同时保留至少一个说明证据来源的 `EvidenceRef`。

```python
def replay_range(project_root: str | Path, start: int = 1, end: int = 6) -> tuple[ChapterContract, ...]:
    if start < 1 or end < start:
        raise ValueError("invalid replay range")
    return tuple(
        replay_chapter(load_chapter_evidence(project_root, number))
        for number in range(start, end + 1)
    )
```

- [ ] **Step 4: 运行回放相关测试**

Run: `python -m pytest -q tests/test_narrative_replay.py tests/test_narrative_evidence.py tests/test_narrative_models.py`

Expected: PASS。

- [ ] **Step 5: 提交只读回放能力**

```powershell
git add creative_os/domains/novel_narrative tests/test_narrative_replay.py
git commit -m "实现章节合同只读回放"
```

---

### Task 5: Explainable Narrative Reviewer

**Files:**
- Create: `creative_os/domains/novel_narrative/reviewer.py`
- Modify: `creative_os/domains/novel_narrative/__init__.py`
- Test: `tests/test_narrative_reviewer.py`

**Interfaces:**
- Consumes: 当前 `ChapterContract`、最近 `tuple[ChapterContract, ...]`。
- Produces: `review_contract(contract, recent=()) -> tuple[NarrativeIssue, ...]`。

- [ ] **Step 1: 编写主动性缺失与章节功能重复测试**

```python
def test_reviewer_reports_missing_protagonist_choice(contract_without_choice):
    issues = review_contract(contract_without_choice)
    issue = next(item for item in issues if item.code == "missing_protagonist_choice")
    assert issue.severity == "warning"
    assert issue.evidence


def test_reviewer_reports_repeated_chapter_function(current_contract, previous_contract):
    issues = review_contract(current_contract, recent=(previous_contract,))
    assert any(item.code == "repeated_chapter_function" for item in issues)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest -q tests/test_narrative_reviewer.py`

Expected: FAIL，缺少 Reviewer。

- [ ] **Step 3: 实现第一版五项门禁**

门禁代码固定为：

```text
missing_protagonist_choice
missing_choice_cost
unknown_reader_change
repeated_chapter_function
unknown_ending_shift
```

每个 Issue 必须包含 `code`、`severity`、`message`、`evidence`、`repair_hint`。Reviewer 不接收路径、Store 或正文写入接口。

- [ ] **Step 4: 运行 Reviewer 与回放测试**

Run: `python -m pytest -q tests/test_narrative_reviewer.py tests/test_narrative_replay.py`

Expected: PASS。

- [ ] **Step 5: 提交叙事审核门禁**

```powershell
git add creative_os/domains/novel_narrative tests/test_narrative_reviewer.py
git commit -m "建立可解释叙事审核门禁"
```

---

### Task 6: Replay CLI and Validation Report

**Files:**
- Create: `scripts/replay_narrative.py`
- Create: `tests/test_narrative_replay_script.py`
- Modify: `README.md`
- Modify: `docs/PROJECT_STATUS_REVIEW.md`
- Generate: `projects/validation_novel/production/reports/narrative_replay_001_006.json`
- Generate: `projects/validation_novel/production/reports/narrative_replay_001_006.md`

**Interfaces:**
- Consumes: `replay_range()`、`review_contract()`。
- Produces: `run(project_root: Path, start: int, end: int, output_dir: Path) -> dict[str, object]` 和 JSON/Markdown 报告。

- [ ] **Step 1: 编写 CLI 产物与只读保护测试**

```python
def test_replay_script_writes_json_and_markdown_without_modifying_chapters(tmp_path):
    root = seed_six_chapter_project(tmp_path)
    before = snapshot_file_hashes(root / "production" / "final_chapters")
    result = run(root, 1, 6, root / "production" / "reports")
    after = snapshot_file_hashes(root / "production" / "final_chapters")
    assert result["chapter_count"] == 6
    assert (root / "production/reports/narrative_replay_001_006.json").is_file()
    assert (root / "production/reports/narrative_replay_001_006.md").is_file()
    assert before == after
```

- [ ] **Step 2: 运行脚本测试并确认失败**

Run: `python -m pytest -q tests/test_narrative_replay_script.py`

Expected: FAIL，缺少 `scripts.replay_narrative`。

- [ ] **Step 3: 实现 CLI 和稳定序列化**

```powershell
python scripts\replay_narrative.py --project-root projects\validation_novel --start 1 --end 6
```

JSON 保存完整结构化合同、Issue 和证据；Markdown 按章节展示功能、戏剧问题、人物选择、代价、读者变化、结尾变化、Issue 与不确定项。输出前先构建完整 payload，只有全部章节成功后才写报告，避免留下半成品。

- [ ] **Step 4: 执行 1 至 6 章正式回放**

Run: `python scripts\replay_narrative.py --project-root projects\validation_novel --start 1 --end 6`

Expected: 生成两个报告，退出码为 0，原章节文件哈希不变。

- [ ] **Step 5: 运行完整回归测试**

Run: `python -m pytest -q`

Expected: 原有 85 个测试与新增测试全部通过。

- [ ] **Step 6: 更新项目状态文档**

README 增加回放命令；状态报告记录实际回放结果、Issue 数量、不确定项数量和是否满足“可追溯叙事解释”验收标准，不提前宣称 Director 已完成。

- [ ] **Step 7: 提交回放验收结果**

```powershell
git add scripts/replay_narrative.py tests/test_narrative_replay_script.py README.md docs/PROJECT_STATUS_REVIEW.md projects/validation_novel/production/reports/narrative_replay_001_006.*
git commit -m "完成前六章叙事回放验证"
```

---

## Final Acceptance

- [ ] `python -m pytest -q` 全部通过。
- [ ] 第 1 至 6 章均生成唯一 Chapter Contract。
- [ ] 每项确定性结论都带有可定位证据。
- [ ] 无法确认的 Reader State、人物选择或结尾变化明确标记为 `unknown`。
- [ ] Reviewer 至少覆盖五项固定门禁，并且不修改正文。
- [ ] 回放前后 `production/final_chapters/chapter_001.md` 至 `chapter_006.md` 内容哈希一致。
- [ ] JSON 和 Markdown 报告可重复生成且内容稳定。
- [ ] 未实现 Director、自动改纲、正文生成或自动修复。

## Next Stage Gate

只有当第 1 至 6 章回放能够稳定输出可追溯章节解释，并且人工抽查确认不存在伪造事实后，才编写下一阶段计划：`Narrative Director + Chapter Contract Approval`。
