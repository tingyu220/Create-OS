# ProjectSnapshot Projection Layer Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为单个小说项目生成严格一致、确定性、可追溯的 `ProjectSnapshot`，首批覆盖 Overview、Chapter Matrix、Quality、Runtime/Trace，并让现有文本控制台只消费该快照。

**Architecture:** 项目范围 Source Adapter 读取 Domain、Knowledge、Runtime 的权威事实，纯 Section Projector 生成不可变读模型，`ProjectProjectionBuilder` 在构建前后校验来源头并原子发布完整快照。消费者只依赖 `ProjectSnapshot`；第一版执行全量构建，但请求、游标和 Projector 接口为后续增量刷新保留兼容入口。

**Tech Stack:** Python 3.11+、标准库 `dataclasses/enum/hashlib/json/pathlib`、pytest、现有 `AppendOnlyEventLog` 与 Novel Domain 文件存储。

**Spec:** `docs/superpowers/specs/2026-09-01-project-snapshot-projection-layer-design.md`

## Global Constraints

- 第一版只服务一个明确 `project_id` 对应的小说项目，不实现 `PortfolioProjection`。
- Domain、Knowledge、Runtime 是唯一真实数据源；Projection 不得调用领域写入、审批或状态迁移接口，未来写操作只能走 `Command → Domain → Event → Projection Refresh`。
- 关键状态必须携带 `SourceRef` 或 `Derivation`，未知不得伪装为空。
- 构建采用严格一致切面；来源漂移时丢弃结果并有限重试。
- 第一版允许全量扫描，但公开接口不得绑定全量模式。
- 不开发 Web UI；现有控制台只能成为 `ProjectSnapshot` 的薄消费者。
- Windows 验证命令使用动态解析的 PowerShell 7+；提交前必须获得用户明确授权，Commit Message 使用中文。

---

## 文件结构

```text
creative_os/projection/
  __init__.py                 # 只导出稳定公共契约
  provenance.py               # SourceRef、SourceHead、Derivation
  model.py                    # 顶层状态、诊断、ProjectSnapshot
  chapters.py                 # Chapter Matrix 读模型
  quality.py                  # Review/Gate/Issue 读模型
  trace.py                    # Runtime/Trace 读模型
  overview.py                 # Overview 读模型
  source.py                   # ProjectSource、ProjectSourceSet、原始事实包
  filesystem_source.py        # 当前文件与 Event Log 的只读适配器
  builder.py                  # 一致性重试和 section 编排
  codec.py                    # 确定性 JSON 编解码
  projectors/
    chapters.py               # 章节阶段投影
    quality.py                # 质量投影
    trace.py                  # 运行轨迹投影
    overview.py               # 汇总投影
tests/projection/
  test_provenance.py
  test_model.py
  test_filesystem_source.py
  test_chapter_projector.py
  test_quality_projector.py
  test_trace_projector.py
  test_overview_projector.py
  test_builder.py
  test_codec.py
tests/test_console_dashboard.py
```

每个 section 模型与 projector 分离，避免 `model.py` 和 `builder.py` 演变为高耦合大文件。

### Task 1: 来源追溯与不可变快照模型

**Files:**
- Create: `creative_os/projection/__init__.py`
- Create: `creative_os/projection/provenance.py`
- Create: `creative_os/projection/model.py`
- Create: `creative_os/projection/chapters.py`
- Create: `creative_os/projection/quality.py`
- Create: `creative_os/projection/trace.py`
- Create: `creative_os/projection/overview.py`
- Test: `tests/projection/test_provenance.py`
- Test: `tests/projection/test_model.py`

**Interfaces:**
- Produces: `SourceRef`, `SourceHead`, `Derivation`, `ProjectionDiagnostic`, `ProjectSnapshot` 以及四个 section 的冻结值对象。
- Consumes: 无。

- [ ] **Step 1: 写来源引用和确定性模型的失败测试**

