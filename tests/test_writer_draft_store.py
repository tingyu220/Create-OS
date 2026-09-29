import pytest

from creative_os.writer_draft_store import DraftConflictError, WriterDraftStore


def test_draft_store_versions_and_conflict(tmp_path):
    store = WriterDraftStore(tmp_path)

    first = store.save(79, "第一版正文", actor="作者", expected_version=None)
    second = store.save(79, "第二版正文", actor="作者", expected_version=first.version)

    assert first.version == 1
    assert second.version == 2
    assert store.current(79)[1] == "第二版正文"
    with pytest.raises(DraftConflictError):
        store.save(79, "过期正文", actor="作者", expected_version=1)


def test_draft_store_restore_creates_new_version(tmp_path):
    store = WriterDraftStore(tmp_path)
    first = store.save(79, "第一版正文", actor="作者", expected_version=None)
    store.save(79, "第二版正文", actor="作者", expected_version=first.version)

    restored = store.restore(79, 1, actor="作者", expected_version=2)

    assert restored.version == 3
    assert store.current(79)[1] == "第一版正文"


def test_draft_store_does_not_create_version_when_content_is_unchanged(tmp_path):
    store = WriterDraftStore(tmp_path)

    first = store.save(79, "同一版正文", actor="作者", expected_version=None)
    duplicate = store.save(79, "同一版正文", actor="作者", expected_version=first.version)

    assert duplicate.version == first.version
    assert len(store.versions(79)) == 1
