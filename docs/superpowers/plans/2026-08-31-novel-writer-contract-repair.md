# 小说 Writer 合同修复重试 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为真实小说 Writer 增加最多一次、可审计且失败关闭的必要信息修复重试，并重新通过独立短篇 Live 闭环验收。

**Architecture:** 将修复提示词投影放入独立纯函数模块，`LLMNovelWriterAdapter` 只负责编排首次生成、精确缺失检测和一次重写。两次模型调用均经过 `RuntimeRunner`，遥测聚合但不持久化原始正文；最终 Reviewer 标准保持不变。

**Tech Stack:** Python 3.12、dataclasses、现有 `RuntimeRunner` / `ModelMessage` / Novel Domain、pytest。

**Spec:** `docs/superpowers/specs/2026-08-31-novel-writer-contract-repair-design.md`

## Global Constraints

- 合同修复最多一次；不得无限重试。
- 不自动拼接句子，不放松 Reviewer，不引入语义相似判断。
- 每次模型调用必须经过 `RuntimeRunner.execute`，不得直接调用 Client。
- 不持久化或报告原始模型正文、Prompt、Client、环境字典、密钥、Header。
- 不加入作品专名或供应商特化业务逻辑。
- Live 验收通过前不得开始投影层或 Web UI。
- 代码注释使用中文；变量名和函数名使用英文。

---

### Task 1: 通用合同修复消息投影

**Files:**
- Create: `creative_os/domains/novel_writer_repair_prompt.py`
- Test: `tests/test_novel_writer_repair_prompt.py`

**Interfaces:**
- Consumes: `NovelWritingRequest`、首次正文 `str`、缺失信息 `tuple[str, ...]`、系统指令 `str`。
- Produces: `build_novel_writer_repair_messages(request, draft, missing_information, system_instruction) -> list[ModelMessage]`。

- [ ] **Step 1: 写失败测试，锁定完整重写与数据边界**

```python
def test_repair_messages_request_complete_rewrite_without_story_hardcoding(writing_request):
    messages = build_novel_writer_repair_messages(
        writing_request,
        "已有正文",
        ("事实甲", "事实乙"),
        DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION,
    )
    assert [item.role for item in messages] == ["system", "user"]
    assert "已有正文" in messages[1].content
    assert "事实甲" in messages[1].content and "事实乙" in messages[1].content
    assert "完整重写" in messages[1].content
    assert "逐字" in messages[1].content
    assert "只输出可发布正文" in messages[0].content
```

- [ ] **Step 2: 运行红测**

Run: `pytest -q tests/test_novel_writer_repair_prompt.py`

Expected: FAIL，模块 `creative_os.domains.novel_writer_repair_prompt` 不存在。

- [ ] **Step 3: 实现纯消息投影函数**

```python
def build_novel_writer_repair_messages(
    request: NovelWritingRequest,
    draft: str,
    missing_information: tuple[str, ...],
    system_instruction: str = DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION,
) -> list[ModelMessage]:
    if not draft.strip() or not missing_information:
        raise ValueError("novel_writer_repair_input_invalid")
    missing = "\n".join(f"- {item}" for item in missing_information)
    user = (
        "请完整重写下列小说正文，只输出可发布正文。"
        "缺失信息必须逐字写入自然叙事，不得同义改写、概括或转述。\n"
        f"章节身份：{request.chapter_id}\n缺失信息：\n{missing}\n原正文：\n{draft}"
    )
    return [ModelMessage("system", system_instruction.strip()), ModelMessage("user", user)]
```

- [ ] **Step 4: 补输入校验和秘密边界测试并运行**

Run: `pytest -q tests/test_novel_writer_repair_prompt.py tests/test_novel_writer_prompt.py`

Expected: PASS；消息不包含 Client、环境或具体作品常量。

- [ ] **Step 5: 提交**

