# Creative OS System Memory Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立跨领域通用的分层记忆、候选经验人工审批和可追踪 Context 编译能力。

**Architecture:** Knowledge 继续保存可验证事实，Memory 独立保存工作信息、项目决策、用户偏好、领域方法和跨项目经验。运行结果只能生成候选经验，候选经验经人工批准后才可进入检索；`ContextCompiler` 按任务作用域召回并压缩 Knowledge 与 Memory，保留来源和使用原因。

**Tech Stack:** Python 3.11、dataclasses、StrEnum、JSON/JSONL、pytest；第一版不引入数据库和向量库。

## Global Constraints

- 通用核心不得包含小说专属字段或规则。
- 正式经验必须经过人工审批，系统不得自动晋升。
- Capability 只能读取编译后的 Context，不能直接读写 Knowledge 或 Memory。
- 所有记忆必须有作用域、来源、状态、版本和时间信息。
- 原始运行记录不可被记忆摘要覆盖；删除前归档并保留备份。
- 不修改 `KnowledgeItem` 的现有语义，避免破坏 V1 流水线。

## File Structure

- `creative_os/memory/model.py`：记忆实体、作用域、生命周期与验证。
- `creative_os/memory/store.py`：项目级 JSON 持久化、索引、归档和版本控制。
- `creative_os/memory/candidates.py`：从审查、重试和人工反馈生成候选经验。
- `creative_os/memory/approval.py`：人工批准、拒绝、降级和审计记录。
- `creative_os/memory/retriever.py`：按任务和作用域召回正式记忆。
- `creative_os/memory/context_compiler.py`：合并 Knowledge、Memory 与运行状态并输出可追踪 Context。
- `creative_os/memory/evaluation.py`：记录记忆命中及使用后的质量变化。
- `scripts/memory_review.py`：候选经验查看和人工审批 CLI。
- `tests/test_memory_*.py`：各边界的独立测试。

---

### Task 1: Define the Generic Memory Schema

**Files:**
- Create: `creative_os/memory/__init__.py`
- Create: `creative_os/memory/model.py`
- Test: `tests/test_memory_model.py`

**Interfaces:**
- Produces: `MemoryItem`, `MemoryKind`, `MemoryScope`, `MemoryStatus`, `MemoryEvidence`, `MemoryLifecycleError`。

- [ ] **Step 1: Write the failing schema tests**

```python
def test_experience_starts_as_candidate_and_requires_scope_and_evidence():
    item = MemoryItem.new_candidate(
        id="exp-001",
        kind=MemoryKind.EXPERIENCE,
        scope=MemoryScope.DOMAIN,
        scope_id="novel",
        title="避免模板化章节开头",
        content="章节开头不应连续使用统一时间词。",
        evidence=[MemoryEvidence(source_type="review", source_id="run-12", note="连续章节命中")],
    )
    assert item.status == MemoryStatus.CANDIDATE
    assert item.version == 1


def test_candidate_cannot_activate_without_manual_approval():
    with pytest.raises(MemoryLifecycleError):
        candidate.activate(actor="system")
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_memory_model.py -q`

Expected: FAIL because `creative_os.memory.model` does not exist.

- [ ] **Step 3: Implement immutable, validated memory types**

Use these exact enums and required fields:

```python
class MemoryKind(StrEnum):
    WORKING = "working"
    PROJECT_DECISION = "project_decision"
    USER_PREFERENCE = "user_preference"
    DOMAIN_METHOD = "domain_method"
    EXPERIENCE = "experience"


class MemoryScope(StrEnum):
    TASK = "task"
    PROJECT = "project"
    USER = "user"
    DOMAIN = "domain"
    GLOBAL = "global"


class MemoryStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    REJECTED = "rejected"
    ARCHIVED = "archived"
```

