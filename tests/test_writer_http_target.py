from creative_os.workspace_command import _valid_target


def test_writer_target_accepts_project_and_positive_chapter_number():
    assert _valid_target({"project_id": "p", "chapter_number": 79})
    assert not _valid_target({"project_id": "p", "chapter_number": 0})

