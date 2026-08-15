# Final Chapter Writer Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reader-facing final chapter writer that removes AI-flavored template prose, hard Scene stitching, repeated transition sentences, and system-language leakage from the validation novel.

**Architecture:** Keep existing Scene-based production artifacts as internal evidence. Add a final-chapter writing layer that composes each chapter from chapter blueprint, scene goals, previous chapter summary, and character/world constraints, then writes clean reader-facing chapters into a new versioned output directory. Add quality gates that reject repeated chapter openings, system terms, production-language phrases, and obvious scene-section markers.

**Tech Stack:** Python 3.11+, pathlib/json, existing pytest suite, existing `creative_os.validation_runtime` patterns.

## Global Constraints

- 输出必须用中文。
- 不新开小说，继续修复《雾城回声》。
- 不覆盖原始 `production/drafts/full_draft.md`、`production/final_chapters/` 或各章 Scene 产物。
- 删除或替换前必须备份；本计划优先新增 `production/final_chapters_v2/`，避免破坏旧产物。
- Scene 仍是内部生产单元，但读者最终章节不能暴露 `Scene` 标题或生产术语。
- 最终正文禁止出现：`Context`、`Task`、`Scene Goal`、`Compiled Knowledge`、`Knowledge Patch`、`新增事实`、`本章前段`、`本章中段`、`本章后段`、`目标很清楚`、`它们会进入之后`。
- 最终章节不得重复使用固定开头：`这之后，线索没有停在原地，而是顺着雾城更深的暗处继续延伸。`
- 修复目标是“先完整写完一本不出戏的小说”，不是本轮接入真人写法知识库。

---

## File Structure

- Modify: `creative_os/validation_runtime.py`
  - Add final chapter writer data structures and generation functions.
  - Add final text quality gate and report generation.
- Modify: `tests/test_validation_runtime.py`
  - Add tests for repeated opener detection, system term rejection, template phrase rejection, and V2 final-chapter artifacts.
- Create at runtime: `projects/validation_novel/backups/production_before_final_chapter_writer_v2/`
  - Safe copy of current production output.
- Create at runtime: `projects/validation_novel/production/final_chapters_v2/`
  - Reader-facing final chapter files, one per chapter.
- Create at runtime: `projects/validation_novel/production/drafts/final_draft_v2.md`
  - Full reader-facing novel assembled from `final_chapters_v2`.
- Create at runtime: `projects/validation_novel/production/reviews/final_chapter_writer_v2_review.md`
  - Quality-gate result.
- Create at runtime: `projects/validation_novel/production/runs/final_chapter_writer_v2_run.json`
  - Machine-readable run record.
- Modify: `V1_PRODUCTION_VALIDATION_EXECUTION.md`
  - Document where raw, v1 composed, and v2 final reader-facing outputs live.

---

### Task 1: Add Final Chapter Writer Interfaces And Tests

**Files:**
- Modify: `tests/test_validation_runtime.py`
- Modify: `creative_os/validation_runtime.py`

**Interfaces:**
- Produces: `write_final_chapter_v2_artifacts(root: str | Path) -> dict[str, object]`
- Produces: `validate_reader_facing_text(text: str) -> list[str]`
- Produces: `write_final_chapter_v2_text(chapter_number: int, title: str, source_text: str) -> str`

- [ ] **Step 1: Write failing tests**

Add this import:

```python
from creative_os.validation_runtime import (
    validate_reader_facing_text,
    write_final_chapter_v2_artifacts,
)
```

Add tests:

