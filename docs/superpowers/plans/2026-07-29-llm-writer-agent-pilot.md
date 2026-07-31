# LLM Writer Agent Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入真实 LLM Writer Agent，并先重写《雾城回声》第 4-6 章做小规模验证。

**Architecture:** 新增独立的 LLM 写作模块，负责模型适配、章节输入包、写作提示词、质量门禁和试跑产物；现有 `validation_runtime.py` 继续保留为生产验证脚手架，只提供 SceneSpec、旧稿和基础门禁。先用可注入的模型客户端做单元测试，再用环境变量启用真实 API 试跑，避免把供应商 SDK 和章节逻辑耦合在一起。

**Tech Stack:** Python 3.11+, standard library `urllib.request`/`json`/`dataclasses`, existing pytest suite, existing `creative_os.validation_runtime` SceneSpec and reader quality gate.

## Global Constraints

- 输出必须用中文。
- 每次回复用户必须以“老大”开头。
- 不新开小说，继续使用《雾城回声》的既有剧情、人物和线索。
- 本阶段只重写第 4-6 章，不能默认覆盖 1-36 章。
- 删除操作必须先备份；本计划不删除旧稿，只新增试跑产物。
- 不直接手写章节正文，必须通过脚本和模型接口生成。
- 没有 API Key 时，单元测试必须仍可用 Fake Client 完成。
- 最终读者正文不得出现 `Scene`、`Context`、`Task`、`Compiled Knowledge`、`Knowledge Patch`、`新增事实`、`前几章`、`本章前段`、`本章中段`、`本章后段`。
- 第 4-6 章开头不得全部使用时间词开头，例如 `凌晨`、`清晨`、`上午`、`中午`、`下午`、`傍晚`、`夜`、`深夜`。
- 章节正文不得低于原 V1 对应章节中文字符数的 85%，防止“修复后缩水”。

---

## File Structure

- Create: `creative_os/llm_writer.py`
  - 定义模型客户端协议、OpenAI-compatible HTTP 客户端、章节输入包、提示词构建、试跑执行器。
- Modify: `creative_os/validation_runtime.py`
  - 暴露第 4-6 章 SceneSpec 和读者门禁复用接口，不在这里继续扩写模型调用。
- Modify: `tests/test_llm_writer.py`
  - 覆盖章节输入包、提示词约束、Fake Client 重写、质量门禁、缩水门禁、时间词开头门禁。
- Runtime create: `projects/validation_novel/production/llm_writer_pilot/`
  - 保存第 4-6 章模型重写稿、输入包、评审记录和运行记录。
- Modify: `V1_PRODUCTION_VALIDATION_EXECUTION.md`
  - 记录 LLM Writer Agent Pilot 的产物位置、运行方式和当前验证结论。

---

### Task 1: Model Client And Config Boundary

**Files:**
- Create: `creative_os/llm_writer.py`
- Create: `tests/test_llm_writer.py`

**Interfaces:**
- Produces: `ModelMessage(role: str, content: str)`
- Produces: `ModelClient` protocol with `complete(messages: list[ModelMessage], *, temperature: float, max_tokens: int) -> str`
- Produces: `OpenAICompatibleClient.from_env() -> OpenAICompatibleClient`

- [ ] **Step 1: Write the failing test**

Create `tests/test_llm_writer.py`:

```python
import os

import pytest

from creative_os.llm_writer import ModelMessage, OpenAICompatibleClient


def test_openai_compatible_client_reads_env(monkeypatch):
    monkeypatch.setenv("CREATIVE_OS_LLM_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("CREATIVE_OS_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("CREATIVE_OS_LLM_MODEL", "writer-model")

    client = OpenAICompatibleClient.from_env()

    assert client.base_url == "https://api.example.test/v1"
    assert client.api_key == "sk-test"
    assert client.model == "writer-model"


def test_openai_compatible_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("CREATIVE_OS_LLM_API_KEY", raising=False)
    monkeypatch.setenv("CREATIVE_OS_LLM_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("CREATIVE_OS_LLM_MODEL", "writer-model")

    with pytest.raises(ValueError, match="CREATIVE_OS_LLM_API_KEY"):
        OpenAICompatibleClient.from_env()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests\test_llm_writer.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'creative_os.llm_writer'`.

