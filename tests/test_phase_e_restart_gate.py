from pathlib import Path
from tests.fakes.fake_chapter_writer import FakeChapterWriter

def test_fake_writer_restart_is_idempotent_and_tampered_artifact_blocks(tmp_path: Path):
    writer=FakeChapterWriter(tmp_path)
    first=writer.prepare(1)
    assert writer.resume(1)==first
    assert writer.calls==1
    try: writer.verify_artifact({"chapter":1,"artifact_hash":"bad"})
    except ValueError: pass
    else: assert False
