# Creative OS Novel Production Priority Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前“能完成一本验证小说”的系统，升级成可反复开新书、可断点续跑、可统计成本、可按问题粒度修复的小说生产工具。

**Architecture:** 采用小步增量方式，不重构已有大文件；优先在 `creative_os/novel_project.py`、`creative_os/batch_runner.py`、`creative_os/llm_metrics.py` 新增边界清晰的模块，再让现有脚本调用这些模块。每个任务独立可测，先补工程化能力，再增强写作质量。

**Tech Stack:** Python 3、pytest、标准库 `pathlib/json/time/dataclasses`、现有 OpenAI-compatible LLM Client、Markdown 文件产物。

## Global Constraints

- 每次用户可见回复必须以“老大”开头。
- 新书项目总文件夹必须使用小说书名命名，例如 `projects/雾城回声/`，不再使用 `validation_novel` 这种测试名。
- `.env` 必须继续被 `.gitignore` 忽略，任何报告和日志不得输出 API Key。
- 不删除旧产物；如需迁移或覆盖，先写入 `backups/`。
- 提交代码前必须向用户确认；Commit Message 使用中文。
- 优先使用 TDD：先写失败测试，再写实现，再跑验证。
- 不引入数据库、任务队列或外部服务；当前阶段只使用文件系统持久化。

---

## Priority Overview

| 优先级 | 能力 | 原因 | 完成标准 |
|---|---|---|---|
| P0 | 新书项目创建器 | 解决重开一本小说时路径混乱 | 一条命令生成以书名命名的项目目录 |
| P0 | 批量重写断点续跑 | 解决 30 章连续重写耗时长、失败后成本高 | 已通过章节不重复请求模型 |
| P0 | 耗时与 token 统计 | 量化最大压测状态和成本 | 每章记录耗时、尝试次数、usage |
| P1 | 局部修复模式 | 避免小问题整章重写 | 可只修复开头、重复句、术语泄露 |
| P1 | 事实校验升级 | 降低关键词同义词维护成本 | 事实校验有明确结构化结果 |
| P2 | 运行报告与文档统一 | 降低使用成本 | README 和报告能指向新流程 |

---

### Task 1: 新书项目创建器

**Files:**
- Create: `creative_os/novel_project.py`
- Create: `scripts/create_novel_project.py`
- Test: `tests/test_novel_project.py`
- Modify: `README.md`

**Interfaces:**
- Produces: `sanitize_project_folder_name(title: str) -> str`
- Produces: `create_novel_project(root: str | Path, title: str, *, author: str = "", genre: str = "") -> Path`
- Consumes: existing project layout conventions from `projects/<book_title>/production/`

- [ ] **Step 1: Write failing tests for book-title folder naming**

```python
from pathlib import Path

from creative_os.novel_project import create_novel_project, sanitize_project_folder_name


def test_sanitize_project_folder_name_keeps_chinese_book_title():
    assert sanitize_project_folder_name("雾城回声") == "雾城回声"


def test_sanitize_project_folder_name_removes_windows_forbidden_chars():
    assert sanitize_project_folder_name("雾城:回声?") == "雾城回声"


def test_create_novel_project_uses_title_as_project_folder(tmp_path):
    project_path = create_novel_project(tmp_path / "projects", "雾城回声", author="田雨", genre="悬疑")

    assert project_path == tmp_path / "projects" / "雾城回声"
    assert (project_path / "project.json").exists()
    assert (project_path / "metadata.json").exists()
    assert (project_path / "production" / "drafts").is_dir()
    assert (project_path / "production" / "final_chapters").is_dir()
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_novel_project.py -q`

Expected: FAIL because `creative_os.novel_project` does not exist.

- [ ] **Step 3: Implement minimal project creator**

