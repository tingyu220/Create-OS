import json

from creative_os.web_workspace import WriterWebAdapter
from creative_os.writer_draft_store import WriterDraftStore


def test_writer_can_read_formal_and_working_draft_separately(tmp_path):
    final = tmp_path / "production" / "final_chapters"
    final.mkdir(parents=True)
    (final / "chapter_079.md").write_text("正式正文", encoding="utf-8")
    WriterDraftStore(tmp_path).save(79, "工作稿正文", actor="作者", expected_version=None)
    adapter = WriterWebAdapter(tmp_path, "p")

    formal = json.loads(adapter.read_chapter(79, source="formal"))
    draft = json.loads(adapter.read_chapter(79, source="draft"))

    assert formal["chapter"]["content"] == "正式正文"
    assert formal["chapter"]["source"]["role"] == "canonical"
    assert draft["chapter"]["content"] == "工作稿正文"
    assert draft["chapter"]["source"]["role"] == "working_draft"


def test_writer_auto_view_prefers_formal_chapter_when_both_sources_exist(tmp_path):
    final = tmp_path / "production" / "final_chapters"
    final.mkdir(parents=True)
    (final / "chapter_001.md").write_text("正式正文", encoding="utf-8")
    WriterDraftStore(tmp_path).save(1, "验收工作稿", actor="作者", expected_version=None)

    payload = json.loads(WriterWebAdapter(tmp_path, "p").read_chapter(1))

    assert payload["chapter"]["content"] == "正式正文"
    assert payload["chapter"]["source"]["role"] == "canonical"
