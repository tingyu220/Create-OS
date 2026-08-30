from creative_os.domains.novel_chapter_memory import compile_chapter_candidates, save_chapter_candidates


def test_passed_chapter_generates_four_project_memory_candidates(tmp_path):
    project = tmp_path / "文明升阶"
    chapter = project / "production/final_chapters/chapter_003.md"
    chapter.parent.mkdir(parents=True)
    chapter.write_text("# 第3章\n林子轩见到林正弘。\n\n他们决定回家。", encoding="utf-8")

    candidates = compile_chapter_candidates(project, 3)

    assert [item.id for item in candidates] == ["chapter-003-summary", "chapter-003-characters", "chapter-003-events", "chapter-003-hooks"]
    assert all(item.status == "candidate" and item.scope_id == "文明升阶" for item in candidates)
    assert save_chapter_candidates(project, 3)