```python
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


WINDOWS_FORBIDDEN_CHARS = r'[<>:"/\\|?*]'


def sanitize_project_folder_name(title: str) -> str:
    cleaned = re.sub(WINDOWS_FORBIDDEN_CHARS, "", title).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        raise ValueError("title must contain at least one valid folder character")
    return cleaned


def create_novel_project(root: str | Path, title: str, *, author: str = "", genre: str = "") -> Path:
    projects_root = Path(root)
    folder_name = sanitize_project_folder_name(title)
    project_path = projects_root / folder_name
    production_path = project_path / "production"
    for directory in [
        project_path / "design",
        project_path / "reviews",
        project_path / "reports",
        production_path / "drafts",
        production_path / "final_chapters",
        production_path / "final_chapters_v2",
        production_path / "llm_writer_pilot",
        production_path / "reports",
        production_path / "reviews",
        production_path / "runs",
        production_path / "tasks",
        production_path / "backups",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    _write_json(project_path / "project.json", {"id": folder_name, "name": title, "domain": "novel", "created_at": now})
    _write_json(project_path / "metadata.json", {"title": title, "author": author, "genre": genre, "created_at": now})
    _write_json(project_path / "state.json", {"current_phase": "brief", "current_goal": "完善新书 brief"})
    _write_json(project_path / "brief.json", {"title": title, "author": author, "genre": genre, "logline": ""})
    _write_json(project_path / "baseline.json", {"version": "v1", "created_at": now})
    (project_path / "production_log.jsonl").touch(exist_ok=True)
    return project_path


def _write_json(path: Path, payload: dict[str, str]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Add CLI wrapper**

```python
from __future__ import annotations

import argparse
from pathlib import Path

from creative_os.novel_project import create_novel_project


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", default="")
    parser.add_argument("--genre", default="")
    parser.add_argument("--projects-root", default="projects")
    args = parser.parse_args()
    project_path = create_novel_project(Path(args.projects_root), args.title, author=args.author, genre=args.genre)
    print(project_path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Verify tests and CLI**

Run: `python -m pytest tests/test_novel_project.py -q`

Expected: PASS.

Run: `python scripts/create_novel_project.py --title 雾城回声测试 --author 田雨 --genre 悬疑 --projects-root .tmp_projects`

Expected: prints `.tmp_projects\雾城回声测试` and creates the project folders.

- [ ] **Step 6: Update README usage**

Add a short section:

```markdown
## 新开一本小说

使用书名作为项目总文件夹：

```powershell
python scripts\create_novel_project.py --title 雾城回声 --author 田雨 --genre 悬疑
```

生成路径：`projects\雾城回声\`
```

- [ ] **Step 7: Git checkpoint after user confirmation**

```bash
git add creative_os/novel_project.py scripts/create_novel_project.py tests/test_novel_project.py README.md
git commit -m "新增新书项目创建流程"
```

---

### Task 2: 批量重写断点续跑

**Files:**
- Create: `creative_os/batch_runner.py`
- Modify: `scripts/run_llm_writer_pilot.py`
- Test: `tests/test_batch_runner.py`

**Interfaces:**
- Produces: `BatchChapterStatus(chapter: int, status: str, attempts: int, issues: list[str])`
- Produces: `load_completed_chapters(run_path: str | Path) -> set[int]`
- Produces: `select_pending_chapters(chapters: list[int], completed: set[int], *, force: bool = False) -> list[int]`
- Consumes: existing `run_llm_writer_pilot(project_root, client, chapters=...)`

- [ ] **Step 1: Write failing tests for skip passed chapters**

```python
import json

from creative_os.batch_runner import load_completed_chapters, select_pending_chapters


def test_load_completed_chapters_reads_passed_chapters(tmp_path):
    run_path = tmp_path / "llm_writer_pilot_run.json"
    run_path.write_text(
        json.dumps({
            "chapter_results": {
                "chapter_007": [],
                "chapter_008": ["missing_fact:测试"],
                "chapter_009": []
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    assert load_completed_chapters(run_path) == {7, 9}


def test_select_pending_chapters_skips_completed_by_default():
    assert select_pending_chapters([7, 8, 9], {7, 9}) == [8]


def test_select_pending_chapters_force_runs_all():
    assert select_pending_chapters([7, 8, 9], {7, 9}, force=True) == [7, 8, 9]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_batch_runner.py -q`

Expected: FAIL because `creative_os.batch_runner` does not exist.

- [ ] **Step 3: Implement checkpoint selection**

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BatchChapterStatus:
    chapter: int
    status: str
    attempts: int
    issues: list[str]


def load_completed_chapters(run_path: str | Path) -> set[int]:
    path = Path(run_path)
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    completed: set[int] = set()
    for key, issues in data.get("chapter_results", {}).items():
        if issues:
            continue
        chapter = int(key.replace("chapter_", ""))
        completed.add(chapter)
    return completed


def select_pending_chapters(chapters: list[int], completed: set[int], *, force: bool = False) -> list[int]:
    if force:
        return chapters
    return [chapter for chapter in chapters if chapter not in completed]
```

- [ ] **Step 4: Add CLI flags**

Modify `scripts/run_llm_writer_pilot.py`:

```python
parser.add_argument("--resume", action="store_true", help="Skip chapters that already passed in the latest run record")
parser.add_argument("--force", action="store_true", help="Run selected chapters even when prior run passed")
```

Before calling `run_llm_writer_pilot`:

```python
if args.resume and not args.force:
    from creative_os.batch_runner import load_completed_chapters, select_pending_chapters

    run_path = Path(args.project_root) / "llm_writer_pilot" / "runs" / "llm_writer_pilot_run.json"
    completed = load_completed_chapters(run_path)
    chapters = select_pending_chapters(chapters, completed)
```

- [ ] **Step 5: Verify tests**

Run: `python -m pytest tests/test_batch_runner.py tests/test_llm_writer_script.py -q`

Expected: PASS.

- [ ] **Step 6: Git checkpoint after user confirmation**

```bash
git add creative_os/batch_runner.py scripts/run_llm_writer_pilot.py tests/test_batch_runner.py
git commit -m "新增章节批量重写断点续跑"
```

---

### Task 3: 耗时与 token 统计

**Files:**
- Create: `creative_os/llm_metrics.py`
- Modify: `creative_os/llm_writer.py`
- Test: `tests/test_llm_metrics.py`

**Interfaces:**
- Produces: `LLMUsage(prompt_tokens: int, completion_tokens: int, total_tokens: int)`
- Produces: `TimedCompletion(content: str, elapsed_seconds: float, usage: LLMUsage | None)`
- Updates: `OpenAICompatibleClient.complete(...) -> TimedCompletion`

- [ ] **Step 1: Write failing tests for usage parsing**

```python
from creative_os.llm_metrics import LLMUsage, parse_usage


def test_parse_usage_from_openai_compatible_response():
    usage = parse_usage({
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 300,
            "total_tokens": 400,
        }
    })

    assert usage == LLMUsage(prompt_tokens=100, completion_tokens=300, total_tokens=400)


