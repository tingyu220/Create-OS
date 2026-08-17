# Legacy Novel Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将保留大纲、世界观、人物设定和正式正文的半成品小说安全导入 Creative OS，人工确认项目真相基线后继续写作。

**Architecture:** 导入过程分为只读扫描、文档分类、事实抽取、冲突报告、人工确认和项目物化六步。旧目录始终作为只读来源；未确认材料只能进入导入候选区，不能参与正式续写 Context；小说领域适配器构造章节接续任务，通用 Memory Kernel 负责记忆治理和 Context 编译。

**Tech Stack:** Python 3.11、Markdown、JSON/JSONL、pathlib、pytest、现有 OpenAI-compatible Writer Client。

## Global Constraints

- 依赖 `2026-08-13-system-memory-kernel.md` 全部通过。
- 源目录 `D:\田雨\AI写作助手\NovelProject\Novels\文明升阶` 只读，不移动、不覆盖、不删除。
- 只把清理后保留的正式正文视为 canon；世界观、人物、大纲和伏笔属于候选项目知识，确认后激活。
- 废稿、备份和重复版本不得进入正常 Retriever。
- 续写前必须输出冲突报告并经过人工确认。
- 第一次试运行只生成下一章，不直接批量写完整本。

## File Structure

- `creative_os/importing/model.py`：导入清单、文档分类、候选事实和冲突模型。
- `creative_os/importing/scanner.py`：只读扫描和文件指纹。
- `creative_os/domains/novel/importer.py`：小说目录分类和 Markdown 解析。
- `creative_os/domains/novel/baseline.py`：canon、人物状态、世界规则、时间线和伏笔基线。
- `creative_os/domains/novel/continuation.py`：下一章任务和接续 Context。
- `scripts/import_legacy_novel.py`：扫描、报告、确认和物化 CLI。
- `scripts/continue_novel.py`：单章接续试运行 CLI。

---

### Task 1: Build a Read-Only Import Manifest

**Files:**
- Create: `creative_os/importing/__init__.py`
- Create: `creative_os/importing/model.py`
- Create: `creative_os/importing/scanner.py`
- Test: `tests/test_legacy_import_scanner.py`

**Interfaces:**
- Produces: `ImportDocument`, `DocumentRole`, `ImportManifest`, `scan_source(source_root) -> ImportManifest`。

- [ ] **Step 1: Write scanner tests**

```python
def test_scanner_records_relative_paths_hashes_and_never_writes_source(tmp_path):
    source = build_legacy_fixture(tmp_path)
    before = snapshot_tree(source)
    manifest = scan_source(source)
    assert manifest.documents[0].sha256
    assert all(not Path(doc.relative_path).is_absolute() for doc in manifest.documents)
    assert snapshot_tree(source) == before
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_legacy_import_scanner.py -q`

Expected: FAIL because importing package is missing.

- [ ] **Step 3: Implement deterministic scanning**

Read `.md` and `.json` only; record relative path, extension, byte size, modified time and SHA-256. Ignore hidden system files. Sort by normalized relative path and perform no writes under `source_root`.

- [ ] **Step 4: Run and verify pass**

Run: `python -m pytest tests/test_legacy_import_scanner.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add creative_os/importing tests/test_legacy_import_scanner.py
git commit -m "新增半成品项目只读扫描器"
```

### Task 2: Classify Novel Documents and Exclude Draft Archives

**Files:**
- Create: `creative_os/domains/novel/importer.py`
- Test: `tests/test_legacy_novel_classifier.py`

**Interfaces:**
- Consumes: `ImportManifest`.
- Produces: `classify_novel_documents(manifest, mapping) -> ClassifiedNovelImport` with roles `CANON_CHAPTER`, `WORLD`, `CHARACTER`, `OUTLINE`, `HOOK`, `AUTHOR_CONTEXT`, `ARCHIVE`, `UNKNOWN`。

- [ ] **Step 1: Write classification tests using the Civilization fixture**