- [ ] **Step 3: Implement the client boundary**

Create `creative_os/llm_writer.py`:

```python
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: str
    content: str


class ModelClient(Protocol):
    def complete(self, messages: list[ModelMessage], *, temperature: float, max_tokens: int) -> str:
        ...


@dataclass(frozen=True, slots=True)
class OpenAICompatibleClient:
    base_url: str
    api_key: str
    model: str

    @classmethod
    def from_env(cls) -> "OpenAICompatibleClient":
        base_url = os.environ.get("CREATIVE_OS_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        api_key = os.environ.get("CREATIVE_OS_LLM_API_KEY", "")
        model = os.environ.get("CREATIVE_OS_LLM_MODEL", "")
        if not api_key:
            raise ValueError("CREATIVE_OS_LLM_API_KEY is required")
        if not model:
            raise ValueError("CREATIVE_OS_LLM_MODEL is required")
        return cls(base_url=base_url, api_key=api_key, model=model)

    def complete(self, messages: list[ModelMessage], *, temperature: float, max_tokens: int) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM request failed: HTTP {exc.code} {body}") from exc
        return data["choices"][0]["message"]["content"].strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest tests\test_llm_writer.py -q
```

Expected: PASS.

### Task 2: Chapter Rewrite Input Package

**Files:**
- Modify: `creative_os/llm_writer.py`
- Modify: `tests/test_llm_writer.py`

**Interfaces:**
- Consumes: `creative_os.validation_runtime._chapter_specs_for_number(chapter_number: int) -> list[SceneSpec]`
- Produces: `ChapterRewriteInput(chapter_number: int, title: str, source_text: str, previous_summary: str, scene_goals: list[str], required_facts: list[str], banned_terms: list[str], min_chinese_chars: int)`
- Produces: `build_chapter_rewrite_input(project_root: str | Path, chapter_number: int) -> ChapterRewriteInput`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_llm_writer.py`:

```python
from pathlib import Path

from creative_os.llm_writer import build_chapter_rewrite_input
from creative_os.validation_runtime import write_v11_acceptance_artifacts


def test_build_chapter_rewrite_input_for_chapter_four(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)

    payload = build_chapter_rewrite_input(tmp_path, 4)

    assert payload.chapter_number == 4
    assert payload.title == "废档案"
    assert "废弃档案库" in payload.source_text
    assert "进入废弃档案库并建立档案被清理过的异常" in payload.scene_goals
    assert "档案库与灯务署系统仍连接" in payload.required_facts
    assert "Context" in payload.banned_terms
    assert payload.min_chinese_chars >= 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests\test_llm_writer.py::test_build_chapter_rewrite_input_for_chapter_four -q
```

Expected: FAIL because `build_chapter_rewrite_input` is not defined.

- [ ] **Step 3: Implement input packaging**

Append to `creative_os/llm_writer.py`:

```python
from pathlib import Path

from creative_os.validation_runtime import _chapter_specs_for_number


CHINESE_TIME_OPENERS = ("凌晨", "清晨", "上午", "中午", "下午", "傍晚", "夜里", "深夜", "夜")
BANNED_READER_TERMS = [
    "Scene",
    "Context",
    "Task",
    "Compiled Knowledge",
    "Knowledge Patch",
    "新增事实",
    "前几章",
    "本章前段",
    "本章中段",
    "本章后段",
    "目标很清楚",
]


