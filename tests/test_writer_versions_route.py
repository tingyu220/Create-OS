from pathlib import Path

from creative_os.web_workspace import WriterWebAdapter
from creative_os.writer_draft_store import WriterDraftStore


def test_writer_versions_endpoint_payload_is_stable(tmp_path: Path):
    store = WriterDraftStore(tmp_path)
    first = store.save(79, "一", actor="作者", expected_version=None)
    store.save(79, "二", actor="作者", expected_version=first.version)
    payload = WriterWebAdapter(tmp_path, "p").read_versions(79).decode("utf-8")
    assert '"version": 2' in payload
    assert '"version": 1' in payload