```python
def test_classifier_keeps_official_chapters_and_excludes_fix_tree():
    result = classify_novel_documents(manifest, default_novel_mapping())
    assert role_of(result, "04_Chapters/第1章 数据里的幽灵.md") == DocumentRole.CANON_CHAPTER
    assert role_of(result, "00_Worldview/Main_Worldview.md") == DocumentRole.WORLD
    assert role_of(result, "01_Characters/林子轩.md") == DocumentRole.CHARACTER
    assert role_of(result, "fix/第1章 数据里的幽灵.md") == DocumentRole.ARCHIVE
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_legacy_novel_classifier.py -q`

Expected: FAIL because classifier is missing.

- [ ] **Step 3: Implement configurable path-based classification**

Defaults must recognize the current Chinese/English folder names but accept an explicit mapping JSON for other projects. `fix`, `_archive`, `backup`, `备份` and paths chosen by the user are excluded from canon regardless of filenames.

- [ ] **Step 4: Run and verify pass**

Run: `python -m pytest tests/test_legacy_novel_classifier.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add creative_os/domains/novel/importer.py tests/test_legacy_novel_classifier.py
git commit -m "实现旧小说资料分类"
```

### Task 3: Extract a Candidate Project Baseline

**Files:**
- Create: `creative_os/domains/novel/baseline.py`
- Test: `tests/test_novel_baseline_builder.py`

**Interfaces:**
- Consumes: classified Markdown documents.
- Produces: `NovelBaselineDraft` containing ordered canon chapters, world rules, characters, plot milestones, hooks, timeline events, style constraints and provenance.

- [ ] **Step 1: Write baseline extraction tests**

```python
def test_baseline_preserves_provenance_and_never_activates_unconfirmed_facts():
    draft = build_novel_baseline(classified_fixture)
    assert [chapter.number for chapter in draft.canon_chapters] == [1, 2]
    assert draft.world_rules[0].source_path == "核心框架.md"
    assert all(item.status == "candidate" for item in draft.knowledge_candidates)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_novel_baseline_builder.py -q`

Expected: FAIL because baseline builder is missing.

- [ ] **Step 3: Implement structured Markdown extraction**

Parse headings, YAML front matter, chapter numbers, lists and Markdown tables. Preserve source path, source hash and heading for every extracted item. Do not infer facts that are absent; ambiguous prose becomes a candidate note with low confidence.

- [ ] **Step 4: Run and verify pass**

Run: `python -m pytest tests/test_novel_baseline_builder.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add creative_os/domains/novel/baseline.py tests/test_novel_baseline_builder.py
git commit -m "构建小说候选记忆基线"
```

### Task 4: Detect Conflicts Before Import Approval

**Files:**
- Create: `creative_os/domains/novel/conflicts.py`
- Test: `tests/test_novel_import_conflicts.py`

**Interfaces:**
- Consumes: `NovelBaselineDraft`.
- Produces: `ImportConflict` records with `code`, `severity`, `subject`, `values`, `sources`, `resolution_required`。

- [ ] **Step 1: Write known-conflict tests**

```python
def test_conflict_detector_reports_volume_count_and_chapter_count_disagreement():
    issues = detect_import_conflicts(civilization_fixture)
    assert "volume_count_conflict" in {issue.code for issue in issues}
    assert "completed_chapter_count_conflict" in {issue.code for issue in issues}
    assert all(issue.sources for issue in issues)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_novel_import_conflicts.py -q`

Expected: FAIL because detector is missing.

- [ ] **Step 3: Implement explicit conflict rules**

Detect duplicate chapter numbers, contradictory immutable character attributes, conflicting world rules, timeline order errors, open/closed hook disagreements, metadata-vs-filesystem chapter counts and outline version conflicts. Never choose a winner automatically for `high` severity.

- [ ] **Step 4: Run and verify pass**

Run: `python -m pytest tests/test_novel_import_conflicts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add creative_os/domains/novel/conflicts.py tests/test_novel_import_conflicts.py
git commit -m "新增小说导入冲突检测"
```

### Task 5: Add Import Review and Materialization CLI

**Files:**
- Create: `scripts/import_legacy_novel.py`
- Create: `creative_os/importing/materializer.py`
- Test: `tests/test_import_legacy_novel_script.py`
- Modify: `creative_os/novel_project.py`

