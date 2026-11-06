import json

from creative_os.web_workspace import WriterWebAdapter
from creative_os.writer_draft_store import WriterDraftStore


def test_writer_context_separates_formal_chapters_drafts_and_projection(tmp_path):
    final = tmp_path / "production" / "final_chapters"
    final.mkdir(parents=True)
    (final / "chapter_001.md").write_text("正文", encoding="utf-8")
    (final / "chapter_003.md").write_text("第三章正文", encoding="utf-8")
    WriterDraftStore(tmp_path).save(2, "工作稿", actor="作者", expected_version=None)

    payload = json.loads(WriterWebAdapter(tmp_path, "p").read_context_summary())

    assert {key: payload[key] for key in ("project_id", "formal_chapter_count", "formal_chapters", "working_draft_count", "working_draft_chapters")} == {
        "project_id": "p",
        "formal_chapter_count": 2,
        "formal_chapters": [1, 3],
        "working_draft_count": 1,
        "working_draft_chapters": [2],
    }


def test_writer_directory_preserves_heading_title_and_combined_sources(tmp_path):
    final = tmp_path / "production/final_chapters"; final.mkdir(parents=True)
    (final / "chapter_001.md").write_text("# 第1章 钟声\n正式正文", encoding="utf-8")
    WriterDraftStore(tmp_path).save(1, "# 第1章 海上的钟\n工作稿正文", actor="作者")
    payload = json.loads(WriterWebAdapter(tmp_path, "p").read_context_summary())
    assert len(payload["chapters"]) == 1
    chapter = payload["chapters"][0]
    assert chapter["has_formal"] and chapter["has_draft"] and "海上的钟" in chapter["title"]