def test_parse_usage_returns_none_when_provider_omits_usage():
    assert parse_usage({"choices": []}) is None
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_llm_metrics.py -q`

Expected: FAIL because `creative_os.llm_metrics` does not exist.

- [ ] **Step 3: Implement metrics module**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class TimedCompletion:
    content: str
    elapsed_seconds: float
    usage: LLMUsage | None


def parse_usage(payload: dict[str, Any]) -> LLMUsage | None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    return LLMUsage(
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
        total_tokens=int(usage.get("total_tokens", 0)),
    )
```

- [ ] **Step 4: Adapt writer client with compatibility shim**

In `creative_os/llm_writer.py`, keep fake clients working by normalizing return values:

```python
def _completion_text(result: str | TimedCompletion) -> str:
    if isinstance(result, str):
        return result
    return result.content
```

When writing review JSON, include:

```python
"elapsed_seconds": elapsed_seconds,
"usage": asdict(usage) if usage else None,
```

- [ ] **Step 5: Verify metrics tests and writer tests**

Run: `python -m pytest tests/test_llm_metrics.py tests/test_llm_writer.py -q`

Expected: PASS.

- [ ] **Step 6: Git checkpoint after user confirmation**

```bash
git add creative_os/llm_metrics.py creative_os/llm_writer.py tests/test_llm_metrics.py tests/test_llm_writer.py
git commit -m "新增模型调用耗时和token统计"
```

---

### Task 4: 局部修复模式

**Files:**
- Create: `creative_os/local_repair.py`
- Modify: `scripts/run_llm_writer_pilot.py`
- Test: `tests/test_local_repair.py`

**Interfaces:**
- Produces: `detect_repair_scope(issues: list[str]) -> str`
- Produces: `build_local_repair_messages(chapter_text: str, issues: list[str]) -> list[ModelMessage]`
- Scope values: `"local"` or `"full"`

- [ ] **Step 1: Write failing tests for local repair routing**

```python
from creative_os.local_repair import detect_repair_scope


def test_detect_repair_scope_uses_local_for_reader_surface_issues():
    assert detect_repair_scope(["time_word_opener"]) == "local"
    assert detect_repair_scope(["reader_term:Context"]) == "local"


def test_detect_repair_scope_uses_full_for_missing_fact():
    assert detect_repair_scope(["missing_fact:林遥未离城"]) == "full"


def test_detect_repair_scope_uses_full_for_shrinkage():
    assert detect_repair_scope(["below_minimum_chinese_chars"]) == "full"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_local_repair.py -q`

