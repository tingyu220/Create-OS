from creative_os.novel_project import create_novel_project, sanitize_project_folder_name


def test_sanitize_project_folder_name_keeps_chinese_book_title():
    assert sanitize_project_folder_name("雾城回声") == "雾城回声"


def test_sanitize_project_folder_name_removes_windows_forbidden_chars():
    assert sanitize_project_folder_name("雾城:回声?") == "雾城回声"


def test_sanitize_project_folder_name_rejects_empty_title():
    try:
        sanitize_project_folder_name(" :?* ")
    except ValueError as exc:
        assert "title" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_create_novel_project_uses_title_as_project_folder(tmp_path):
    project_path = create_novel_project(tmp_path / "projects", "雾城回声", author="田雨", genre="悬疑")

    assert project_path == tmp_path / "projects" / "雾城回声"
    assert (project_path / "project.json").exists()
    assert (project_path / "metadata.json").exists()
    assert (project_path / "production_log.jsonl").exists()
    assert (project_path / "production" / "drafts").is_dir()
    assert (project_path / "production" / "final_chapters").is_dir()
    assert (project_path / ".creative_os" / "llm_writer").is_dir()
