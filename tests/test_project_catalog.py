"""书架只读目录，摘要按页读取且不装配运行时。"""

import json
import os
import pytest
from creative_os.project_catalog import ProjectCatalog
from creative_os.novel_project_command import NovelProjectCreator
from creative_os.workspace_command import CommandStoreError


def snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns) for path in root.rglob("*") if path.is_file() and not path.is_symlink()}


def book(root, title):
    return NovelProjectCreator(root).create(title, "真实想法", operation_id=title)


def test_catalog_discovers_books_uses_real_summary_and_never_runtime(tmp_path, monkeypatch):
    from creative_os.writer_draft_store import WriterDraftStore
    first, second, third = [book(tmp_path, title) for title in ("海上的钟", "旧书", "无最近记录")]
    WriterDraftStore(second).save(4, "工作稿正文不得进入目录", actor="作者")
    def forbidden(*args, **kwargs):
        raise AssertionError("目录不可装配 Runtime")
    monkeypatch.setattr("creative_os.project_registry.ProjectRegistry.get", forbidden)
    monkeypatch.setattr("creative_os.project_registry.WriterAgentRuntime", forbidden)
    before = snapshot(tmp_path)
    result = ProjectCatalog(tmp_path).list_projects()
    assert result["total"] == 3 and len(result["items"]) == 3
    item = next(item for item in result["items"] if item["project_id"] == second.name)
    assert item["title"] == "旧书" and item["counts"]["draft"] == 1
    assert item["entry_url"].startswith("/p/")
    assert "工作稿正文不得进入目录" not in json.dumps(result, ensure_ascii=False)
    assert snapshot(tmp_path) == before


def test_catalog_search_paging_reads_only_selected_summaries(tmp_path, monkeypatch):
    for index in range(6):
        book(tmp_path, f"作品{index}")
    calls = []
    from creative_os.author_home_query import AuthorHomeQuery
    original = AuthorHomeQuery.read
    def read(query):
        calls.append(query.project_id)
        return original(query)
    monkeypatch.setattr(AuthorHomeQuery, "read", read)
    result = ProjectCatalog(tmp_path).list_projects("作品", offset=2, limit=2)
    assert result["total"] == 6 and [item["project_id"] for item in result["items"]] == ["作品2", "作品3"]
    assert calls == ["作品2", "作品3"]
    assert ProjectCatalog(tmp_path).list_projects("不存在")["items"] == []


def test_bad_entries_do_not_hide_healthy_books(tmp_path):
    book(tmp_path, "有效作品")
    bad = tmp_path / "损坏作品"; bad.mkdir(); (bad / "project.json").write_text("{bad", encoding="utf-8")
    mismatch = tmp_path / "错名"; mismatch.mkdir(); (mismatch / "project.json").write_text('{"id":"../other"}', encoding="utf-8")
    result = ProjectCatalog(tmp_path).list_projects()
    assert result["total"] == 1 and result["items"][0]["project_id"] == "有效作品"
    assert len(result["warnings"]) == 2


def test_linked_project_outside_root_is_rejected(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir(); (outside / "project.json").write_text('{"id":"逃逸"}', encoding="utf-8")
    try:
        os.symlink(outside, tmp_path / "逃逸", target_is_directory=True)
    except OSError:
        pytest.skip("当前账户不能创建符号链接")
    assert ProjectCatalog(tmp_path).list_projects()["total"] == 0
    assert ProjectCatalog(tmp_path).list_projects()["warnings"]


@pytest.mark.parametrize("options", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": True}, {"query": []}])
def test_catalog_invalid_parameters(tmp_path, options):
    with pytest.raises(ValueError):
        ProjectCatalog(tmp_path).list_projects(**options)


def test_missing_root_is_unavailable_not_empty(tmp_path):
    with pytest.raises(OSError):
        ProjectCatalog(tmp_path / "missing").list_projects()


@pytest.mark.parametrize("error", [AttributeError("bad shape"), KeyError("missing"), ValueError("invalid"), OSError("unreadable"), CommandStoreError("command_store_corrupt")])
def test_summary_failure_keeps_healthy_book_and_marks_unknown(tmp_path, monkeypatch, error):
    book(tmp_path, "healthy"); book(tmp_path, "bad-summary")
    from creative_os.author_home_query import AuthorHomeQuery
    original = AuthorHomeQuery.read
    def read(self):
        if self.project_id == "bad-summary": raise error
        return original(self)
    monkeypatch.setattr(AuthorHomeQuery, "read", read)
    before = snapshot(tmp_path)
    result = ProjectCatalog(tmp_path).list_projects()
    healthy = next(item for item in result["items"] if item["project_id"] == "healthy")
    bad = next(item for item in result["items"] if item["project_id"] == "bad-summary")
    assert healthy["status"] == "fresh"
    assert bad["status"] == "partial" and bad["counts"] == {"formal": None, "draft": None, "candidate": None}
    assert bad["notices"] and result["warnings"]
    assert snapshot(tmp_path) == before


def test_candidate_resume_preserves_existing_working_draft(tmp_path, monkeypatch):
    project = book(tmp_path, "候选与双稿")
    monkeypatch.setattr("creative_os.project_catalog.AuthorHomeQuery.read", lambda self: {
        "resume": {"chapter_number": 1, "source": "candidate"},
        "chapters": [{"chapter_number": 1, "has_draft": True, "has_formal": True}],
        "counts": {"draft": 1, "formal": 1, "candidate": 1}, "status": "fresh", "notices": [],
    })
    assert ProjectCatalog(tmp_path).project(project.name)["default_location"] == {
        "page": "writer", "chapter_number": 1, "source": "draft"}


def test_confirmed_story_without_manuscript_has_explicit_writer_entry(tmp_path):
    from creative_os.story_architecture_store import StoryArchitectureStore
    project = book(tmp_path, "已确认设定")
    store = StoryArchitectureStore(project, project.name)
    candidate = store.propose(store.session_id, [{"key": "core", "title": "核心", "text": "已确认的事实"}], [],
                              expected_revision=0, actor="验收", operation_id="candidate")
    store.confirm(store.session_id, candidate["revision"], candidate["hash"], expected_confirmed_version=0, actor="验收", operation_id="confirm")
    before = snapshot(tmp_path)
    assert ProjectCatalog(tmp_path).project(project.name)["default_location"] == {
        "page": "writer", "chapter_number": 1, "source": "auto"}
    assert snapshot(tmp_path) == before