@dataclass(frozen=True, slots=True)
class ChapterRewriteInput:
    chapter_number: int
    title: str
    source_text: str
    previous_summary: str
    scene_goals: list[str]
    required_facts: list[str]
    banned_terms: list[str]
    min_chinese_chars: int


def build_chapter_rewrite_input(project_root: str | Path, chapter_number: int) -> ChapterRewriteInput:
    root = Path(project_root)
    chapter_path = root / "final_chapters" / f"chapter_{chapter_number:03d}.md"
    if not chapter_path.exists():
        raise FileNotFoundError(chapter_path)
    source_text = chapter_path.read_text(encoding="utf-8")
    title = source_text.splitlines()[0].removeprefix("# 第 ").split("：", 1)[1].strip()
    previous_summary = _previous_chapter_summary(root, chapter_number)
    specs = _chapter_specs_for_number(chapter_number)
    required_facts: list[str] = []
    for spec in specs:
        required_facts.extend(spec.new_facts)
    return ChapterRewriteInput(
        chapter_number=chapter_number,
        title=title,
        source_text=source_text,
        previous_summary=previous_summary,
        scene_goals=[spec.goal for spec in specs],
        required_facts=required_facts,
        banned_terms=BANNED_READER_TERMS,
        min_chinese_chars=max(1000, int(_count_chinese_chars(source_text) * 0.85)),
    )


def _previous_chapter_summary(root: Path, chapter_number: int) -> str:
    if chapter_number <= 1:
        return ""
    previous_path = root / "final_chapters" / f"chapter_{chapter_number - 1:03d}.md"
    if not previous_path.exists():
        return ""
    paragraphs = [line.strip() for line in previous_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    return " ".join(paragraphs[-3:])[:800]


def _count_chinese_chars(text: str) -> int:
    return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest tests\test_llm_writer.py::test_build_chapter_rewrite_input_for_chapter_four -q
```

Expected: PASS.

### Task 3: Prompt Builder And Quality Gate

**Files:**
- Modify: `creative_os/llm_writer.py`
- Modify: `tests/test_llm_writer.py`

**Interfaces:**
- Consumes: `ChapterRewriteInput`
- Produces: `build_writer_messages(payload: ChapterRewriteInput) -> list[ModelMessage]`
- Produces: `validate_llm_rewrite(payload: ChapterRewriteInput, text: str) -> list[str]`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_llm_writer.py`:

```python
from creative_os.llm_writer import build_writer_messages, validate_llm_rewrite


def test_writer_prompt_contains_continuity_and_anti_ai_constraints(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)
    payload = build_chapter_rewrite_input(tmp_path, 4)

    messages = build_writer_messages(payload)
    joined = "\n".join(message.content for message in messages)

    assert "不要把三个场景机械拼接" in joined
    assert "转场必须服务情绪、动作或信息推进" in joined
    assert "不要使用统一时间词开头" in joined
    assert "档案库与灯务署系统仍连接" in joined


def test_validate_llm_rewrite_rejects_time_opener_and_shrinkage(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)
    payload = build_chapter_rewrite_input(tmp_path, 4)

    issues = validate_llm_rewrite(payload, "# 第 4 章：废档案\n\n凌晨，林澈站在门外。")

    assert "time_word_opener" in issues
    assert "below_minimum_chinese_chars" in issues
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests\test_llm_writer.py::test_writer_prompt_contains_continuity_and_anti_ai_constraints tests\test_llm_writer.py::test_validate_llm_rewrite_rejects_time_opener_and_shrinkage -q
```

Expected: FAIL because functions are missing.

- [ ] **Step 3: Implement prompt builder and gate**

Append to `creative_os/llm_writer.py`:

```python
from creative_os.validation_runtime import validate_reader_facing_text


def build_writer_messages(payload: ChapterRewriteInput) -> list[ModelMessage]:
    system = (
        "你是长篇小说章节 Writer Agent。只输出读者可见正文，不输出解释、提纲、审稿意见或系统术语。"
        "写作目标是降低 AI 味，保持长篇小说连贯性。"
    )
    user = (
        f"请重写《雾城回声》第 {payload.chapter_number} 章《{payload.title}》。\n"
        f"上一章收束信息：{payload.previous_summary}\n"
        f"本章必须完成的剧情目标：{'; '.join(payload.scene_goals)}\n"
        f"本章必须保留的事实：{'; '.join(payload.required_facts)}\n"
        f"禁止出现的词：{'; '.join(payload.banned_terms)}\n"
        f"最低中文字符数：{payload.min_chinese_chars}\n\n"
        "写作要求：\n"
        "1. 不要把三个场景机械拼接成三段概要。\n"
        "2. 转场必须服务情绪、动作或信息推进，只有真实换地点或换视角时才明显转场。\n"
        "3. 不要使用统一时间词开头，尤其不要让每章第一句都从凌晨、傍晚、中午等时间开始。\n"
        "4. 保留悬疑推进、人物动机和证据链，不要改核心设定。\n"
        "5. 只输出 Markdown 章节正文，标题格式必须是 `# 第 N 章：标题`。\n\n"
        "旧稿如下，重写时可调整句序、转场和段落，但不得丢失关键事实：\n"
        f"{payload.source_text}"
    )
    return [ModelMessage(role="system", content=system), ModelMessage(role="user", content=user)]


