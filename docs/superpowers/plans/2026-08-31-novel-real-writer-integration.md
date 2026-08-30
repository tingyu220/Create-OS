# Novel Domain 真实 Writer 接入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将通用 OpenAI-Compatible Writer 接入 Novel Domain，并以独立短篇项目证明规划—准入—写作—审查—编译闭环不依赖具体作品。

**Architecture:** 用纯函数把 `NovelWritingRequest` 投影为稳定模型消息，用 `LLMNovelWriterAdapter` 适配现有 `ModelClient`，遥测通过可选观察端口输出。组合根负责真实客户端装配，独立验证运行器负责样本构造、闭环运行和脱敏报告，领域服务本身不增加文件或网络副作用。

**Tech Stack:** Python 3.12、dataclasses、typing.Protocol、现有 `ModelClient/OpenAICompatibleClient`、pytest。

**Spec:** `docs/superpowers/specs/2026-08-31-novel-real-writer-integration-design.md`

## Global Constraints

- 通用源码不得出现《文明升阶》《末班钟表店》或两部作品的人物、地点专名。
- Writer 不读取项目目录，不写 Draft、Canon、State、Task 或报告。
- Writer 必须验证 admission 的章节与上下文绑定，失败时关闭。
- 内容质量判断继续归 `NovelReviewer`，Writer 不复制重复、边界或一致性规则。
- 导入模块和 Fake Client 测试不得访问网络。
- 真实报告不得写入 API Key、Authorization Header 或完整模型响应对象。
- Writer 与独立样本验证完成前不得开发 Web UI。

---

### Task 1: 通用 Writer 消息投影

**Files:**
- Create: `creative_os/domains/novel_writer_prompt.py`
- Test: `tests/test_novel_writer_prompt.py`

**Interfaces:**
- Consumes: `NovelWritingRequest`、`ModelMessage`。
- Produces: `build_novel_writer_messages(request: NovelWritingRequest, system_instruction: str) -> list[ModelMessage]`。

- [ ] **Step 1: 写失败测试，固定消息结构与通用边界**

```python
def test_prompt_projects_approved_contract_without_work_specific_terms(chapter_contract):
    request = NovelWritingRequest("chapter_001", chapter_contract, "a" * 64, "保持克制的现实语气")
    messages = build_novel_writer_messages(request, "只输出小说正文")
    rendered = "\n".join(item.content for item in messages)
    assert [item.role for item in messages] == ["system", "user"]
    assert "戏剧问题" in rendered
    assert "必要信息" in rendered
    assert "闭合要求" in rendered
    assert "保持克制的现实语气" in rendered
    assert "文明升阶" not in rendered
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `pytest -q tests/test_novel_writer_prompt.py`

Expected: FAIL，错误包含 `ModuleNotFoundError: creative_os.domains.novel_writer_prompt`。

- [ ] **Step 3: 实现确定性纯函数投影**

```python
DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION = (
    "你是小说正文 Writer。严格依据已批准合同写作；只输出可发布正文；"
    "不得输出分析、提纲、代码块或系统术语；不得把未授权信息写成既成事实。"
)

def build_novel_writer_messages(request, system_instruction=DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION):
    request.chapter_contract.scene_plan.validate(required=True, novel_required=True)
    sections = _contract_sections(request)
    return [ModelMessage("system", system_instruction.strip()), ModelMessage("user", "\n\n".join(sections))]
```

`_contract_sections()` 必须按章节身份、章节功能、戏剧问题、主人公选择、读者变化、目标字数、场景、伏笔、禁止项、补充指令的固定顺序输出；场景逐项包含目的、目标、冲突、行动、必要信息、情绪变化和四项闭合布尔值。

- [ ] **Step 4: 补充空系统指令、空补充指令和 Scene 增强语义失败测试并运行**

Run: `pytest -q tests/test_novel_writer_prompt.py`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add creative_os/domains/novel_writer_prompt.py tests/test_novel_writer_prompt.py
git commit -m "feat: 增加通用小说 Writer 消息投影"
```

### Task 2: LLM Writer 适配器与遥测

**Files:**
- Create: `creative_os/domains/llm_novel_writer.py`
- Test: `tests/test_llm_novel_writer.py`

