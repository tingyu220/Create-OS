import json

from creative_os.web_workspace import WriterWebAdapter
from creative_os.writer_draft_store import WriterDraftStore


def test_writer_diff_compares_formal_text_with_current_working_draft(tmp_path):
    final = tmp_path / "production" / "final_chapters"
    final.mkdir(parents=True)
    (final / "chapter_079.md").write_text("旧正文\n", encoding="utf-8")
    WriterDraftStore(tmp_path).save(79, "新正文\n", actor="作者", expected_version=None)

    payload = json.loads(WriterWebAdapter(tmp_path, "p").read_diff(79, None, None))

    assert "-旧正文" in payload["diff"]
    assert "+新正文" in payload["diff"]