def validate_llm_rewrite(payload: ChapterRewriteInput, text: str) -> list[str]:
    issues = validate_reader_facing_text(text)
    body_lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    first_body = body_lines[0] if body_lines else ""
    if first_body.startswith(CHINESE_TIME_OPENERS):
        issues.append("time_word_opener")
    if _count_chinese_chars(text) < payload.min_chinese_chars:
        issues.append("below_minimum_chinese_chars")
    for fact in payload.required_facts:
        if fact not in text:
            issues.append(f"missing_fact:{fact}")
    return issues
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest tests\test_llm_writer.py -q
```

Expected: PASS.

### Task 4: Rewrite Runner With Retry And Artifacts

**Files:**
- Modify: `creative_os/llm_writer.py`
- Modify: `tests/test_llm_writer.py`

**Interfaces:**
- Consumes: `ModelClient`
- Consumes: `build_chapter_rewrite_input(project_root, chapter_number)`
- Consumes: `build_writer_messages(payload)`
- Consumes: `validate_llm_rewrite(payload, text)`
- Produces: `run_llm_writer_pilot(project_root: str | Path, client: ModelClient, chapters: list[int] = [4, 5, 6], max_attempts: int = 2) -> dict[str, object]`

- [ ] **Step 1: Write failing test with Fake Client**

Append to `tests/test_llm_writer.py`:

```python
from creative_os.llm_writer import ModelClient, ModelMessage, run_llm_writer_pilot


class FakeWriterClient:
    def __init__(self):
        self.calls = 0

    def complete(self, messages: list[ModelMessage], *, temperature: float, max_tokens: int) -> str:
        self.calls += 1
        chapter_marker = next(message.content for message in messages if "请重写《雾城回声》第" in message.content)
        if "第 4 章" in chapter_marker:
            return _fake_chapter(4, "废档案", "林澈把手套压在废弃档案库门缝上。", "档案库与灯务署系统仍连接")
        if "第 5 章" in chapter_marker:
            return _fake_chapter(5, "审查室", "许砚没有先看口供，她先看林澈的手。", "审查记录存在缺页")
        return _fake_chapter(6, "白塔旧址", "白塔旧址的墙面先认出了林澈。", "林澈曾安装回声室相关模块")