```python
def test_source_ref_rejects_absolute_locator() -> None:
    with pytest.raises(ValueError, match="source_locator_must_be_project_relative"):
        SourceRef("chapter_status", "chapter-029", r"D:\\book\\status.json", "a" * 64)


def test_project_snapshot_id_is_independent_of_built_at() -> None:
    first = make_snapshot(built_at="2026-09-01T00:00:00+00:00")
    second = make_snapshot(built_at="2026-09-01T00:01:00+00:00")
    assert first.snapshot_id == second.snapshot_id
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `pytest tests/projection/test_provenance.py tests/projection/test_model.py -q`

Expected: FAIL，错误包含 `No module named 'creative_os.projection'`。

- [ ] **Step 3: 实现冻结模型及精确校验**

```python
@dataclass(frozen=True, slots=True)
class SourceRef:
    source_kind: str
    source_id: str
    locator: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class Derivation:
    rule_id: str
    inputs: tuple[SourceRef, ...]
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    schema_version: int
    snapshot_id: str
    project_id: str
    built_at: str
    source_heads: tuple[SourceHead, ...]
    overview: OverviewSnapshot
    chapters: tuple[ChapterSnapshot, ...]
    quality: QualitySnapshot
    trace: TraceSnapshot
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()
```

`snapshot_id` 由规范化后的 `schema_version + project_id + source_heads + sections + diagnostics` 计算，不包含 `built_at`。集合字段全部使用 tuple，状态全部使用 `StrEnum`，`unknown` 与空集合保持不同语义。

- [ ] **Step 4: 运行模型测试**

Run: `pytest tests/projection/test_provenance.py tests/projection/test_model.py -q`

Expected: PASS。

- [ ] **Step 5: 请求提交授权后提交本任务**

```bash
git add creative_os/projection tests/projection/test_provenance.py tests/projection/test_model.py
git commit -m "新增只读投影基础模型"
```

### Task 2: 项目范围 Source Adapter 与来源头

**Files:**
- Create: `creative_os/projection/source.py`
- Create: `creative_os/projection/filesystem_source.py`
- Test: `tests/projection/test_filesystem_source.py`

**Interfaces:**
- Consumes: `SourceRef`、`SourceHead`。
- Produces: `ProjectFacts`, `ProjectSource.read_head()`, `ProjectSource.read_facts()`, `FilesystemProjectSource`。

- [ ] **Step 1: 写项目隔离、缺失语义和 Event Log 头测试**

```python
def test_source_uses_explicit_project_identity(tmp_path: Path) -> None:
    project = make_project(tmp_path / "book-a", project_id="book-a")
    facts = FilesystemProjectSource(project).read_facts()
    assert facts.project_id == "book-a"
    assert all("book-b" not in ref.locator for ref in facts.source_refs)


def test_event_head_uses_last_sequence_and_event_id(tmp_path: Path) -> None:
    project = make_project_with_events(tmp_path, sequences=(1, 2))
    head = FilesystemProjectSource(project).read_head()
    assert head.parts["event_log"] == "2:event-2"
```

- [ ] **Step 2: 运行单测确认失败**

Run: `pytest tests/projection/test_filesystem_source.py -q`

Expected: FAIL，错误指向尚未实现的 `FilesystemProjectSource`。

- [ ] **Step 3: 实现只读事实包和适配器**

```python
class ProjectSource(Protocol):
    def read_head(self) -> SourceHead: ...
    def read_facts(self, cursor: ProjectionCursor | None = None) -> ProjectFacts: ...


@dataclass(frozen=True, slots=True)
class ProjectFacts:
    project_id: str
    chapter_statuses: tuple[ChapterStatusFact, ...]
    quality_records: tuple[QualityFact, ...]
    execution_events: tuple[ExecutionEventFact, ...]
    diagnostics: tuple[ProjectionDiagnostic, ...]
    source_refs: tuple[SourceRef, ...]