**Interfaces:**
- Produces CLI phases: `scan`, `report`, `approve`, `materialize`.
- Materializes into `projects/<书名>/.creative_os/import/` and confirmed Knowledge/Memory stores.

- [ ] **Step 1: Write approval-gate tests**

```python
def test_materialize_refuses_unresolved_high_conflicts(tmp_path):
    result = run_cli("materialize", fixture_with_high_conflict, tmp_path)
    assert result.exit_code != 0
    assert not (tmp_path / "projects" / "文明升阶" / "production" / "final_chapters").exists()


def test_materialize_copies_canon_and_keeps_source_unchanged(tmp_path):
    result = run_approved_import(tmp_path)
    assert result.exit_code == 0
    assert (result.project / "production/final_chapters/chapter_001.md").exists()
    assert snapshot_tree(result.source) == result.source_snapshot
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_import_legacy_novel_script.py -q`

Expected: FAIL because CLI and materializer are missing.

- [ ] **Step 3: Implement staged import**

`scan` writes a manifest only under the destination project. `report` writes Markdown and JSON conflict reports. `approve` records actor, accepted canon paths and conflict resolutions. `materialize` copies confirmed canon, creates active project Knowledge, keeps import sources/provenance, and refuses unresolved high-severity conflicts.

- [ ] **Step 4: Run and verify pass**

Run: `python -m pytest tests/test_import_legacy_novel_script.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/import_legacy_novel.py creative_os/importing/materializer.py creative_os/novel_project.py tests/test_import_legacy_novel_script.py
git commit -m "实现半成品小说审批导入"
```

### Task 6: Build the Next-Chapter Continuation Context

**Files:**
- Create: `creative_os/domains/novel/continuation.py`
- Test: `tests/test_novel_continuation.py`

**Interfaces:**
- Consumes: confirmed baseline, last canon chapter, active project Memory/Knowledge and the next outline milestone.
- Produces: `ContinuationTask` and `CompiledContext` for exactly one next chapter.

- [ ] **Step 1: Write continuation tests**

```python
def test_next_chapter_uses_last_canon_state_and_next_outline_goal():
    task, context = build_next_chapter(project)
    assert task.chapter_number == 3
    assert task.previous_chapter == 2
    assert context.contains_source("production/final_chapters/chapter_002.md")
    assert not context.contains_source("fix/第3章 普通人的最后一天.md")


def test_continuation_blocks_when_required_character_state_is_unresolved():
    with pytest.raises(ContinuationBlockedError):
        build_next_chapter(project_with_unresolved_character_conflict)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_novel_continuation.py -q`

Expected: FAIL because continuation builder is missing.

- [ ] **Step 3: Implement continuation task construction**

The task must include chapter number, narrative goal, required facts, forbidden contradictions, open hooks, last-chapter ending state, character states and minimum length. Compile through the generic `ContextCompiler`; never read archive documents directly.

- [ ] **Step 4: Run and verify pass**

Run: `python -m pytest tests/test_novel_continuation.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add creative_os/domains/novel/continuation.py tests/test_novel_continuation.py
git commit -m "生成小说单章接续上下文"
```

### Task 7: Run One-Chapter Continuation Through Quality Gates

**Files:**
- Create: `scripts/continue_novel.py`
- Modify: `creative_os/llm_writer.py`
- Test: `tests/test_continue_novel_script.py`
- Modify: `tests/test_llm_writer.py`

**Interfaces:**
- Consumes: project root, model client and `ContinuationTask`.
- Produces: one draft chapter, review result, candidate Knowledge patch, candidate experience records and chapter status.

- [ ] **Step 1: Write dry-run and one-chapter tests**

```python
def test_dry_run_compiles_context_without_calling_model(fake_client, project):
    result = continue_one_chapter(project, fake_client, dry_run=True)
    assert fake_client.calls == []
    assert result.context_path.exists()


def test_failed_review_does_not_promote_chapter_or_memory(fake_client, project):
    result = continue_one_chapter(project, fake_client, max_attempts=1)
    assert result.status == "fail"
    assert not result.final_chapter_path.exists()
    assert all(item.status == MemoryStatus.CANDIDATE for item in result.experiences)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_continue_novel_script.py tests/test_llm_writer.py -q`

