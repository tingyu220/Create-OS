from creative_os.validation_runtime import (
    chapter_one_scene_specs,
    seed_validation_knowledge,
    write_chapter_one_artifacts,
    write_first_five_chapters_artifacts,
    write_first_three_chapters_artifacts,
    write_first_ten_chapters_artifacts,
    write_full_draft_artifacts,
    write_full_review_artifacts,
    write_v11_acceptance_artifacts,
    _build_validation_fixture_composed_artifacts as write_composed_final_artifacts,
    validate_reader_facing_text,
    _build_validation_fixture_final_v2_artifacts as write_final_chapter_v2_artifacts,
)


def test_validation_knowledge_seeds_retrievable_design_context():
    store = seed_validation_knowledge()
    task = chapter_one_scene_specs()[0].to_task()

    items = store.find_by_tags(set(task.tags), limit=8)

    assert any(item.id == "kb-character-lin-che" for item in items)
    assert any(item.id == "kb-world-fog-city" for item in items)


def test_chapter_one_artifacts_prove_minimal_writing_loop(tmp_path):
    record = write_chapter_one_artifacts(tmp_path)

    assert record.chapter_id == "chapter-001"
    assert len(record.scene_records) == 3
    assert all(scene.status == "pass" for scene in record.scene_records)
    assert (tmp_path / "drafts" / "chapter_001.md").exists()
    assert (tmp_path / "runs" / "chapter_001_run.json").exists()
    assert "林遥没有离开雾城" in (tmp_path / "drafts" / "chapter_001.md").read_text(encoding="utf-8")
    assert len(list((tmp_path / "contexts").glob("*.json"))) == 3
    assert len(list((tmp_path / "reviews").glob("*_review.md"))) == 3
    assert len(list((tmp_path / "knowledge").glob("*_compiled.json"))) == 3


def test_first_three_chapters_prove_m5_minimal_continuity_checkpoint(tmp_path):
    records = write_first_three_chapters_artifacts(tmp_path)

    assert [record.chapter_id for record in records] == ["chapter-001", "chapter-002", "chapter-003"]
    assert sum(len(record.scene_records) for record in records) == 9
    assert (tmp_path / "reviews" / "m5_chapter_003_continuity_review.md").exists()
    review = (tmp_path / "reviews" / "m5_chapter_003_continuity_review.md").read_text(encoding="utf-8")
    assert "Result\n\nPass" in review
    assert "冷光管 -> 旧灯巷 -> 废弃档案库 -> 回声室" in review


def test_first_five_chapters_prove_character_world_checkpoint(tmp_path):
    records = write_first_five_chapters_artifacts(tmp_path)

    assert [record.chapter_id for record in records] == [
        "chapter-001",
        "chapter-002",
        "chapter-003",
        "chapter-004",
        "chapter-005",
    ]
    assert sum(len(record.scene_records) for record in records) == 15
    review_path = tmp_path / "reviews" / "m5_chapter_005_character_world_review.md"
    assert review_path.exists()
    review = review_path.read_text(encoding="utf-8")
    assert "Result\n\nPass" in review
    assert "冷光显影边界一致" in review


def test_first_ten_chapters_prove_m5_completion_checkpoint(tmp_path):
    records = write_first_ten_chapters_artifacts(tmp_path)

    assert len(records) == 10
    assert sum(len(record.scene_records) for record in records) == 30
    run_path = tmp_path / "runs" / "m5_first_ten_chapters_run.json"
    review_path = tmp_path / "reviews" / "m5_chapter_010_direction_context_review.md"
    assert run_path.exists()
    assert review_path.exists()
    review = review_path.read_text(encoding="utf-8")
    assert "Result\n\nPass" in review
    assert "回声室入口被定位" in review
    assert "进入 M6" in review


def test_full_draft_artifacts_prove_m6_draft_complete(tmp_path):
    records = write_full_draft_artifacts(tmp_path)

    assert len(records) == 36
    assert sum(len(record.scene_records) for record in records) == 108
    assert (tmp_path / "runs" / "m6_full_draft_run.json").exists()
    assert (tmp_path / "drafts" / "full_draft.md").exists()
    review = (tmp_path / "reviews" / "m6_draft_complete_review.md").read_text(encoding="utf-8")
    assert "Result\n\nPass" in review
    assert "36/36" in review
    full_draft = (tmp_path / "drafts" / "full_draft.md").read_text(encoding="utf-8")
    assert "第 36 章：第一盏灯" in full_draft


def test_full_review_artifacts_prove_m7_review_complete(tmp_path):
    run_record = write_full_review_artifacts(tmp_path)

    assert run_record["result"] == "pass"
    assert run_record["chapter_count"] == 36
    assert run_record["scene_count"] == 108
    for name in ["structure", "character", "world", "timeline", "text"]:
        assert (tmp_path / "reviews" / f"m7_{name}_review.md").exists()
    assert (tmp_path / "reports" / "m7_issue_report.md").exists()
    assert (tmp_path / "tasks" / "m7_repair_tasks.json").exists()
    assert (tmp_path / "reviews" / "m7_regression_review.md").exists()
    final_compile = (tmp_path / "drafts" / "final_compile.md").read_text(encoding="utf-8")
    assert "Ready for M8 V1.1 acceptance" in final_compile