`MemoryItem` must contain `id`, `kind`, `scope`, `scope_id`, `title`, `content`, `applicability`, `exceptions`, `tags`, `evidence`, `status`, `confidence`, `version`, `created_at`, `updated_at` and `approved_by`。Only `actor != "system"` may promote `CANDIDATE -> ACTIVE`。

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m pytest tests/test_memory_model.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add creative_os/memory tests/test_memory_model.py
git commit -m "新增通用记忆数据模型"
```

### Task 2: Add Versioned JSON Memory Persistence

**Files:**
- Create: `creative_os/memory/store.py`
- Test: `tests/test_memory_store.py`
- Modify: `creative_os/novel_project.py`
- Modify: `tests/test_new_book_project_layout.py`

**Interfaces:**
- Consumes: `MemoryItem` from Task 1.
- Produces: `JsonMemoryStore(root: Path)`, `add_candidate()`, `get()`, `list()`, `save_revision()`, `archive()`。

- [ ] **Step 1: Write persistence and isolation tests**

```python
def test_store_round_trips_candidate_without_cross_project_leakage(tmp_path):
    first = JsonMemoryStore(tmp_path / "projects" / "甲" / ".creative_os" / "memory")
    second = JsonMemoryStore(tmp_path / "projects" / "乙" / ".creative_os" / "memory")
    first.add_candidate(candidate)
    assert first.get(candidate.id) == candidate
    assert second.list() == []


def test_revision_preserves_previous_version(tmp_path):
    store = JsonMemoryStore(tmp_path / "memory")
    store.add_candidate(candidate)
    revised = store.save_revision(candidate.id, content="修订内容", actor="user")
    assert revised.version == 2
    assert store.revisions(candidate.id)[0].version == 1
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_memory_store.py tests/test_new_book_project_layout.py -q`

Expected: FAIL because store and project memory directories are missing.

- [ ] **Step 3: Implement atomic JSON persistence**

Store records under:

```text
.creative_os/memory/items/<memory-id>.json
.creative_os/memory/revisions/<memory-id>/v0001.json
.creative_os/memory/audit.jsonl
```

Write to a sibling `.tmp` file and replace the destination. Reject duplicate IDs and invalid JSON. Extend new-project creation with the three memory directories without removing existing `.creative_os/knowledge`。

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m pytest tests/test_memory_store.py tests/test_new_book_project_layout.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add creative_os/memory/store.py creative_os/novel_project.py tests/test_memory_store.py tests/test_new_book_project_layout.py
git commit -m "实现版本化记忆持久化"
```

### Task 3: Extract Candidate Experiences Without Auto-Promotion

**Files:**
- Create: `creative_os/memory/candidates.py`
- Test: `tests/test_memory_candidates.py`

**Interfaces:**
- Consumes: task ID, domain, project ID, review issues, attempts, human feedback and source references.
- Produces: `CandidateExtractionInput`, `extract_candidates(input) -> list[MemoryItem]`。

- [ ] **Step 1: Write candidate extraction tests**

```python
def test_repeated_issue_creates_scoped_candidate_not_active_memory():
    result = extract_candidates(CandidateExtractionInput(
        task_id="chapter-004",
        project_id="文明升阶",
        domain="novel",
        issues=["time_word_opener", "time_word_opener"],
        attempts=2,
        human_feedback="章节开头不要总用时间词",
        source_ids=["review-004-a", "review-004-b"],
    ))
    assert result[0].status == MemoryStatus.CANDIDATE
    assert result[0].scope == MemoryScope.DOMAIN
    assert result[0].scope_id == "novel"
```

- [ ] **Step 2: Run test and verify failure**

Run: `python -m pytest tests/test_memory_candidates.py -q`

Expected: FAIL because extractor is missing.

- [ ] **Step 3: Implement deterministic candidate generation**

Group repeated normalized issue codes; attach every source ID as evidence. Human feedback may improve title and content, but extraction must never return `ACTIVE`. Deduplicate by `scope + scope_id + normalized content` hash.

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m pytest tests/test_memory_candidates.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add creative_os/memory/candidates.py tests/test_memory_candidates.py
git commit -m "新增候选经验提取器"
```

### Task 4: Implement Manual Approval and Audit Trail

**Files:**
- Create: `creative_os/memory/approval.py`
- Create: `scripts/memory_review.py`
- Test: `tests/test_memory_approval.py`
- Test: `tests/test_memory_review_script.py`

**Interfaces:**
- Consumes: `JsonMemoryStore` and candidate ID.
- Produces: `approve_candidate(store, id, actor, note)`, `reject_candidate(...)`, `archive_memory(...)` and CLI commands `list`, `show`, `approve`, `reject`, `archive`。

- [ ] **Step 1: Write approval and CLI tests**

```python
def test_human_approval_activates_candidate_and_records_actor(tmp_path):
    store = seeded_store(tmp_path)
    approved = approve_candidate(store, "exp-001", actor="tingyu", note="确认适用于长篇小说")
    assert approved.status == MemoryStatus.ACTIVE
    assert approved.approved_by == "tingyu"
    assert '"action": "approve"' in store.audit_path.read_text(encoding="utf-8")