Expected: FAIL because `creative_os.local_repair` does not exist.

- [ ] **Step 3: Implement repair scope**

```python
from __future__ import annotations

from creative_os.llm_writer import ModelMessage


LOCAL_ONLY_ISSUES = {"time_word_opener"}
LOCAL_PREFIXES = ("reader_term:",)


def detect_repair_scope(issues: list[str]) -> str:
    for issue in issues:
        if issue in LOCAL_ONLY_ISSUES:
            continue
        if issue.startswith(LOCAL_PREFIXES):
            continue
        return "full"
    return "local"


def build_local_repair_messages(chapter_text: str, issues: list[str]) -> list[ModelMessage]:
    return [
        ModelMessage(role="system", content="你是小说局部修复 Agent。只输出修复后的完整章节正文。"),
        ModelMessage(
            role="user",
            content=(
                "请只修复以下读者可见问题，不改变剧情事实、人物关系和章节长度：\n"
                + "\n".join(f"- {issue}" for issue in issues)
                + "\n\n原章节：\n"
                + chapter_text
            ),
        ),
    ]
```

- [ ] **Step 4: Add optional CLI flag**

Add:

```python
parser.add_argument("--local-repair", action="store_true", help="Use local repair for reader-surface issues")
```

When a retry is caused only by local issues, call `build_local_repair_messages` with the previous generated chapter instead of rebuilding a full rewrite prompt.

- [ ] **Step 5: Verify tests**

Run: `python -m pytest tests/test_local_repair.py tests/test_llm_writer.py -q`

Expected: PASS.

- [ ] **Step 6: Git checkpoint after user confirmation**

```bash
git add creative_os/local_repair.py scripts/run_llm_writer_pilot.py tests/test_local_repair.py
git commit -m "新增章节局部修复模式"
```

---

### Task 5: 事实校验结构化升级

**Files:**
- Create: `creative_os/fact_validation.py`
- Modify: `creative_os/llm_writer.py`
- Test: `tests/test_fact_validation.py`

**Interfaces:**
- Produces: `FactValidationResult(fact: str, supported: bool, evidence: list[str])`
- Produces: `validate_required_facts(required_facts: list[str], text: str) -> list[FactValidationResult]`
- Consumes: current keyword evidence table from `creative_os.llm_writer`

- [ ] **Step 1: Write failing tests for structured result**

```python
from creative_os.fact_validation import validate_required_facts


def test_validate_required_facts_returns_evidence():
    results = validate_required_facts(
        ["灯务署镇压失败"],
        "灯务署的镇压已经失败了，因为他们无法遗忘所有人。",
    )

    assert results[0].fact == "灯务署镇压失败"
    assert results[0].supported is True
    assert results[0].evidence == ["镇压", "失败"]


def test_validate_required_facts_marks_missing_fact():
    results = validate_required_facts(["林遥未离城"], "林澈走进旧灯巷。")

    assert results[0].supported is False
    assert results[0].evidence == []
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_fact_validation.py -q`

Expected: FAIL because `creative_os.fact_validation` does not exist.

- [ ] **Step 3: Implement structured keyword validator**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FactValidationResult:
    fact: str
    supported: bool
    evidence: list[str]


def validate_required_facts(required_facts: list[str], text: str) -> list[FactValidationResult]:
    from creative_os.llm_writer import FACT_KEYWORD_ALIASES

    results: list[FactValidationResult] = []
    for fact in required_facts:
        matched_keys = [key for key in FACT_KEYWORD_ALIASES if key in fact]
        evidence = [
            key
            for key in matched_keys
            if any(alias in text for alias in FACT_KEYWORD_ALIASES[key])
        ]
        required_count = len(matched_keys) if len(matched_keys) <= 2 else len(matched_keys) - 1
        supported = bool(matched_keys) and len(evidence) >= required_count
        results.append(FactValidationResult(fact=fact, supported=supported, evidence=evidence))
    return results
```

- [ ] **Step 4: Use structured results in writer reviews**

In `validate_llm_rewrite`, replace opaque `missing_fact` checks with structured results:

```python
for result in validate_required_facts(payload.required_facts, text):
    if not result.supported:
        issues.append(f"missing_fact:{result.fact}")