```bash
git add creative_os/domains/novel_writer_repair_prompt.py tests/test_novel_writer_repair_prompt.py
git commit -m "feat: 增加小说合同修复消息投影"
```

### Task 2: Writer 有限重试与聚合遥测

**Files:**
- Modify: `creative_os/domains/llm_novel_writer.py`
- Modify: `tests/test_llm_novel_writer.py`
- Modify: `tests/test_novel_writer_validation.py`

**Interfaces:**
- Consumes: Task 1 的 `build_novel_writer_repair_messages(request, draft, missing_information, system_instruction)`。
- Produces: `NovelWriterConfig.max_contract_repairs: int = 1`；`LLMNovelWriterAdapter.write(request, admission)` 最多两次 Runtime 调用；现有 `NovelWriterTelemetry` 字段保持不变并聚合尝试。

- [ ] **Step 1: 写无缺失、修复成功、修复耗尽三组失败测试**

```python
def test_adapter_does_not_retry_when_first_draft_contains_required_information(writing_request, admission):
    client = SequenceClient([complete_draft])
    writer.write(writing_request, admission)
    assert client.calls == 1

def test_adapter_rewrites_once_when_first_draft_misses_required_information(writing_request, admission):
    client = SequenceClient([missing_draft, complete_draft])
    draft = writer.write(writing_request, admission)
    assert client.calls == 2
    assert draft.content == complete_draft
    assert missing_draft in client.messages[1][-1].content

def test_adapter_never_calls_model_three_times_when_repair_still_misses(writing_request, admission):
    client = SequenceClient([missing_draft, missing_draft])
    draft = writer.write(writing_request, admission)
    assert client.calls == 2
    result = NovelReviewer().review(review_request_for(draft))
    assert result.blocking_codes == ("essential_information_missing",)
```

- [ ] **Step 2: 运行红测**

Run: `pytest -q tests/test_llm_novel_writer.py tests/test_novel_writer_validation.py`

Expected: FAIL，当前 Adapter 只调用一次且配置无 `max_contract_repairs`。

- [ ] **Step 3: 增加严格配置和缺失集合函数**

```python
@dataclass(frozen=True, slots=True)
class NovelWriterConfig:
    temperature: float = 0.7
    max_tokens: int = 6000
    minimum_reviewable_chars: int = 500
    system_instruction: str = DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION
    max_contract_repairs: int = 1

    def __post_init__(self) -> None:
        if self.max_contract_repairs not in (0, 1):
            raise ValueError("novel_writer_max_contract_repairs_invalid")

def _missing_information(request: NovelWritingRequest, content: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        item
        for scene in request.chapter_contract.scene_plan.scenes
        for item in scene.essential_information
        if item not in content
    ))
```

- [ ] **Step 4: 提取单次 Runtime 执行并实现一次修复**

```python
first = self._execute(
    request,
    build_novel_writer_messages(request, self._config.system_instruction),
    input_refs=(("chapter", request.chapter_id), ("context", request.context_fingerprint)),
)
self._validate_content(first.output)
missing = _missing_information(request, first.output)
results = [first]
if missing and self._config.max_contract_repairs == 1:
    repaired = self._execute(request, build_novel_writer_repair_messages(
        request, first.output, missing, self._config.system_instruction,
    ))
    self._validate_content(repaired.output)
    results.append(repaired)
content = results[-1].output
```

`_execute` 必须构造 `RuntimeRequest` 并调用现有 `self._runtime.execute`；修复调用的 `input_refs` 增加 `("repair", "essential_information")` 以区分审计记录。

- [ ] **Step 5: 聚合遥测并测试缺失 usage 的传播**

```python
def _sum_optional(values: tuple[int | None, ...]) -> int | None:
    return None if any(value is None for value in values) else sum(value for value in values if value is not None)
```

耗时采用同样规则：任一 `reported_elapsed_seconds` 为 `None` 则聚合为 `None`，否则求和。`content_hash` 只取最终正文。