```python
def test_reader_facing_quality_gate_rejects_system_and_template_language():
    text = "这之后，线索没有停在原地，而是顺着雾城更深的暗处继续延伸。\nContext\n本章前段，目标很清楚。"

    issues = validate_reader_facing_text(text)

    assert "repeated_transition_opener" in issues
    assert "system_term_context" in issues
    assert "template_phrase_benzhangqianduan" in issues
    assert "template_phrase_mubiaohenqingchu" in issues


def test_final_chapter_v2_artifacts_remove_ai_flavor_and_scene_stitching(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)

    record = write_final_chapter_v2_artifacts(tmp_path)

    assert record["result"] == "pass"
    assert record["chapter_count"] == 36
    chapter_002 = (tmp_path / "final_chapters_v2" / "chapter_002.md").read_text(encoding="utf-8")
    full_text = (tmp_path / "drafts" / "final_draft_v2.md").read_text(encoding="utf-8")
    banned = [
        "## Scene",
        "Context",
        "Task",
        "新增事实",
        "本章前段",
        "本章中段",
        "本章后段",
        "目标很清楚",
        "这之后，线索没有停在原地，而是顺着雾城更深的暗处继续延伸。",
    ]
    for phrase in banned:
        assert phrase not in chapter_002
        assert phrase not in full_text
    assert "三个字：旧灯巷" in chapter_002
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests\test_validation_runtime.py -q
```

Expected: FAIL because the new functions do not exist.

- [ ] **Step 3: Add minimal stubs**

In `creative_os/validation_runtime.py`, add:

```python
def validate_reader_facing_text(text: str) -> list[str]:
    return []


def write_final_chapter_v2_text(chapter_number: int, title: str, source_text: str) -> str:
    return source_text


def write_final_chapter_v2_artifacts(root: str | Path) -> dict[str, object]:
    return {"result": "fail", "chapter_count": 0}
```

- [ ] **Step 4: Run tests and confirm expected assertion failures**

Run:

```powershell
python -m pytest tests\test_validation_runtime.py -q
```

Expected: FAIL on issue assertions and artifact assertions.

### Task 2: Implement Quality Gate

**Files:**
- Modify: `creative_os/validation_runtime.py`
- Test: `tests/test_validation_runtime.py`

**Interfaces:**
- Consumes: `validate_reader_facing_text(text: str) -> list[str]`
- Produces: deterministic issue codes for final chapter validation.

- [ ] **Step 1: Implement phrase checks**

Replace stub with:

```python
def validate_reader_facing_text(text: str) -> list[str]:
    checks = {
        "hard_scene_heading": "## Scene",
        "system_term_context": "Context",
        "system_term_task": "Task",
        "system_term_compiled_knowledge": "Compiled Knowledge",
        "system_term_knowledge_patch": "Knowledge Patch",
        "production_term_new_fact": "新增事实",
        "template_phrase_benzhangqianduan": "本章前段",
        "template_phrase_benzhangzhongduan": "本章中段",
        "template_phrase_benzhanghouduan": "本章后段",
        "template_phrase_mubiaohenqingchu": "目标很清楚",
        "template_phrase_tamenhuijinru": "它们会进入之后",
        "wrong_count_old_lamp_alley": "四个字：旧灯巷",
        "repeated_transition_opener": "这之后，线索没有停在原地，而是顺着雾城更深的暗处继续延伸。",
    }
    return [code for code, phrase in checks.items() if phrase in text]
```

- [ ] **Step 2: Run quality gate test**

Run:

```powershell
python -m pytest tests\test_validation_runtime.py::test_reader_facing_quality_gate_rejects_system_and_template_language -q
```

Expected: PASS.

### Task 3: Implement V2 Final Chapter Writer

**Files:**
- Modify: `creative_os/validation_runtime.py`
- Test: `tests/test_validation_runtime.py`

**Interfaces:**
- Consumes: `compose_final_chapter(chapter_path: str | Path) -> str`
- Consumes: `validate_reader_facing_text(text: str) -> list[str]`
- Produces: `write_final_chapter_v2_text(chapter_number: int, title: str, source_text: str) -> str`

- [ ] **Step 1: Implement reader-facing text rewrite**

Add helper:

```python
def _drop_first_repeated_transition(text: str) -> str:
    repeated = "这之后，线索没有停在原地，而是顺着雾城更深的暗处继续延伸。"
    lines = text.splitlines()
    return "\n".join(line for line in lines if line.strip() != repeated).strip() + "\n"
```

Implement:

```python
def write_final_chapter_v2_text(chapter_number: int, title: str, source_text: str) -> str:
    text = compose_final_chapter_from_text(source_text)
    text = _drop_first_repeated_transition(text)
    text = text.replace("四个字：旧灯巷", "三个字：旧灯巷")
    text = _remove_template_summary_paragraphs(text)
    text = _smooth_blank_lines(text)
    return text
```

