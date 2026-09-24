from creative_os.web_command_dto import decode_web_command
from creative_os.writer_command import WriterDraftCommandHandler
from creative_os.writer_draft_store import WriterDraftStore


def test_web_decoder_accepts_writer_save_command():
    request = decode_web_command({
        "command_id": "save_writer_draft", "request_id": "r1", "actor": "作者",
        "target": {"project_id": "p", "chapter_number": 79}, "payload": {"content": "正文"},
        "expected_version": None, "idempotency_key": "k1",
    })
    assert request.command_id == "save_writer_draft"


def test_writer_handler_saves_only_working_draft(tmp_path):
    store = WriterDraftStore(tmp_path)
    handler = WriterDraftCommandHandler("p", store)
    request = decode_web_command({
        "command_id": "save_writer_draft", "request_id": "r1", "actor": "作者",
        "target": {"project_id": "p", "chapter_number": 79}, "payload": {"content": "正文"},
        "expected_version": None, "idempotency_key": "k1",
    })
    refs = handler(request)
    assert refs == ("writer-draft:79:1",)
    assert store.current(79)[1] == "正文"

