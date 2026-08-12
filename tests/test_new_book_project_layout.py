from creative_os.novel_project import create_novel_project


def test_new_book_project_uses_book_title_and_clean_top_level(tmp_path):
    project = create_novel_project(tmp_path / "projects", "雾城回声", author="田雨", genre="悬疑")

    assert project.name == "雾城回声"
    assert (project / "README.md").exists()
    assert (project / "metadata.json").exists()
    assert (project / "production").is_dir()
    assert (project / ".creative_os").is_dir()
    assert not (project / "validation_novel").exists()


def test_new_book_readme_points_to_draft_and_release_locations(tmp_path):
    project = create_novel_project(tmp_path / "projects", "雾城回声")

    readme = (project / "README.md").read_text(encoding="utf-8")

    assert "# 雾城回声" in readme
    assert "production/drafts/final_draft_polished.md" in readme
    assert "releases/雾城回声/book.md" in readme
    assert ".creative_os/" in readme
