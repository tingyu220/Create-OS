from creative_os.creative_context import CreativeContextBuilder


def test_creative_context_builder_collects_formal_draft_and_adjacent_sources(tmp_path):
    final = tmp_path / "production" / "final_chapters"
    final.mkdir(parents=True)
    for number in (77, 78):
        (final / f"chapter_{number:03d}.md").write_text(f"第{number}章正文", encoding="utf-8")
    draft = tmp_path / ".creative_os" / "writer" / "drafts"
    draft.mkdir(parents=True)
    (draft / "chapter_079.jsonl").write_text('{"version": 1, "content": "第79章工作稿"}\n', encoding="utf-8")

    context = CreativeContextBuilder(tmp_path).build("这一章我觉得有问题，你自己检查一下。", 79)

    assert context.target_chapter == 79
    assert context.current_draft == "第79章工作稿"
    assert context.recent_chapters == (77, 78)
    assert "production/final_chapters/chapter_078.md" in context.source_refs


def test_creative_context_builder_does_not_create_domain_facts(tmp_path):
    context = CreativeContextBuilder(tmp_path).build("分析这一章", 79)

    assert context.observations == ()
    assert context.decision is not None
    assert context.decision.intent == "分析这一章"


def test_creative_context_builder_reads_current_formal_chapter(tmp_path):
    final = tmp_path / "production" / "final_chapters"
    final.mkdir(parents=True)
    (final / "chapter_079.md").write_text("当前正式正文", encoding="utf-8")

    context = CreativeContextBuilder(tmp_path).build("检查本章", 79)

    assert context.current_formal == "当前正式正文"
    assert "production/final_chapters/chapter_079.md" in context.source_refs