Expected: FAIL because continuation runner is missing.

- [ ] **Step 3: Implement one-chapter runner**

Support `--dry-run`; default to one chapter; write drafts under `.creative_os/llm_writer/drafts`, contexts under `.creative_os/contexts/compiled`, and status under `production/runs/status`. Promote to `production/final_chapters` only after fact, continuity, reader-facing text and minimum-length gates pass.

- [ ] **Step 4: Run and verify pass**

Run: `python -m pytest tests/test_continue_novel_script.py tests/test_llm_writer.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/continue_novel.py creative_os/llm_writer.py tests/test_continue_novel_script.py tests/test_llm_writer.py
git commit -m "打通半成品小说单章续写"
```

### Task 8: Import and Dry-Run Civilization Ascension

**Files:**
- Create: `projects/文明升阶/` through the import CLI, not manual file edits.
- Create: `projects/文明升阶/production/reports/import_report.md`
- Create: `projects/文明升阶/production/reports/continuation_readiness.md`
- Modify: `README.md`

**Interfaces:**
- Uses the real source path only after the user finishes cleanup.

- [ ] **Step 1: Scan the source without materializing**

```powershell
python scripts\import_legacy_novel.py scan --source "D:\田雨\AI写作助手\NovelProject\Novels\文明升阶" --projects-root projects --title "文明升阶"
python scripts\import_legacy_novel.py report --project-root "projects\文明升阶"
```

Expected: source tree remains unchanged; report lists canon candidates, supporting materials, excluded archives, unknown files and conflicts.

- [ ] **Step 2: Review and resolve the import report manually**

Record the accepted official chapter paths and resolutions for volume count, completed chapter count, active outline version and any immutable-character conflicts using:

```powershell
python scripts\import_legacy_novel.py approve --project-root "projects\文明升阶" --actor "tingyu" --decisions "projects\文明升阶\.creative_os\import\decisions.json"
```

Expected: all high-severity conflicts have explicit decisions and actor records.

- [ ] **Step 3: Materialize the approved baseline**

```powershell
python scripts\import_legacy_novel.py materialize --project-root "projects\文明升阶"
```

Expected: only approved chapters enter `production/final_chapters`; approved setting documents become active project Knowledge; excluded files remain provenance-only.

- [ ] **Step 4: Compile a dry-run continuation context**

```powershell
python scripts\continue_novel.py --project-root "projects\文明升阶" --dry-run
```

Expected: identifies the next chapter after the final confirmed canon chapter, contains no archive sources, fits the context budget and writes `continuation_readiness.md`.

- [ ] **Step 5: Run complete verification before any paid model call**

```powershell
python -m pytest -q
python scripts\novel_console.py --project-root "projects\文明升阶"
rg -n "fix/|_archive/|backup/|备份/" "projects\文明升阶\.creative_os\contexts\compiled"
```

Expected: tests pass, console shows imported chapter state, and archive paths are absent from compiled contexts.

- [ ] **Step 6: Commit the importer and reports, excluding generated paid-model prose**

```bash
git add creative_os scripts tests README.md projects/文明升阶/production/reports projects/文明升阶/.creative_os/import
git commit -m "完成文明升阶接续准备验证"
```

## Acceptance Gate

- 旧项目全程保持只读且文件指纹不变。
- 正式正文、设定资料、废稿和未知文件能够明确分类。
- 高风险冲突未经人工解决时禁止续写。
- 每条项目事实都能追踪到来源文件、标题和哈希。
- 接续 Context 不包含废稿或备份内容。
- 第一次运行只处理一章，失败稿不进入正式章节。
- 续写产生的新经验仍是候选状态，必须人工审批。

## Later Stress-Validation Plan

本计划通过后另行编写百万字持续写作压力计划，按 `3章 -> 10章 -> 30章 -> 10万字 -> 30万字 -> 100万字` 设置检查点。核心指标包括事实冲突率、伏笔丢失率、Context 大小、召回准确率、中断恢复率、人工干预率、单章耗时和每万字成本；未达到前一检查点不得直接扩大生成规模。