```

In review JSON, include:

```python
"fact_results": [asdict(result) for result in validate_required_facts(payload.required_facts, final_text)]
```

- [ ] **Step 5: Verify tests**

Run: `python -m pytest tests/test_fact_validation.py tests/test_llm_writer.py -q`

Expected: PASS.

- [ ] **Step 6: Git checkpoint after user confirmation**

```bash
git add creative_os/fact_validation.py creative_os/llm_writer.py tests/test_fact_validation.py tests/test_llm_writer.py
git commit -m "升级章节事实校验结果结构"
```

---

### Task 6: 运行报告与开发路线文档同步

**Files:**
- Modify: `projects/validation_novel/production/reports/llm_writer_stress_report.md`
- Modify: `projects/validation_novel/production/reports/v2_backlog.md`
- Create: `docs/novel-production-roadmap.md`
- Test: `tests/test_docs_links.py`

**Interfaces:**
- Produces: readable roadmap document for future work
- Consumes: report paths from current production validation project

- [ ] **Step 1: Write failing doc link test**

```python
from pathlib import Path


def test_roadmap_links_existing_reports():
    roadmap = Path("docs/novel-production-roadmap.md")
    assert roadmap.exists()
    text = roadmap.read_text(encoding="utf-8")
    assert "projects/validation_novel/production/reports/llm_writer_stress_report.md" in text
    assert "projects/validation_novel/production/reports/v2_backlog.md" in text
```

- [ ] **Step 2: Run test and verify failure**

Run: `python -m pytest tests/test_docs_links.py -q`

Expected: FAIL because `docs/novel-production-roadmap.md` does not exist.

- [ ] **Step 3: Create roadmap doc**

```markdown
# Novel Production Roadmap

## P0

- 新书项目创建器：使用书名创建 `projects/<书名>/`。
- 批量重写断点续跑：失败后只跑未通过章节。
- 耗时与 token 统计：每章记录 elapsed_seconds、attempts、usage。

## P1

- 局部修复模式：针对开头模板、术语泄露、重复句做小范围修复。
- 事实校验结构化升级：输出 supported/evidence，减少人工判断成本。

## Reports

- Stress Report: `projects/validation_novel/production/reports/llm_writer_stress_report.md`
- V2 Backlog: `projects/validation_novel/production/reports/v2_backlog.md`
```

- [ ] **Step 4: Update V2 backlog**

Append this exact section:

```markdown
## LLM Writer 性能与工程化

- P0：新书项目创建器，项目总文件夹使用小说书名。
- P0：批量重写断点续跑，避免已通过章节重复请求模型。
- P0：记录每章耗时、尝试次数、token usage 和失败原因。
- P1：局部修复模式，降低整章重写比例。
- P1：结构化事实校验，输出 evidence 便于审查。
```

- [ ] **Step 5: Verify docs**

Run: `python -m pytest tests/test_docs_links.py -q`

Expected: PASS.

- [ ] **Step 6: Git checkpoint after user confirmation**

```bash
git add docs/novel-production-roadmap.md projects/validation_novel/production/reports/v2_backlog.md tests/test_docs_links.py
git commit -m "补充小说生产开发路线图"
```

---

## Execution Order

1. Task 1: 新书项目创建器。
2. Task 2: 批量重写断点续跑。
3. Task 3: 耗时与 token 统计。
4. Task 4: 局部修复模式。
5. Task 5: 事实校验结构化升级。
6. Task 6: 运行报告与开发路线文档同步。

## Verification Before Completion

Run:

```powershell
python -m pytest -q
python -m py_compile creative_os\novel_project.py creative_os\batch_runner.py creative_os\llm_metrics.py creative_os\local_repair.py creative_os\fact_validation.py creative_os\llm_writer.py scripts\create_novel_project.py scripts\run_llm_writer_pilot.py
rg -n "API_KEY|sk-" docs projects creative_os scripts tests
```

Expected:

- All tests pass.
- `py_compile` exits with code 0.
- Secret scan finds no real API key.

## Self-Review

- Spec coverage: includes project folder naming, long rewrite time optimization, cost metrics, partial repair, fact validation, and docs.
- Placeholder scan: no placeholder markers and no unspecified implementation step.
- Type consistency: function names and return types are defined before use in later tasks.
