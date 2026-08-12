# New Book Release Flow Before Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 先打通“新书创建 -> 生产目录 -> 正式发布目录 -> 状态记录”的稳定链路，再进入控制台任务面板开发。

**Architecture:** 把底层路径、发布目录和批量任务状态先收敛成稳定接口；控制台面板只读取这些接口，不直接扫描混乱的研发目录。现有 `projects/validation_novel/` 继续作为验证项目，正式新书默认使用 `projects/<书名>/`，发布版统一导出到 `releases/<书名>/`。

**Tech Stack:** Python 3、pytest、标准库 `pathlib/json/shutil/dataclasses`、现有 `creative_os.novel_project`、`creative_os.release_exporter`、`creative_os.llm_writer`。

## Global Constraints

- 当前阶段不优先做 Web 可视化工作台。
- 新书项目总文件夹必须使用小说书名，例如 `projects/雾城回声/`。
- 正式发布目录必须简单：`releases/<书名>/README.md`、`book.md`、`chapters/`、`metadata.json`、`reports/`。
- 研发过程产物必须保留在项目生产目录或 `.creative_os/` 类隐藏目录，不能混进正式发布版。
- 不删除、不移动已有 `projects/validation_novel/` 验证产物；任何迁移先做导出或备份。
- `.env` 不得进入版本控制；日志、报告和发布目录不得包含真实 API Key。
- 提交前运行测试；推送必须推到功能分支，不推 `main`。

---

## Priority Order

1. P0：新书项目创建与目录规范统一。
2. P0：正式发布导出全流程稳定。
3. P0：批量生成/重写任务状态记录与断点续跑统一。
4. P1：控制台任务面板。
5. P2：Web 可视化工作台。

---

### Task 1: 新书项目结构规范化

**Files:**
- Modify: `creative_os/novel_project.py`
- Modify: `scripts/create_novel_project.py`
- Create: `tests/test_new_book_project_layout.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `create_novel_project(root: str | Path, title: str, *, author: str = "", genre: str = "") -> Path`
- Produces: project directory `projects/<书名>/`
- Produces: production directory `projects/<书名>/production/`
- Produces: optional hidden runtime directory `projects/<书名>/.creative_os/`

- [ ] **Step 1: Write failing layout test**

```python
from creative_os.novel_project import create_novel_project


def test_new_book_project_uses_book_title_and_clean_top_level(tmp_path):
    project = create_novel_project(tmp_path / "projects", "雾城回声", author="田雨", genre="悬疑")

    assert project.name == "雾城回声"
    assert (project / "README.md").exists()
    assert (project / "metadata.json").exists()
    assert (project / "production").is_dir()
    assert (project / ".creative_os").is_dir()
    assert not (project / "validation_novel").exists()
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_new_book_project_layout.py -q`

Expected: FAIL if `README.md` or `.creative_os` is not created.

- [ ] **Step 3: Implement minimal structure update**

Update `create_novel_project()` so it creates:

```text
projects/<书名>/
├─ README.md
├─ metadata.json
├─ project.json
├─ brief.json
├─ state.json
├─ production/
│  ├─ drafts/
│  ├─ final_chapters/
│  ├─ reports/
│  └─ runs/
└─ .creative_os/
   ├─ contexts/
   ├─ knowledge/
   ├─ reviews/
   ├─ tasks/
   ├─ backups/
   └─ llm_writer/
```

Use this README content:

```markdown
# 雾城回声

## 正文位置

- 研发全书稿：`production/drafts/final_draft_polished.md`
- 正式发布版：运行导出后查看 `releases/雾城回声/book.md`

## 生产过程

研发过程产物在 `.creative_os/` 和 `production/` 中维护。
```

- [ ] **Step 4: Verify**

Run: `python -m pytest tests/test_new_book_project_layout.py tests/test_novel_project.py -q`

Expected: PASS.

---

### Task 2: 发布导出器适配书名项目

**Files:**
- Modify: `creative_os/release_exporter.py`
- Modify: `scripts/export_novel_release.py`
- Modify: `tests/test_release_exporter.py`

**Interfaces:**
- Consumes: `export_novel_release(project_root: str | Path, output_root: str | Path) -> Path`
- Produces: `releases/<书名>/book.md`
- Produces: `releases/<书名>/chapters/001-章节名.md`

- [ ] **Step 1: Add test for book-title project root**

```python
def test_export_accepts_book_title_project_root(tmp_path):
    project_root = tmp_path / "projects" / "雾城回声"
    production = project_root / "production"
    (production / "drafts").mkdir(parents=True)
    (production / "final_chapters").mkdir(parents=True)
    (project_root / "project.json").write_text('{"name":"雾城回声"}', encoding="utf-8")
    (project_root / "metadata.json").write_text("{}", encoding="utf-8")
    (production / "drafts" / "final_draft_polished.md").write_text("# 第 1 章：回城\n\n正文", encoding="utf-8")
    (production / "final_chapters" / "chapter_001.md").write_text("# 第 1 章：回城\n\n正文", encoding="utf-8")

    release = export_novel_release(project_root, tmp_path / "releases")

    assert release == tmp_path / "releases" / "雾城回声"
    assert (release / "book.md").exists()
    assert (release / "chapters" / "001-回城.md").exists()