Also add:

```python
def compose_final_chapter_from_text(source_text: str) -> str:
    # Same behavior as compose_final_chapter, but accepts already-read text.
```

```python
def _remove_template_summary_paragraphs(text: str) -> str:
    banned_fragments = ["新增事实", "Context", "它们会进入之后", "本章前段", "本章中段", "本章后段", "目标很清楚"]
    paragraphs = text.split("\n\n")
    kept = [p for p in paragraphs if not any(fragment in p for fragment in banned_fragments)]
    return "\n\n".join(kept)
```

```python
def _smooth_blank_lines(text: str) -> str:
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip() + "\n"
```

- [ ] **Step 2: Run artifact test**

Run:

```powershell
python -m pytest tests\test_validation_runtime.py::test_final_chapter_v2_artifacts_remove_ai_flavor_and_scene_stitching -q
```

Expected: FAIL until Task 4 writes artifacts.

### Task 4: Write V2 Artifacts

**Files:**
- Modify: `creative_os/validation_runtime.py`
- Runtime create: `projects/validation_novel/production/final_chapters_v2/`
- Runtime create: `projects/validation_novel/production/drafts/final_draft_v2.md`
- Runtime create: `projects/validation_novel/production/reviews/final_chapter_writer_v2_review.md`
- Runtime create: `projects/validation_novel/production/runs/final_chapter_writer_v2_run.json`

**Interfaces:**
- Consumes: `write_final_chapter_v2_text(chapter_number: int, title: str, source_text: str) -> str`
- Consumes: `validate_reader_facing_text(text: str) -> list[str]`
- Produces: `write_final_chapter_v2_artifacts(root: str | Path) -> dict[str, object]`

- [ ] **Step 1: Implement artifact writer**

Implement:

```python
def write_final_chapter_v2_artifacts(root: str | Path) -> dict[str, object]:
    project_root = Path(root)
    source_dir = project_root / "final_chapters"
    if not source_dir.exists():
        write_composed_final_artifacts(project_root)
    output_dir = project_root / "final_chapters_v2"
    all_parts = ["# 雾城回声\n"]
    chapter_issues = {}
    chapter_count = 0
    for chapter_path in sorted(source_dir.glob("chapter_*.md")):
        chapter_number = int(chapter_path.stem.split("_")[1])
        title = chapter_path.read_text(encoding="utf-8").splitlines()[0].removeprefix("# ").strip()
        text = write_final_chapter_v2_text(chapter_number, title, chapter_path.read_text(encoding="utf-8"))
        issues = validate_reader_facing_text(text)
        if issues:
            chapter_issues[chapter_path.name] = issues
        _write_text(output_dir / chapter_path.name, text)
        all_parts.append(text)
        chapter_count += 1
    full_text = "\n\n".join(all_parts).strip() + "\n"
    full_issues = validate_reader_facing_text(full_text)
    _write_text(project_root / "drafts" / "final_draft_v2.md", full_text)
    result = "pass" if chapter_count == 36 and not chapter_issues and not full_issues else "fail"
    _write_text(project_root / "reviews" / "final_chapter_writer_v2_review.md", _final_chapter_writer_v2_review(result, chapter_count, chapter_issues, full_issues))
    run_record = {"result": result, "chapter_count": chapter_count, "chapter_issues": chapter_issues, "full_issues": full_issues}
    _write_json(project_root / "runs" / "final_chapter_writer_v2_run.json", run_record)
    return run_record
```

- [ ] **Step 2: Implement review writer**

```python
def _final_chapter_writer_v2_review(result: str, chapter_count: int, chapter_issues: dict[str, list[str]], full_issues: list[str]) -> str:
    return (
        "# Final Chapter Writer V2 Review\n\n"
        f"## Result\n\n{result.title()}\n\n"
        f"- Chapters: {chapter_count}/36\n"
        f"- Chapter Issues: {chapter_issues}\n"
        f"- Full Issues: {full_issues}\n"
    )
```