```

适配器只读取项目根内的状态、审查、Gate、运行记录和 Event Log。旧章节状态格式在适配器内转换并标记 `legacy`；路径定位统一转换为项目相对 POSIX 路径。无权威来源时产出 `source_missing` 诊断，不生成“零问题”事实。

- [ ] **Step 4: 运行适配器测试及现有事件日志测试**

Run: `pytest tests/projection/test_filesystem_source.py tests/test_runtime.py tests/test_task_status.py -q`

Expected: PASS。

- [ ] **Step 5: 请求提交授权后提交本任务**

```bash
git add creative_os/projection/source.py creative_os/projection/filesystem_source.py tests/projection/test_filesystem_source.py
git commit -m "新增项目投影只读数据源"
```

### Task 3: Chapter Matrix、Quality 与 Trace 纯投影器

**Files:**
- Create: `creative_os/projection/projectors/__init__.py`
- Create: `creative_os/projection/projectors/chapters.py`
- Create: `creative_os/projection/projectors/quality.py`
- Create: `creative_os/projection/projectors/trace.py`
- Test: `tests/projection/test_chapter_projector.py`
- Test: `tests/projection/test_quality_projector.py`
- Test: `tests/projection/test_trace_projector.py`

**Interfaces:**
- Consumes: `ProjectFacts` 与可选上一 section、可选 `ProjectionChangeSet`。
- Produces: `project_chapters(...)`, `project_quality(...)`, `project_trace(...)`。

- [ ] **Step 1: 写阶段、阻塞依据、Issue 保真和 Trace 排序测试**

```python
def test_failed_chapter_keeps_blocking_derivation() -> None:
    chapter = project_chapters(facts_with_failed_gate())[0]
    assert chapter.status is ChapterStatus.BLOCKED
    assert chapter.blocked_by[0].rule_id == "chapter.blocked_by_gate"
    assert chapter.blocked_by[0].inputs[0].source_id == "gate-029"


def test_quality_does_not_promote_warning() -> None:
    quality = project_quality(facts_with_warning())
    assert quality.issues[0].severity == "warning"
    assert quality.blocking_count == 0


def test_trace_is_ordered_by_event_sequence() -> None:
    trace = project_trace(facts_with_events(3, 1, 2))
    assert [entry.sequence for entry in trace.entries] == [1, 2, 3]
```

- [ ] **Step 2: 运行三个 projector 测试确认失败**

Run: `pytest tests/projection/test_chapter_projector.py tests/projection/test_quality_projector.py tests/projection/test_trace_projector.py -q`

Expected: FAIL，缺少三个公开函数。

- [ ] **Step 3: 实现纯函数及稳定排序**

```python
def project_chapters(
    facts: ProjectFacts,
    previous: tuple[ChapterSnapshot, ...] | None = None,
    changes: ProjectionChangeSet | None = None,
) -> tuple[ChapterSnapshot, ...]: ...


def project_quality(
    facts: ProjectFacts,
    previous: QualitySnapshot | None = None,
    changes: ProjectionChangeSet | None = None,
) -> QualitySnapshot: ...


def project_trace(
    facts: ProjectFacts,
    previous: TraceSnapshot | None = None,
    changes: ProjectionChangeSet | None = None,
) -> TraceSnapshot: ...
```

章节阶段只由明确状态、Gate、Review、Compiler 或事件事实推进。`failed`、`blocked`、`unknown` 分开；Quality 保留原始 code、severity、blocking 和来源；Trace 按 sequence 排序，去除凭据、完整提示词和模型正文。

- [ ] **Step 4: 运行 projector 测试**

Run: `pytest tests/projection/test_chapter_projector.py tests/projection/test_quality_projector.py tests/projection/test_trace_projector.py -q`

Expected: PASS。

- [ ] **Step 5: 请求提交授权后提交本任务**

```bash
git add creative_os/projection/projectors tests/projection/test_chapter_projector.py tests/projection/test_quality_projector.py tests/projection/test_trace_projector.py
git commit -m "实现章节质量与运行轨迹投影"
```

### Task 4: Overview 与严格一致 Builder

**Files:**
- Create: `creative_os/projection/projectors/overview.py`
- Create: `creative_os/projection/builder.py`
- Test: `tests/projection/test_overview_projector.py`
- Test: `tests/projection/test_builder.py`

**Interfaces:**
- Consumes: `ProjectSource`、三个基础 section projector。
- Produces: `ProjectProjectionRequest`, `ProjectionCursor`, `ProjectionBuildResult`, `ProjectProjectionBuilder.build()`。

- [ ] **Step 1: 写 Overview 汇总和来源漂移重试测试**

```python
def test_overview_reports_current_blocker_without_inventing_fact() -> None:
    overview = project_overview(chapters=blocked_chapters(), quality=quality(), trace=trace())
    assert overview.blocked_chapter_count == 1
    assert overview.blockers[0].derivation.inputs


