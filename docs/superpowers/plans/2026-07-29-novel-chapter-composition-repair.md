# Novel Chapter Composition Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the validation novel output so Scene remains an internal production unit while reader-facing chapters are composed, sanitized, and reviewed as continuous chapter text.

**Architecture:** Keep raw Scene outputs untouched as the production baseline. Add a Chapter Composer layer that reads existing chapter draft artifacts, removes internal Scene headings, inserts light transitions, sanitizes system terms, fixes known Chinese count errors, and writes separate final reader-facing chapters. Add tests that prove the final output does not leak production vocabulary or hard Scene boundaries.

**Tech Stack:** Python 3.11+, pathlib/json, existing pytest suite.

## Global Constraints

- Output must be in Chinese when reporting to the user.
- Do not overwrite raw production artifacts; write repaired reader-facing output under `projects/validation_novel/production/final_chapters/`.
- Before any destructive replacement, back up the original production directory.
- Scene Task / Context / Review / Knowledge artifacts remain valid internal evidence.
- Reader-facing text must not contain `Context`, `Task`, `Scene Goal`, `Compiled Knowledge`, `Knowledge Patch`, `新增事实`, `它们会进入之后的 Context`, or `## Scene`.
- Fix `四个字：旧灯巷` to `三个字：旧灯巷`.

---

### Task 1: Add Composer And Sanitizer

**Files:**
- Modify: `creative_os/validation_runtime.py`
- Test: `tests/test_validation_runtime.py`

**Interfaces:**
- Produces: `compose_final_chapter(chapter_path: str | Path) -> str`
- Produces: `write_composed_final_artifacts(root: str | Path) -> dict[str, object]`

- [ ] **Step 1: Write failing tests**

Add tests that:

```python
def test_composed_final_artifacts_remove_internal_scene_and_system_terms(tmp_path):
    write_full_draft_artifacts(tmp_path)
    record = write_composed_final_artifacts(tmp_path)
    assert record["result"] == "pass"
    final_chapter = (tmp_path / "final_chapters" / "chapter_002.md").read_text(encoding="utf-8")
    assert "## Scene" not in final_chapter
    assert "Context" not in final_chapter
    assert "新增事实" not in final_chapter
    assert "三个字：旧灯巷" in final_chapter
    assert "四个字：旧灯巷" not in final_chapter
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_validation_runtime.py -q`

Expected: FAIL because composer functions do not exist.

- [ ] **Step 3: Implement composer**

In `creative_os/validation_runtime.py`, implement:

```python
def compose_final_chapter(chapter_path: str | Path) -> str:
    ...

def write_composed_final_artifacts(root: str | Path) -> dict[str, object]:
    ...
```

Behavior:
- Preserve `# 第 N 章：标题`.
- Remove lines starting with `## Scene`.
- Insert subtle transition sentences between removed Scene blocks.
- Replace `四个字：旧灯巷` with `三个字：旧灯巷`.
- Remove paragraphs containing system-only terms.
- Write `final_chapters/chapter_XXX.md`.
- Write `drafts/final_draft_polished.md`.
- Write `reviews/chapter_composition_review.md`.
- Write `runs/chapter_composition_run.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_validation_runtime.py -q`

Expected: PASS.

### Task 2: Generate Repaired Novel Output

**Files:**
- Create: `projects/validation_novel/production/final_chapters/*.md`
- Create: `projects/validation_novel/production/drafts/final_draft_polished.md`
- Create: `projects/validation_novel/production/reviews/chapter_composition_review.md`
- Create: `projects/validation_novel/production/runs/chapter_composition_run.json`
- Modify: `projects/validation_novel/production_log.jsonl`
- Modify: `projects/validation_novel/state.json`

**Interfaces:**
- Consumes: `write_composed_final_artifacts(root: str | Path) -> dict[str, object]`
- Produces: repaired reader-facing novel output.

- [ ] **Step 1: Back up current production output**

Run a safe PowerShell copy:

```powershell
Copy-Item -LiteralPath 'projects\validation_novel\production' -Destination 'projects\validation_novel\backups\production_before_chapter_composition_repair' -Recurse -Force
```

- [ ] **Step 2: Generate repaired artifacts**

Run:

```powershell
@'
from creative_os.validation_runtime import write_composed_final_artifacts
write_composed_final_artifacts("projects/validation_novel/production")
'@ | python -
```

- [ ] **Step 3: Update project log and state**

Append production log entry for `chapter-composition-repair`.

Set current state to indicate the repair pass is complete and V1.1 remains archived.

- [ ] **Step 4: Verify artifacts**

Run:

```powershell
rg -n "Context|Task|Scene Goal|Compiled Knowledge|Knowledge Patch|新增事实|## Scene|四个字：旧灯巷" projects\validation_novel\production\final_chapters projects\validation_novel\production\drafts\final_draft_polished.md
```

Expected: no matches.

### Task 3: Final Validation

**Files:**
- Modify if needed: `V1_PRODUCTION_VALIDATION_EXECUTION.md`

**Interfaces:**
- Consumes: repaired artifacts and test suite.
- Produces: final verification result.

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

- [ ] **Step 3: Update execution report**

Add a note that raw Scene drafts are preserved and reader-facing composed chapters are now in `production/final_chapters/`.

## Self-Review

- Spec coverage: covers Scene hard boundaries, transition/composition layer, Context leakage, Chinese count bug, and preservation of raw production evidence.
- Placeholder scan: no TODO/TBD placeholders.
- Type consistency: `write_composed_final_artifacts` returns a JSON-serializable dict used by tests and generation.