def _fake_chapter(number: int, title: str, first_sentence: str, chapter_fact: str) -> str:
    required = {
        4: ["废弃档案库未彻底废弃", "林澈旧维护权限可进入档案库", "档案库与灯务署系统仍连接", "林遥档案被覆盖", "岚舟档案与林遥同属回声室编号", "自愿离城名单存在原始底稿", "许砚知道回声室编号", "许砚没有立即上报全部证据", "林澈和阿岚继续逃亡"],
        5: ["林澈熟悉审查室结构", "许砚怀疑林澈旧身份", "林澈刻意隐藏冷光管核心信息", "许砚看见林遥残影", "低亮冷光可在审查室环境显影", "林澈愿意冒险证明林遥未离城", "审查记录存在缺页", "缺页与回声室编号相关", "许砚开始保护证据链"],
        6: ["白塔旧址保存旧事故档案", "白姨知道回声室相关旧事", "十年前事故与禁灯令升级有关", "林澈有旧维护员编号", "白姨认识年少林澈", "周闻白与白塔事故存在隐秘关联", "林澈曾安装回声室相关模块", "冷光塔前身与白塔有关", "林澈记忆被剪除不是偶然"],
    }[number]
    body = "\n\n".join([first_sentence + " " + "。".join(required) + "。"] * 80)
    return f"# 第 {number} 章：{title}\n\n{body}\n"


def test_run_llm_writer_pilot_writes_chapters_four_to_six(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)

    record = run_llm_writer_pilot(tmp_path, FakeWriterClient())

    assert record["result"] == "pass"
    assert record["chapters"] == [4, 5, 6]
    assert (tmp_path / "llm_writer_pilot" / "chapters" / "chapter_004.md").exists()
    assert (tmp_path / "llm_writer_pilot" / "inputs" / "chapter_004_input.json").exists()
    assert (tmp_path / "llm_writer_pilot" / "reviews" / "chapter_004_review.json").exists()
    chapter_004 = (tmp_path / "llm_writer_pilot" / "chapters" / "chapter_004.md").read_text(encoding="utf-8")
    assert not chapter_004.splitlines()[2].startswith(("凌晨", "清晨", "上午", "中午", "下午", "傍晚", "夜", "深夜"))
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests\test_llm_writer.py::test_run_llm_writer_pilot_writes_chapters_four_to_six -q
```

Expected: FAIL because `run_llm_writer_pilot` is missing.

- [ ] **Step 3: Implement runner**

Append to `creative_os/llm_writer.py`:

```python
from dataclasses import asdict


def run_llm_writer_pilot(
    project_root: str | Path,
    client: ModelClient,
    chapters: list[int] | None = None,
    max_attempts: int = 2,
) -> dict[str, object]:
    root = Path(project_root)
    selected = chapters or [4, 5, 6]
    out_root = root / "llm_writer_pilot"
    chapter_results: dict[str, list[str]] = {}
    for chapter_number in selected:
        payload = build_chapter_rewrite_input(root, chapter_number)
        _write_json(out_root / "inputs" / f"chapter_{chapter_number:03d}_input.json", asdict(payload))
        final_text = ""
        final_issues: list[str] = []
        for _ in range(max_attempts):
            final_text = client.complete(build_writer_messages(payload), temperature=0.78, max_tokens=12000)
            final_issues = validate_llm_rewrite(payload, final_text)
            if not final_issues:
                break
        _write_text(out_root / "chapters" / f"chapter_{chapter_number:03d}.md", final_text)
        _write_json(out_root / "reviews" / f"chapter_{chapter_number:03d}_review.json", {"issues": final_issues})
        chapter_results[f"chapter_{chapter_number:03d}"] = final_issues
    result = "pass" if all(not issues for issues in chapter_results.values()) else "fail"
    run_record = {"result": result, "chapters": selected, "chapter_results": chapter_results}
    _write_json(out_root / "runs" / "llm_writer_pilot_run.json", run_record)
    return run_record


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest tests\test_llm_writer.py -q
```

Expected: PASS.

### Task 5: Manual API Pilot Command And Documentation

**Files:**
- Create: `scripts/run_llm_writer_pilot.py`
- Modify: `V1_PRODUCTION_VALIDATION_EXECUTION.md`

**Interfaces:**
- Consumes: `OpenAICompatibleClient.from_env()`
- Consumes: `run_llm_writer_pilot(project_root, client)`
- Produces: repeatable command for rewriting chapters 4-6 with a configured model.

- [ ] **Step 1: Create script**

Create `scripts/run_llm_writer_pilot.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from creative_os.llm_writer import OpenAICompatibleClient, run_llm_writer_pilot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default="projects/validation_novel/production")
    parser.add_argument("--chapters", default="4,5,6")
    args = parser.parse_args()
    chapters = [int(item.strip()) for item in args.chapters.split(",") if item.strip()]
    record = run_llm_writer_pilot(Path(args.project_root), OpenAICompatibleClient.from_env(), chapters=chapters)
    print(record)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run offline tests**