Run: `pytest -q tests/test_llm_novel_writer.py tests/test_novel_writer_validation.py tests/test_novel_domain_end_to_end.py`

Expected: PASS；Fake 夹具首稿完整，只调用一次并达到 `compile_candidate_ready`。

- [ ] **Step 6: 运行 Writer 架构守卫和全量测试**

Run: `pytest -q tests/test_writer_production_exit_architecture.py tests/test_runtime.py`

Run: `$env:PYTHONDONTWRITEBYTECODE='1'; pytest -q -p no:cacheprovider`

Expected: 全部通过，仅保留已有显式 skip。

- [ ] **Step 7: 提交**

```bash
git add creative_os/domains/llm_novel_writer.py tests/test_llm_novel_writer.py tests/test_novel_writer_validation.py
git commit -m "feat: 增加小说 Writer 有限合同修复"
```

### Task 3: 配置修正与 Live 独立验收

**Files:**
- Modify outside Git: `D:/田雨/Creative OS/.env`（仅 Base URL）
- Modify: `projects/novel_domain_validation/production/reports/real_writer_validation.json`
- Modify: `docs/novel-production-roadmap.md`
- Create: `.superpowers/sdd/2026-08-31-novel-writer-contract-repair/task-3-report.md`

**Interfaces:**
- Consumes: Task 2 的有限重试 Adapter 和现有 Live CLI。
- Produces: 脱敏 Live 报告；通过时开放统一只读投影层设计门禁。

- [ ] **Step 1: 安全修正 Base URL**

用 PowerShell 7 解析 `.env`，只将 `CREATIVE_OS_LLM_BASE_URL` 的值替换为 `https://api.deepseek.com`。不得输出其他行、不得复制或提交 `.env`。修改后通过 `OpenAICompatibleClient.from_env()` 仅断言 `base_url`，不打印 Key。

- [ ] **Step 2: 运行 Fake 回归**

Run: `python scripts/validate_novel_real_writer.py --fixture projects/novel_domain_validation/validation/independent_short_story.json --mode fake --report projects/novel_domain_validation/production/reports/fake_writer_validation.json`

Expected: 退出 0，`stage=compile_candidate_ready`、`review_passed=true`。

- [ ] **Step 3: 运行 Live 独立验收**

Run: `python scripts/validate_novel_real_writer.py --fixture projects/novel_domain_validation/validation/independent_short_story.json --mode live --report projects/novel_domain_validation/production/reports/real_writer_validation.json --env-file "D:/田雨/Creative OS/.env"`

Expected: 最多两次模型调用；退出 0；报告 `stage=compile_candidate_ready`、`review_passed=true`、`canon_patch_count > 0`、`state_candidate_count > 0`。

- [ ] **Step 4: 审计脱敏、硬编码和门禁**

Run: `rg -ni "api_key|authorization|bearer|raw_response|messages|prompt" projects/novel_domain_validation/production/reports/real_writer_validation.json`

Run: `rg -n "文明升阶|林子轩|陈景行|末班钟表店" creative_os`

Expected: 报告无秘密字段；通用源码无作品专名。若 Live 失败，路线图记录真实阻断且不得开放投影/UI。

- [ ] **Step 5: 更新路线图和任务报告**

Live 成功时把真实 Writer 独立验收标为完成，并明确下一阶段仅开放“统一只读可视化数据投影层”，仍不直接开发完整 Web UI。报告记录模型、阶段、Token 统计和审查码，不记录原始正文或秘密。

- [ ] **Step 6: 最终全量验证并提交**

Run: `$env:PYTHONDONTWRITEBYTECODE='1'; pytest -q -p no:cacheprovider`

Run: `git diff --check`

```bash
git add projects/novel_domain_validation/production/reports docs/novel-production-roadmap.md .superpowers/sdd/2026-08-31-novel-writer-contract-repair/task-3-report.md
git commit -m "test: 完成小说 Writer 合同修复验收"
```

不得提交 `.env`。