```

CLI test must assert that `approve --actor system` exits non-zero and leaves the candidate unchanged.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_memory_approval.py tests/test_memory_review_script.py -q`

Expected: FAIL because approval module and script are missing.

- [ ] **Step 3: Implement approval service and CLI**

All transitions append `timestamp`, `action`, `memory_id`, `actor`, `from_status`, `to_status`, and `note` to `audit.jsonl`. Require a non-empty human actor and reject literal `system`.

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m pytest tests/test_memory_approval.py tests/test_memory_review_script.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add creative_os/memory/approval.py scripts/memory_review.py tests/test_memory_approval.py tests/test_memory_review_script.py
git commit -m "增加记忆人工审批流程"
```

### Task 5: Retrieve Active Memory by Scope and Applicability

**Files:**
- Create: `creative_os/memory/retriever.py`
- Test: `tests/test_memory_retriever.py`

**Interfaces:**
- Consumes: `MemoryQuery(task_id, project_id, user_id, domain, task_kind, tags)` and one or more stores.
- Produces: `MemoryRetrievalResult(items, reasons)` via `MemoryRetriever.retrieve(query, stores, limit=8)`。

- [ ] **Step 1: Write scope, status and ranking tests**

```python
def test_retriever_excludes_candidates_and_other_project_memory():
    result = MemoryRetriever().retrieve(query_for_project_a, [store], limit=8)
    assert [item.id for item in result.items] == ["user-style", "novel-method", "project-a-decision"]
    assert "candidate-rule" not in result.reasons
    assert "project-b-decision" not in result.reasons
```

- [ ] **Step 2: Run test and verify failure**

Run: `python -m pytest tests/test_memory_retriever.py -q`

Expected: FAIL because retriever is missing.

- [ ] **Step 3: Implement deterministic retrieval**

Filter to `ACTIVE`; enforce scope identity; reject task-kind mismatches in `applicability`; rank exact task tags, project scope, domain scope, user scope, then confidence and ID. Return explicit reasons such as `scope:project`, `tag:continuity`, `applicability:writing`。

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m pytest tests/test_memory_retriever.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add creative_os/memory/retriever.py tests/test_memory_retriever.py
git commit -m "实现分层记忆召回"
```

### Task 6: Compile Traceable Runtime Context

**Files:**
- Create: `creative_os/memory/context_compiler.py`
- Modify: `creative_os/engine/context.py`
- Test: `tests/test_context_compiler.py`
- Modify: `tests/test_context_model.py`

**Interfaces:**
- Consumes: existing `Task`, `ProjectState`, retrieved `KnowledgeItem`, `MemoryRetrievalResult`, domain rules and user input.
- Produces: `CompiledContext` with `working`, `knowledge`, `memory`, `rules`, `sources`, `size_chars`, `compiler_version`。

- [ ] **Step 1: Write budget and provenance tests**

```python
def test_compiler_keeps_required_project_facts_before_optional_experience():
    compiled = compiler.compile(request, max_chars=1200)
    assert compiled.knowledge[0].id == "required-character-state"
    assert all(source.source_id for source in compiled.sources)
    assert compiled.size_chars <= 1200


def test_compiler_output_is_reproducible_for_same_inputs():
    assert compiler.compile(request).fingerprint == compiler.compile(request).fingerprint
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_context_compiler.py tests/test_context_model.py -q`

Expected: FAIL because `CompiledContext` is missing.

- [ ] **Step 3: Implement priority-based compilation**

