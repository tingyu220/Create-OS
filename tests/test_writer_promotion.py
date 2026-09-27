from creative_os.writer_draft_store import WriterDraftStore


def test_promote_working_draft_writes_formal_chapter_only_when_explicitly_requested(tmp_path):
    store = WriterDraftStore(tmp_path)
    store.save(79, "# 第79章\n工作稿正文", actor="作者", expected_version=None)

    result = store.promote(79, version_number=1, actor="作者", expected_version=1)

    assert result.version == 1
    assert (tmp_path / "production" / "final_chapters" / "chapter_079.md").read_text(encoding="utf-8") == "# 第79章\n工作稿正文"


def test_promote_does_not_replace_formal_chapter_on_version_conflict(tmp_path):
    store = WriterDraftStore(tmp_path)
    store.save(79, "新工作稿", actor="作者", expected_version=None)
    formal = tmp_path / "production" / "final_chapters" / "chapter_079.md"
    formal.parent.mkdir(parents=True)
    formal.write_text("旧正式稿", encoding="utf-8")

    try:
        store.promote(79, version_number=1, actor="作者", expected_version=None)
    except ValueError as error:
        assert str(error) == "version_conflict"
    else:
        raise AssertionError("expected version conflict")
    assert formal.read_text(encoding="utf-8") == "旧正式稿"