**Interfaces:**
- Consumes: `ModelClient.complete(messages, temperature, max_tokens)`、`NovelWritingRequest`、admission 对象。
- Produces: `NovelWriterConfig`、`NovelWriterTelemetry`、`NovelWriterObserver`、`LLMNovelWriterAdapter.write(...) -> NovelDraft`。

- [ ] **Step 1: 写失败测试覆盖字符串与 TimedCompletion 返回值**

```python
def test_adapter_returns_hashed_draft_and_emits_telemetry(request, admission):
    client = FakeClient(TimedCompletion("第一段。\n\n" + "正文" * 300, 1.25, LLMUsage(10, 20, 30)))
    observer = RecordingObserver()
    writer = LLMNovelWriterAdapter(client, observer=observer)
    draft = writer.write(request, admission)
    assert draft.content.startswith("第一段")
    assert len(draft.content_hash) == 64
    assert observer.items[0].elapsed_seconds == 1.25
    assert observer.items[0].total_tokens == 30
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `pytest -q tests/test_llm_novel_writer.py`

Expected: FAIL，错误包含 `ModuleNotFoundError: creative_os.domains.llm_novel_writer`。

- [ ] **Step 3: 实现不可变配置、遥测模型和观察端口**

```python
@dataclass(frozen=True, slots=True)
class NovelWriterConfig:
    temperature: float = 0.7
    max_tokens: int = 6000
    minimum_reviewable_chars: int = 500
    system_instruction: str = DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION

@dataclass(frozen=True, slots=True)
class NovelWriterTelemetry:
    chapter_id: str
    content_hash: str
    elapsed_seconds: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None

class NovelWriterObserver(Protocol):
    def record(self, telemetry: NovelWriterTelemetry) -> None: ...
```

- [ ] **Step 4: 实现 admission 绑定、模型调用和输出失败关闭**

`write()` 必须检查 `admission.chapter_id == request.chapter_id`、`admission.context_fingerprint == request.context_fingerprint`，并要求 `admission.contract_id` 非空。捕获模型异常后以 `NovelWritingError("novel_writer_model_failed")` 链接原异常；拒绝空文本、少于 `minimum_reviewable_chars`、以“分析：/提纲：”开头或被三反引号包裹的输出。

- [ ] **Step 5: 增加错误矩阵测试并运行**

```python
@pytest.mark.parametrize("mutation,code", [
    ("chapter", "novel_writer_chapter_binding_mismatch"),
    ("context", "novel_writer_context_binding_mismatch"),
    ("empty", "novel_draft_empty"),
    ("short", "novel_draft_below_reviewable_minimum"),
    ("analysis", "novel_draft_contains_model_scaffolding"),
])
def test_adapter_fails_closed(mutation, code, request, admission): ...
```

Run: `pytest -q tests/test_llm_novel_writer.py tests/test_novel_writer_prompt.py`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add creative_os/domains/llm_novel_writer.py tests/test_llm_novel_writer.py
git commit -m "feat: 接入通用 LLM 小说 Writer 适配器"
```

### Task 3: 真实客户端组合入口

**Files:**
- Modify: `creative_os/domains/novel_domain_composition.py`
- Test: `tests/test_novel_domain_composition.py`

**Interfaces:**
- Consumes: `ModelClient` 或 `OpenAICompatibleClient.from_env()`。
- Produces: `build_llm_novel_domain_service(project_root, *, baseline_resolver, client, writer_config=None, observer=None)` 与 `build_env_novel_domain_service(project_root, *, baseline_resolver, env_file='.env', writer_config=None, observer=None)`。

- [ ] **Step 1: 写失败测试，证明 Client 注入和延迟环境读取**

```python
def test_build_llm_service_wraps_injected_client(tmp_path):
    service = build_llm_novel_domain_service(tmp_path, baseline_resolver=_Resolver(), client=_Client())
    assert service.capabilities().names[2] == "draft_writing"

def test_importing_composition_does_not_read_environment(monkeypatch):
    monkeypatch.setattr(OpenAICompatibleClient, "from_env", lambda *_: (_ for _ in ()).throw(AssertionError()))
    importlib.reload(novel_domain_composition)
```