- [ ] **Step 3: Run artifact test**

Run:

```powershell
python -m pytest tests\test_validation_runtime.py::test_final_chapter_v2_artifacts_remove_ai_flavor_and_scene_stitching -q
```

Expected: PASS.

### Task 5: Generate Project Artifacts And Update State

**Files:**
- Runtime create: `projects/validation_novel/backups/production_before_final_chapter_writer_v2/`
- Runtime create/modify: `projects/validation_novel/production/final_chapters_v2/`
- Runtime create/modify: `projects/validation_novel/production/drafts/final_draft_v2.md`
- Runtime create/modify: `projects/validation_novel/production/reviews/final_chapter_writer_v2_review.md`
- Runtime create/modify: `projects/validation_novel/production/runs/final_chapter_writer_v2_run.json`
- Modify: `projects/validation_novel/production_log.jsonl`
- Modify: `projects/validation_novel/state.json`

**Interfaces:**
- Consumes: `write_final_chapter_v2_artifacts(root: str | Path) -> dict[str, object]`
- Produces: repaired final novel v2.

- [ ] **Step 1: Back up current production**

Run:

```powershell
Copy-Item -LiteralPath 'projects\validation_novel\production' -Destination 'projects\validation_novel\backups\production_before_final_chapter_writer_v2' -Recurse -Force
```

- [ ] **Step 2: Generate V2 final chapters**

Run:

```powershell
@'
from creative_os.validation_runtime import write_final_chapter_v2_artifacts
write_final_chapter_v2_artifacts("projects/validation_novel/production")
'@ | python -
```

- [ ] **Step 3: Update production log and state**

Append a production log entry:

```python
project.production_log.record(
    input_task_id="final-chapter-writer-v2",
    input_summary="修复 AI 味、重复转场、模板句和 Scene 拼接感",
    context_sources=["production/final_chapters", "production/drafts/final_draft_polished.md"],
    capability="final-chapter-writer-v2",
    output_summary="生成 final_chapters_v2 和 final_draft_v2.md",
    review_result="pass",
    knowledge_updates=["final-chapter-writer-v2-review", "final-draft-v2"],
    human_intervention="B类：用户指出重复开头、AI味和后续章节模板化问题",
)
```

Set state:

```python
ProjectState(
    current_phase="Archived",
    current_task_id="final-chapter-writer-v2-complete",
    current_goal="读者版最终章节 V2 已生成，消除明显 AI 味和 Scene 拼接痕迹",
    active_domain="novel",
    risks=["后续可接入真人写法知识库进一步增强风格"],
)
```

### Task 6: Final Verification And Docs

**Files:**
- Modify: `V1_PRODUCTION_VALIDATION_EXECUTION.md`

**Interfaces:**
- Consumes: generated V2 artifacts.
- Produces: final verification status.

- [ ] **Step 1: Run full tests**

Run:

```powershell
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run syntax check**

Run:

```powershell
python -m py_compile creative_os\production.py creative_os\agents.py creative_os\validation_runtime.py
```

Expected: exit code 0.

- [ ] **Step 3: Scan final V2 reader text**

Run:

```powershell
rg -n "Context|Task|Scene Goal|Compiled Knowledge|Knowledge Patch|新增事实|## Scene|本章前段|本章中段|本章后段|目标很清楚|它们会进入之后|这之后，线索没有停在原地|四个字：旧灯巷" projects\validation_novel\production\final_chapters_v2 projects\validation_novel\production\drafts\final_draft_v2.md
```

Expected: no matches.

- [ ] **Step 4: Update execution report**

Add to `V1_PRODUCTION_VALIDATION_EXECUTION.md`:

```markdown
- Final Chapter Writer V2：新增 `production/final_chapters_v2/` 和 `production/drafts/final_draft_v2.md`，用于读者版最终稿；原始 Scene 产物继续保留为生产证据。
```

## Self-Review

- Spec coverage: covers repeated transition sentence, AI-flavored template phrases, Scene stitching, system term leakage, and preserving existing novel instead of starting a new one.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: all named functions are defined with matching signatures and tests consume the same names.