```

- [ ] **Step 2: Run test**

Run: `python -m pytest tests/test_release_exporter.py -q`

Expected: PASS after any required small adjustments.

- [ ] **Step 3: Add CLI smoke command to docs**

Update README:

```powershell
python scripts\export_novel_release.py --project-root projects\雾城回声 --output-root releases
```

- [ ] **Step 4: Verify real validation export still works**

Run:

```powershell
python scripts\export_novel_release.py --project-root projects\validation_novel --output-root releases
```

Expected:

```text
releases\雾城回声
```

---

### Task 3: 任务状态记录统一

**Files:**
- Create: `creative_os/task_status.py`
- Modify: `creative_os/llm_writer.py`
- Modify: `creative_os/batch_runner.py`
- Create: `tests/test_task_status.py`

**Interfaces:**
- Produces: `ChapterTaskStatus(chapter: int, status: str, attempts: int, elapsed_seconds: float, issues: list[str])`
- Produces: `write_chapter_status(project_root: str | Path, status: ChapterTaskStatus) -> Path`
- Produces: `load_chapter_statuses(project_root: str | Path) -> list[ChapterTaskStatus]`

- [ ] **Step 1: Write failing status tests**

```python
from creative_os.task_status import ChapterTaskStatus, load_chapter_statuses, write_chapter_status


def test_write_and_load_chapter_status(tmp_path):
    status = ChapterTaskStatus(chapter=7, status="pass", attempts=2, elapsed_seconds=12.5, issues=[])

    path = write_chapter_status(tmp_path, status)
    statuses = load_chapter_statuses(tmp_path)

    assert path.name == "chapter_007_status.json"
    assert statuses == [status]
```

- [ ] **Step 2: Implement file-backed status**

Write status files to:

```text
<project_root>/production/runs/status/chapter_007_status.json
```

If the caller passes a production root directly, support:

```text
<production_root>/runs/status/chapter_007_status.json
```

- [ ] **Step 3: Integrate LLM writer**

After each chapter run in `run_llm_writer_pilot()`, write:

```python
ChapterTaskStatus(
    chapter=chapter_number,
    status="pass" if not final_issues else "fail",
    attempts=attempts.get(chapter_key, 0),
    elapsed_seconds=float(metrics[chapter_key]["elapsed_seconds"]),
    issues=final_issues,
)
```

- [ ] **Step 4: Verify**

Run: `python -m pytest tests/test_task_status.py tests/test_llm_writer.py tests/test_batch_runner.py -q`

Expected: PASS.

---

### Task 4: 控制台任务面板

**Files:**
- Create: `creative_os/console_dashboard.py`
- Create: `scripts/novel_console.py`
- Create: `tests/test_console_dashboard.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `load_chapter_statuses(project_root: str | Path) -> list[ChapterTaskStatus]`
- Produces: `render_console_dashboard(project_root: str | Path) -> str`
- CLI: `python scripts\novel_console.py --project-root projects\雾城回声`

- [ ] **Step 1: Write failing render test**

```python
from creative_os.console_dashboard import render_console_dashboard
from creative_os.task_status import ChapterTaskStatus, write_chapter_status


def test_render_console_dashboard_shows_status_summary(tmp_path):
    write_chapter_status(tmp_path, ChapterTaskStatus(1, "pass", 1, 3.2, []))
    write_chapter_status(tmp_path, ChapterTaskStatus(2, "fail", 2, 8.5, ["missing_fact:测试"]))

    output = render_console_dashboard(tmp_path)

    assert "章节状态" in output
    assert "通过: 1" in output
    assert "失败: 1" in output
    assert "chapter_002" in output
    assert "missing_fact:测试" in output
```

- [ ] **Step 2: Implement text dashboard**

Output format:

```text
章节状态
通过: 1
失败: 1

chapter_001 pass attempts=1 elapsed=3.2s
chapter_002 fail attempts=2 elapsed=8.5s issues=missing_fact:测试
```

- [ ] **Step 3: Add CLI**

`novel_console.py` prints `render_console_dashboard(args.project_root)`.

- [ ] **Step 4: Verify**

Run: `python -m pytest tests/test_console_dashboard.py tests/test_task_status.py -q`

Expected: PASS.

---

### Task 5: Web 可视化工作台暂缓记录

**Files:**
- Modify: `docs/novel-production-roadmap.md`
- Modify: `projects/validation_novel/production/reports/v2_backlog.md`

**Interfaces:**
- Produces: explicit roadmap statement that Web UI starts after status files and console dashboard are stable.

- [ ] **Step 1: Update roadmap**

Add:

```markdown
## Web 工作台准入条件

只有满足以下条件后才进入 Web 可视化工作台：

- 新书项目使用 `projects/<书名>/`。
- 正式发布目录使用 `releases/<书名>/`。
- 每章任务状态已落盘到 `runs/status/`。
- 控制台任务面板能展示通过、失败、耗时和失败原因。
```

- [ ] **Step 2: Verify docs mention order**

Run:

```powershell
rg -n "Web 工作台准入条件|控制台任务面板|projects/<书名>|releases/<书名>" docs projects/validation_novel/production/reports/v2_backlog.md
```

Expected: all key phrases are present.

---

## Verification Before Completion

Run:

```powershell
python -m pytest -q
python -m py_compile creative_os\novel_project.py creative_os\release_exporter.py creative_os\task_status.py creative_os\console_dashboard.py scripts\create_novel_project.py scripts\export_novel_release.py scripts\novel_console.py
python scripts\export_novel_release.py --project-root projects\validation_novel --output-root releases
python scripts\novel_console.py --project-root projects\validation_novel
rg -n "sk-[A-Za-z0-9]{20,}" --glob "!.env" .
```

Expected:

- All tests pass.
- Release export contains only `README.md`、`book.md`、`chapters/`、`metadata.json`、`reports/`。
- Console dashboard prints chapter status summary.
- Secret scan finds no real API key.

## Self-Review

- Spec coverage: plan implements the recommended order: project/release flow first, status second, console panel third, Web UI last.
- Placeholder scan: no placeholder markers or unspecified implementation steps.
- Type consistency: all produced interfaces are named before dependent tasks consume them.