def test_builder_discards_snapshot_when_source_head_drifts() -> None:
    source = DriftingSource(heads=(head("1"), head("2"), head("2"), head("2")))
    result = ProjectProjectionBuilder(source, max_attempts=2).build(request("book-a"))
    assert result.attempts == 2
    assert result.snapshot.source_heads == (head("2"),)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/projection/test_overview_projector.py tests/projection/test_builder.py -q`

Expected: FAIL，Builder 尚不存在。

- [ ] **Step 3: 实现 Overview 与双读来源头构建流程**

```python
@dataclass(frozen=True, slots=True)
class ProjectProjectionRequest:
    project_id: str
    previous_cursor: ProjectionCursor | None = None
    requested_sections: tuple[str, ...] = ("overview", "chapters", "quality", "trace")


class ProjectProjectionBuilder:
    def build(self, request: ProjectProjectionRequest) -> ProjectionBuildResult:
        for attempt in range(1, self.max_attempts + 1):
            before = self.source.read_head()
            facts = self.source.read_facts(request.previous_cursor)
            sections = self._project(facts, request)
            after = self.source.read_head()
            if before == after:
                return self._result(request, after, sections, attempt)
        raise ProjectionConsistencyError("projection_source_drift")
```

Overview 只能从已生成 section 和明确运行事实汇总；Builder 校验 `facts.project_id == request.project_id`。任何尝试失败均不得暴露半成品快照。

- [ ] **Step 4: 运行 Builder 测试**

Run: `pytest tests/projection/test_overview_projector.py tests/projection/test_builder.py -q`

Expected: PASS。

- [ ] **Step 5: 请求提交授权后提交本任务**

```bash
git add creative_os/projection/projectors/overview.py creative_os/projection/builder.py tests/projection/test_overview_projector.py tests/projection/test_builder.py
git commit -m "实现严格一致项目快照构建"
```

### Task 5: 确定性 Codec 与只读缓存边界

**Files:**
- Create: `creative_os/projection/codec.py`
- Test: `tests/projection/test_codec.py`

**Interfaces:**
- Consumes: `ProjectSnapshot`。
- Produces: `encode_project_snapshot(snapshot) -> str`、`decode_project_snapshot(payload) -> ProjectSnapshot`。

- [ ] **Step 1: 写往返、稳定输出和路径安全测试**

```python
def test_snapshot_codec_is_deterministic() -> None:
    snapshot = make_snapshot()
    assert encode_project_snapshot(snapshot) == encode_project_snapshot(snapshot)
    assert decode_project_snapshot(encode_project_snapshot(snapshot)) == snapshot


def test_snapshot_payload_has_no_absolute_paths() -> None:
    payload = encode_project_snapshot(make_snapshot())
    assert r"D:\\" not in payload
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/projection/test_codec.py -q`

Expected: FAIL，Codec 尚不存在。

- [ ] **Step 3: 实现显式 schema 编解码**

```python
def encode_project_snapshot(snapshot: ProjectSnapshot) -> str:
    payload = _encode_snapshot(snapshot)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def decode_project_snapshot(payload: str) -> ProjectSnapshot:
    raw = json.loads(payload)
    if raw.get("schema_version") != PROJECT_SNAPSHOT_SCHEMA_VERSION:
        raise ProjectionCodecError("project_snapshot_schema_unsupported")
    return _decode_snapshot(raw)
```

禁止使用 pickle 或隐式 `asdict()` 作为长期协议；每个字段显式编码，未知字段和非法枚举失败关闭。缓存写入不在此任务实现，避免把 Codec 与文件系统耦合。

- [ ] **Step 4: 运行 Codec 与全部 projection 测试**

Run: `pytest tests/projection -q`

Expected: PASS。

- [ ] **Step 5: 请求提交授权后提交本任务**

```bash
git add creative_os/projection/codec.py tests/projection/test_codec.py
git commit -m "新增项目快照确定性编解码"
```

### Task 6: 将文本控制台降为薄消费者

**Files:**
- Modify: `creative_os/console_dashboard.py`
- Modify: `tests/test_console_dashboard.py`

**Interfaces:**
- Consumes: `ProjectSnapshot`。
- Produces: `render_console_dashboard(snapshot: ProjectSnapshot) -> str`。

- [ ] **Step 1: 修改测试，禁止控制台直接读取项目文件**

```python
def test_dashboard_renders_projection_without_project_access(monkeypatch) -> None:
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: pytest.fail("控制台不得读取文件"))
    output = render_console_dashboard(make_snapshot())
    assert "当前阶段" in output
    assert "chapter_029 blocked" in output
    assert "gate-029" in output
