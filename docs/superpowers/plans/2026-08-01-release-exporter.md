# Novel Release Exporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成干净的正式发布目录，让读者和作者能快速找到全书正文与章节，不暴露研发过程产物。

**Architecture:** 保留现有 `projects/<project>/production/` 研发目录不动，新增只读导出模块从 canonical final draft 和 final chapters 复制到 `releases/<书名>/`。发布目录只包含 `README.md`、`book.md`、`chapters/`、`metadata.json` 和少量 reports。

**Tech Stack:** Python 3、pytest、标准库 `pathlib/json/re/shutil`。

## Global Constraints

- 不删除、不移动现有 `projects/` 研发产物。
- 新发布目录用书名命名，例如 `releases/雾城回声/`。
- 正式章节目录必须简单：`chapters/001-回城.md`。
- 全书正文必须固定为根目录 `book.md`。
- `.creative_os/` 暂不导出，避免发布版继续复杂化。

---

### Task 1: Release Exporter Core

**Files:**
- Create: `creative_os/release_exporter.py`
- Create: `tests/test_release_exporter.py`

**Interfaces:**
- Produces: `export_novel_release(project_root: str | Path, output_root: str | Path) -> Path`
- Produces: `chapter_release_name(chapter_path: Path) -> str`

- [ ] Write failing tests for release directory shape.
- [ ] Implement metadata loading, title fallback, book copy, chapter rename, report copy.
- [ ] Run `python -m pytest tests/test_release_exporter.py -q`.

### Task 2: CLI

**Files:**
- Create: `scripts/export_novel_release.py`
- Test: `tests/test_release_exporter.py`

**Interfaces:**
- CLI: `python scripts/export_novel_release.py --project-root projects/validation_novel --output-root releases`

- [ ] Add script wrapper.
- [ ] Verify CLI against `projects/validation_novel`.

### Task 3: Docs

**Files:**
- Modify: `README.md`

- [ ] Add “导出正式发布版” section.
- [ ] Run full test suite.