- [ ] **Step 2: 运行测试并确认新函数不存在**

Run: `pytest -q tests/test_novel_domain_composition.py`

Expected: FAIL，错误包含 `cannot import name 'build_llm_novel_domain_service'`。

- [ ] **Step 3: 实现两个薄组合函数**

`build_llm_novel_domain_service()` 只创建 `LLMNovelWriterAdapter` 后调用现有 `build_novel_domain_service()`；`build_env_novel_domain_service()` 只在函数调用时执行 `OpenAICompatibleClient.from_env(env_file)`。

- [ ] **Step 4: 运行组合测试**

Run: `pytest -q tests/test_novel_domain_composition.py tests/test_llm_writer.py`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add creative_os/domains/novel_domain_composition.py tests/test_novel_domain_composition.py
git commit -m "feat: 增加真实小说 Writer 组合入口"
```

### Task 4: 独立短篇样本夹具

**Files:**
- Create: `projects/novel_domain_validation/project.json`
- Create: `projects/novel_domain_validation/brief.json`
- Create: `projects/novel_domain_validation/validation/independent_short_story.json`
- Create: `creative_os/domains/novel_validation_fixture.py`
- Test: `tests/test_novel_validation_fixture.py`

**Interfaces:**
- Produces: `load_independent_validation_case(path: str | Path) -> IndependentNovelValidationCase`；该对象包含规划、写作、边界、角色变化和确定性 Fake 正文所需的全部数据。

- [ ] **Step 1: 写失败测试，确保样本与既有作品隔离**

```python
def test_independent_fixture_has_complete_novel_scene_contract():
    case = load_independent_validation_case(PROJECT / "validation/independent_short_story.json")
    case.chapter_contract.scene_plan.validate(required=True, novel_required=True)
    payload = (PROJECT / "validation/independent_short_story.json").read_text(encoding="utf-8")
    for forbidden in ("文明升阶", "林子轩", "陈景行"):
        assert forbidden not in payload
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `pytest -q tests/test_novel_validation_fixture.py`

Expected: FAIL，fixture loader 不存在。

- [ ] **Step 3: 实现严格 JSON loader 与《末班钟表店》单章数据**

`project.json` 和 `brief.json` 明确该目录是独立小说验证项目；验证 JSON 必须包含最小 Profile、Chapter Contract、当前 State、基线证据和确定性 Fake 正文。Loader 必须拒绝未知根字段、缺少章节身份、空场景、未完成闭合、正文哈希不一致和低于边界最小字数。样本正文不得包含系统术语，并必须逐字包含每项 `essential_information`，以便统一 Reviewer 可以真实验证。

- [ ] **Step 4: 运行夹具测试**

Run: `pytest -q tests/test_novel_validation_fixture.py tests/test_novel_scene_contract.py`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add creative_os/domains/novel_validation_fixture.py projects/novel_domain_validation tests/test_novel_validation_fixture.py
git commit -m "test: 增加独立短篇小说验证夹具"
```

### Task 5: 独立样本端到端验收运行器

**Files:**
- Create: `creative_os/novel_writer_validation.py`
- Create: `scripts/validate_novel_real_writer.py`
- Test: `tests/test_novel_writer_validation.py`
- Test: `tests/test_validate_novel_real_writer_script.py`

**Interfaces:**
- Produces: `run_independent_writer_validation(case, client, *, mode: str) -> NovelWriterValidationReport`。
- CLI: `python scripts/validate_novel_real_writer.py --fixture <path> --mode fake|live --report <path> [--env-file <path>]`。

- [ ] **Step 1: 写 Fake Client 闭环失败测试**

```python
def test_fake_validation_reaches_compile_candidate(case):
    report = run_independent_writer_validation(case, FakeClient(case.fake_draft), mode="fake")
    assert report.stage == "compile_candidate_ready"
    assert report.review_passed is True
    assert report.canon_patch_count > 0
    assert report.contains_secret_fields is False