Use this order: current task constraints, required active project facts, current working memory, project decisions, user preferences, domain methods, cross-project experiences. Trim optional entries before required facts and emit a source record containing `source_type`, `source_id`, `reason`, `version` and content hash. Keep the existing `ContextBuilder` public behavior while delegating new compilation through an additive API.

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m pytest tests/test_context_compiler.py tests/test_context_model.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add creative_os/memory/context_compiler.py creative_os/engine/context.py tests/test_context_compiler.py tests/test_context_model.py
git commit -m "新增可追踪上下文编译器"
```

### Task 7: Record Memory Usage and Outcome

**Files:**
- Create: `creative_os/memory/evaluation.py`
- Test: `tests/test_memory_evaluation.py`
- Modify: `creative_os/llm_writer.py`
- Modify: `tests/test_llm_writer.py`

**Interfaces:**
- Consumes: run ID, task ID, compiled-context fingerprint, memory IDs, review issues before/after and human rating.
- Produces: `MemoryUsageRecord` JSONL and aggregate `MemoryEffect` reports; it must not automatically change memory status.

- [ ] **Step 1: Write usage recording tests**

```python
def test_usage_record_links_memory_to_review_outcome_without_auto_promotion(tmp_path):
    record_usage(log_path, usage)
    effects = summarize_effects(log_path)
    assert effects["exp-001"].uses == 1
    assert effects["exp-001"].issue_delta == -1
    assert store.get("exp-001").status == MemoryStatus.ACTIVE
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_memory_evaluation.py tests/test_llm_writer.py -q`

Expected: FAIL because evaluation logging is missing.

- [ ] **Step 3: Implement append-only evaluation records**

Write to `.creative_os/memory/usage.jsonl`. Integrate the writer additively: when a compiled context is supplied, save its fingerprint and memory IDs in the chapter run record; existing callers without memory continue to work.

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m pytest tests/test_memory_evaluation.py tests/test_llm_writer.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add creative_os/memory/evaluation.py creative_os/llm_writer.py tests/test_memory_evaluation.py tests/test_llm_writer.py
git commit -m "记录记忆命中与使用效果"
```

### Task 8: Document and Verify the Memory Kernel

**Files:**
- Create: `DOMAIN/Memory.md`
- Modify: `DOMAIN/Knowledge.md`
- Modify: `ENGINE/Context.md`
- Modify: `README.md`
- Test: `tests/test_docs_links.py`

**Interfaces:**
- Documents the boundary: Knowledge answers facts; Memory answers prior decisions, preferences and reusable methods; Context is disposable compiled input.

- [ ] **Step 1: Add documentation assertions**

Assert that README links to `DOMAIN/Memory.md`, and that the memory document contains `candidate`, `人工审批`, `作用域`, `来源追踪` and `效果评估`.

- [ ] **Step 2: Run documentation tests and verify failure**

Run: `python -m pytest tests/test_docs_links.py -q`

Expected: FAIL until the new documentation exists.

- [ ] **Step 3: Write boundary and operation documentation**

Include directory layout, lifecycle, CLI examples and migration note replacing the old statement “Memory 不作为独立长期层存在”。Do not claim vector retrieval or automatic promotion.

- [ ] **Step 4: Run complete verification**

```powershell
python -m pytest -q
python -m py_compile creative_os\memory\model.py creative_os\memory\store.py creative_os\memory\candidates.py creative_os\memory\approval.py creative_os\memory\retriever.py creative_os\memory\context_compiler.py creative_os\memory\evaluation.py scripts\memory_review.py
rg -n "Memory 不作为独立长期层存在|TODO|TBD" DOMAIN ENGINE creative_os\memory README.md
```

Expected: all tests pass, compilation succeeds, and no obsolete boundary or placeholder remains.

- [ ] **Step 5: Commit**

```bash
git add DOMAIN/Memory.md DOMAIN/Knowledge.md ENGINE/Context.md README.md tests/test_docs_links.py
git commit -m "完善系统记忆架构文档"
```

## Acceptance Gate

- 候选经验无法被 Retriever 召回。
- 只有人工审批可以激活经验。
- 不同项目的项目记忆不会串线。
- Context 超限时优先保留任务约束和项目事实。
- 每次记忆命中都能追踪来源、版本和召回原因。
- 记忆使用结果会被记录，但不会自动改变生命周期。
- 现有 V1 流水线和小说重写测试保持兼容。