Run:

```powershell
python -m pytest tests\test_llm_writer.py tests\test_validation_runtime.py -q
```

Expected: PASS without API Key.

- [ ] **Step 3: Run real pilot when env is configured**

Run only when the user has configured a model key:

```powershell
$env:CREATIVE_OS_LLM_BASE_URL="https://api.openai.com/v1"
$env:CREATIVE_OS_LLM_API_KEY="<real-key>"
$env:CREATIVE_OS_LLM_MODEL="<writer-model>"
python scripts\run_llm_writer_pilot.py --project-root projects\validation_novel\production --chapters 4,5,6
```

Expected: `projects/validation_novel/production/llm_writer_pilot/runs/llm_writer_pilot_run.json` has `"result": "pass"`.

- [ ] **Step 4: Document result**

Append to `V1_PRODUCTION_VALIDATION_EXECUTION.md`:

```markdown
- LLM Writer Agent Pilot：新增 `creative_os/llm_writer.py`、`scripts/run_llm_writer_pilot.py` 和 `production/llm_writer_pilot/`。第 4-6 章通过真实模型接口重写；无 API Key 时可用 Fake Client 完成离线回归测试。
```

### Task 6: Final Verification

**Files:**
- Test: `tests/test_llm_writer.py`
- Test: `tests/test_validation_runtime.py`
- Runtime inspect: `projects/validation_novel/production/llm_writer_pilot/`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verified pilot result.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run syntax check**

Run:

```powershell
python -m py_compile creative_os\llm_writer.py creative_os\production.py creative_os\agents.py creative_os\validation_runtime.py scripts\run_llm_writer_pilot.py
```

Expected: exit code 0.

- [ ] **Step 3: Scan pilot chapters**

Run:

```powershell
rg -n "Scene|Context|Task|Compiled Knowledge|Knowledge Patch|新增事实|前几章|本章前段|本章中段|本章后段|目标很清楚" projects\validation_novel\production\llm_writer_pilot\chapters
```

Expected: no matches.

- [ ] **Step 4: Inspect chapter openers**

Run:

```powershell
Get-Content projects\validation_novel\production\llm_writer_pilot\chapters\chapter_004.md -TotalCount 4
Get-Content projects\validation_novel\production\llm_writer_pilot\chapters\chapter_005.md -TotalCount 4
Get-Content projects\validation_novel\production\llm_writer_pilot\chapters\chapter_006.md -TotalCount 4
```

Expected: the first body sentences are not all time-word openings.

## Self-Review

- Spec coverage: covers LLM Writer Agent integration, model invocation boundary, chapters 4-6 pilot rewrite, existing-novel continuity, no manual prose writing, no knowledge-base expansion in this phase.
- Placeholder scan: no unresolved placeholder markers.
- Type consistency: `ModelMessage`, `ModelClient`, `ChapterRewriteInput`, `build_writer_messages`, `validate_llm_rewrite`, and `run_llm_writer_pilot` signatures match across tasks.