```

- [ ] **Step 2: 运行控制台测试确认旧接口失败**

Run: `pytest tests/test_console_dashboard.py -q`

Expected: FAIL，因为旧控制台仍接收 `project_root` 并调用 `load_chapter_statuses()`。

- [ ] **Step 3: 把控制台改为纯格式化器**

```python
def render_console_dashboard(snapshot: ProjectSnapshot) -> str:
    lines = [f"项目：{snapshot.project_id}", f"当前阶段：{snapshot.overview.current_stage}"]
    lines.extend(_render_chapter(item) for item in snapshot.chapters)
    lines.extend(_render_quality(snapshot.quality))
    lines.extend(_render_trace(snapshot.trace))
    return "\n".join(lines)
```

若需要兼容 CLI，由组合根先构建 snapshot 再调用 renderer；不得在 renderer 中保留项目路径兼容分支。

- [ ] **Step 4: 运行控制台与 projection 测试**

Run: `pytest tests/test_console_dashboard.py tests/projection -q`

Expected: PASS。

- [ ] **Step 5: 请求提交授权后提交本任务**

```bash
git add creative_os/console_dashboard.py tests/test_console_dashboard.py
git commit -m "改造控制台为项目快照消费者"
```

### Task 7: 真实项目验收与全量回归

**Files:**
- Create: `tests/projection/test_real_project_projection.py`
- Modify: `docs/novel-production-roadmap.md`

**Interfaces:**
- Consumes: 完整 Phase 1 投影 API。
- Produces: 可重复的单项目验收测试和路线图状态证据。

- [ ] **Step 1: 写真实夹具验收测试**

```python
def test_novel_validation_project_builds_traceable_snapshot(repo_root: Path) -> None:
    project = repo_root / "projects" / "novel_domain_validation"
    result = ProjectProjectionBuilder(FilesystemProjectSource(project)).build(
        ProjectProjectionRequest(project_id="novel_domain_validation")
    )
    assert result.snapshot.overview.current_stage
    assert result.snapshot.chapters
    assert all(item.source_refs or item.derivations for item in result.snapshot.chapters)
    assert result.snapshot.trace.entries
```

- [ ] **Step 2: 运行真实项目验收并修正数据源映射错误**

Run: `pytest tests/projection/test_real_project_projection.py -q`

Expected: PASS；不得通过在测试中伪造项目状态绕过真实文件。

- [ ] **Step 3: 运行架构边界检查**

Run: `rg -n "append\(|save\(|write_|approve|transition" creative_os/projection`

Expected: 只允许出现只读协议说明或 Codec 名称，不得出现领域写调用。随后运行 `rg -n "creative_os\.(domains|runtime)|load_chapter_statuses" creative_os/console_dashboard.py`，Expected: 无匹配。

- [ ] **Step 4: 运行全量测试**

Run: `pytest -q`

Expected: 全部通过；既有真实 Writer 验收和 Novel Domain 测试无回归。

- [ ] **Step 5: 更新路线图的可验证状态**

在 `docs/novel-production-roadmap.md` 记录 Phase 1 已实现范围、真实验收命令、明确未实现的 Characters/Story Threads/Timeline 与 Web UI，禁止使用“全部可视化已完成”的表述。

- [ ] **Step 6: 请求最终提交与推送授权**

```bash
git add creative_os tests docs/novel-production-roadmap.md docs/superpowers/specs/2026-09-01-project-snapshot-projection-layer-design.md docs/superpowers/plans/2026-09-01-project-snapshot-projection-phase-1.md
git commit -m "完成小说项目第一阶段只读投影"
```

推送只能在用户再次明确授权后使用 Git Bash 执行。

## 第二阶段入口条件

Phase 1 全量测试、真实项目快照和消费者边界全部通过后，再为以下能力单独编写计划：

- Characters：已批准角色状态与候选状态分层；
- Story Threads：Foreshadow、Expectation、Open Loop 聚合但保留原始类型；
- Timeline：只投影结构化时间事实和冲突，不从正文臆测；
- Event Log 项目身份升级与真正增量刷新；
- Projection 接口稳定后才评估 Web UI。