```

- [ ] **Step 2: 运行测试并确认运行器不存在**

Run: `pytest -q tests/test_novel_writer_validation.py`

Expected: FAIL，错误包含 `ModuleNotFoundError: creative_os.novel_writer_validation`。

- [ ] **Step 3: 实现内存验收组合与脱敏报告**

运行器用真实 `NovelChapterPlanner`、`LLMNovelWriterAdapter`、`NovelReviewer`、`NovelCompiler` 和 `NovelDomainService.run_chapter()`。样本 admission 端口必须返回具备 `chapter_id/contract_id/context_fingerprint` 的验证令牌；正式 `WriterAdmissionService` 的权威记录链由现有测试继续覆盖，运行器不得伪装该令牌已通过持久化审批。

报告字段固定为：`mode`、`provider_kind`、`model`、`chapter_id`、`stage`、`review_passed`、`blocking_codes`、`content_hash`、`elapsed_seconds`、三项 Token 数、`canon_patch_count`、`state_candidate_count`。不得序列化 Client 或环境字典。

- [ ] **Step 4: 实现 CLI 的 fake/live 分支**

Fake 模式使用 fixture 正文且不读取 `.env`；live 模式调用 `OpenAICompatibleClient.from_env()`，缺配置时以退出码 2 和 `live_writer_configuration_missing` 失败。报告使用 UTF-8 JSON 原子替换写入指定路径。

- [ ] **Step 5: 运行端到端与 CLI 测试**

Run: `pytest -q tests/test_novel_writer_validation.py tests/test_validate_novel_real_writer_script.py tests/test_novel_domain_end_to_end.py`

Expected: PASS；Fake 报告达到 `compile_candidate_ready`，live 缺配置测试退出码为 2。

- [ ] **Step 6: 提交**

```bash
git add creative_os/novel_writer_validation.py scripts/validate_novel_real_writer.py tests/test_novel_writer_validation.py tests/test_validate_novel_real_writer_script.py
git commit -m "feat: 增加独立小说 Writer 端到端验收"
```

### Task 6: 完成回归、硬编码审计与真实验收门禁

**Files:**
- Create when live configuration exists: `projects/novel_domain_validation/production/reports/real_writer_validation.json`
- Modify: `docs/novel-production-roadmap.md`

**Interfaces:**
- Consumes: Task 5 CLI。
- Produces: 可审计的 Fake/Live 验收证据和下一阶段准入状态。

- [ ] **Step 1: 运行 Fake 独立验收**

Run:

```powershell
python scripts/validate_novel_real_writer.py --fixture projects/novel_domain_validation/validation/independent_short_story.json --mode fake --report projects/novel_domain_validation/production/reports/fake_writer_validation.json
```

Expected: 退出码 0；报告 `stage=compile_candidate_ready`、`review_passed=true`。

- [ ] **Step 2: 扫描通用源码的作品专名**

Run:

```powershell
rg -n "文明升阶|林子轩|陈景行|末班钟表店" creative_os
```

Expected: 无输出，退出码 1。

- [ ] **Step 3: 检查 live 配置并执行真实验收**

若 `CREATIVE_OS_LLM_API_KEY`、`CREATIVE_OS_LLM_MODEL` 缺失，记录 `live_validation=blocked_missing_configuration`，保持本阶段未完成并请求用户配置；不得用 Fake 结果冒充真实验收。

配置存在时运行：

```powershell
python scripts/validate_novel_real_writer.py --fixture projects/novel_domain_validation/validation/independent_short_story.json --mode live --report projects/novel_domain_validation/production/reports/real_writer_validation.json --env-file .env
```

Expected: 退出码 0，报告无 `api_key`、`authorization` 字段且达到 `compile_candidate_ready`。

- [ ] **Step 4: 更新路线图的真实状态**

只有 live 报告通过时，才能把“真实 Writer 接入”和“独立小说验证”标为完成，并开放可视化数据投影层设计；配置缺失或内容审查失败时，路线图明确记录阻塞原因。

- [ ] **Step 5: 运行全量测试且不产生缓存**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; pytest -q -p no:cacheprovider
```

Expected: 全部通过，仅保留已有显式 skip。

- [ ] **Step 6: 提交验收证据与路线图**

```bash
git add projects/novel_domain_validation docs/novel-production-roadmap.md
git commit -m "test: 完成真实 Writer 独立小说验收"
```

不得提交 `.env`、API Key、响应 Header 或未脱敏模型原始响应。
