import json

from creative_os.web_workspace import WriterWebAdapter
from creative_os.writer_draft_store import WriterDraftStore


def test_writer_context_separates_formal_chapters_drafts_and_projection(tmp_path):
    final = tmp_path / "production" / "final_chapters"
    final.mkdir(parents=True)
    (final / "chapter_001.md").write_text("正文", encoding="utf-8")
    WriterDraftStore(tmp_path).save(2, "工作稿", actor="作者", expected_version=None)

    payload = json.loads(WriterWebAdapter(tmp_path, "p").read_context_summary())

    assert payload == {"project_id": "p", "formal_chapter_count": 1, "working_draft_count": 1}