def test_v11_acceptance_artifacts_prove_m8_completion(tmp_path):
    run_record = write_v11_acceptance_artifacts(tmp_path)

    assert run_record["result"] == "pass"
    assert run_record["version"] == "V1.1 Production Ready"
    assert run_record["chapter_count"] == 36
    assert run_record["scene_count"] == 108
    for report in [
        "production_report",
        "benchmark_report",
        "v1_gap_list",
        "v2_backlog",
        "v11_acceptance_report",
        "project_summary",
    ]:
        assert (tmp_path / "reports" / f"{report}.md").exists()
    acceptance = (tmp_path / "reports" / "v11_acceptance_report.md").read_text(encoding="utf-8")
    assert "Final Result\n\nPass" in acceptance
    assert "V1.1 Production Ready" in acceptance


def test_composed_final_artifacts_remove_internal_scene_and_system_terms(tmp_path):
    write_full_draft_artifacts(tmp_path)

    record = write_composed_final_artifacts(tmp_path)

    assert record["result"] == "pass"
    assert record["chapter_count"] == 36
    final_chapter = (tmp_path / "final_chapters" / "chapter_002.md").read_text(encoding="utf-8")
    final_draft = (tmp_path / "drafts" / "final_draft_polished.md").read_text(encoding="utf-8")
    assert "## Scene" not in final_chapter
    assert "Context" not in final_chapter
    assert "新增事实" not in final_chapter
    assert "三个字：旧灯巷" in final_chapter
    assert "四个字：旧灯巷" not in final_chapter
    assert "## Scene" not in final_draft
    assert "Context" not in final_draft
    assert "新增事实" not in final_draft


def test_reader_facing_quality_gate_rejects_system_and_template_language():
    text = "## 废弃档案库外门\n这之后，线索没有停在原地，而是顺着雾城更深的暗处继续延伸。\nContext\n本章前段，目标很清楚。\n林澈把前几章留下的线索重新排了一遍。\n最终，局面被迫向前推进：局面推进到：发现真相。\n\n重复段落用于验证长段落重复会被门禁拦截。\n\n重复段落用于验证长段落重复会被门禁拦截。"

    issues = validate_reader_facing_text(text)

    assert "repeated_transition_opener" in issues
    assert "system_term_context" in issues
    assert "reader_subheading" in issues
    assert "template_phrase_benzhangqianduan" in issues
    assert "template_phrase_mubiaohenqingchu" in issues
    assert "template_phrase_qianjizhang" in issues
    assert "template_phrase_jumianbeipo" in issues
    assert "template_phrase_jumianjintuidao" in issues
    assert "duplicate_reader_paragraph" in issues


def test_reader_facing_quality_gate_rejects_reversed_dialogue_reference():
    text = "“所以我们找到了你。”林子轩说。\n\n“不是找到了我。”林正弘说，“是在你出生前，我们就知道你可能是唯一解。”"

    issues = validate_reader_facing_text(text)

    assert "dialogue_reference_mismatch" in issues


def test_reader_facing_quality_gate_rejects_wrong_father_child_gender():
    text = "林正弘看着林子轩，像是想把这些字在女儿面前摆稳一些。"

    assert "character_relation_mismatch" in validate_reader_facing_text(text)


def test_reader_facing_quality_gate_rejects_truncated_sentence_ending():
    text = "# 第25章：家属服务厅\n\n老周抬起头说：“我这一班，夜"

    assert "truncated_sentence_ending" in validate_reader_facing_text(text)


def test_final_chapter_v2_artifacts_remove_ai_flavor_and_scene_stitching(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)

    record = write_final_chapter_v2_artifacts(tmp_path)

    assert record["result"] == "pass"
    assert record["chapter_count"] == 36
    chapter_002 = (tmp_path / "final_chapters_v2" / "chapter_002.md").read_text(encoding="utf-8")
    full_text = (tmp_path / "drafts" / "final_draft_v2.md").read_text(encoding="utf-8")
    banned = [
        "## ",
        "Context",
        "Task",
        "新增事实",
        "前几章",
        "本章前段",
        "本章中段",
        "本章后段",
        "目标很清楚",
        "对方没有立刻让路",
        "局面被迫向前推进",
        "局面推进到",
        "关键证据被确认",
        "如果灯不会制造灾难",
        "这之后，线索没有停在原地，而是顺着雾城更深的暗处继续延伸。",
    ]
    for phrase in banned:
        assert phrase not in chapter_002
        assert phrase not in full_text
    assert "三个字：旧灯巷" in chapter_002


def test_final_chapter_v2_promotes_clean_reader_copy_to_canonical_paths(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)

    record = write_final_chapter_v2_artifacts(tmp_path)

    assert record["result"] == "pass"
    canonical_chapter = (tmp_path / "final_chapters" / "chapter_004.md").read_text(encoding="utf-8")
    canonical_draft = (tmp_path / "drafts" / "final_draft_polished.md").read_text(encoding="utf-8")
    for phrase in ["## ", "前几章", "Scene", "Context", "新增事实", "对方没有立刻让路", "局面推进到", "关键证据被确认", "林澈和林澈", "外外", "为了林澈见到"]:
        assert phrase not in canonical_chapter
        assert phrase not in canonical_draft
    assert "档案库被清理过的痕迹" in canonical_chapter


def test_final_chapter_v2_preserves_reader_draft_volume(tmp_path):
    write_v11_acceptance_artifacts(tmp_path)

    record = write_final_chapter_v2_artifacts(tmp_path)

    assert record["result"] == "pass"
    chapter_004 = (tmp_path / "final_chapters" / "chapter_004.md").read_text(encoding="utf-8")
    full_text = (tmp_path / "drafts" / "final_draft_polished.md").read_text(encoding="utf-8")
    assert _count_chinese_chars(chapter_004) >= 1200
    assert _count_chinese_chars(full_text) >= 43000


def _count_chinese_chars(text: str) -> int:
    return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
