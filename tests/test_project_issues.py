import json

from creative_os.project_issues import ProjectIssuesQuery


def test_issues_keep_counts_and_page_metadata(tmp_path):
    project = tmp_path / "technical_name"
    project.mkdir()
    (project / "project.json").write_text(json.dumps({"id": "book-1", "name": "中文书"}, ensure_ascii=False), encoding="utf-8")
    result = ProjectIssuesQuery(tmp_path).read(limit=20)
    assert result["checked_projects"] == 1
    assert result["catalog_revision"]
    issue = next(item for item in result["issues"] if item["code"] == "directory_name_mismatch")
    assert issue["project_id"] == "book-1"
    assert issue["known_counts"] == {"formal": 0, "draft": 0, "candidate": 0}
    assert issue["actions"] == ["preview_migration"]


def test_bad_project_does_not_hide_healthy_project(tmp_path):
    healthy = tmp_path / "healthy"
    healthy.mkdir()
    (healthy / "project.json").write_text(json.dumps({"id": "ok", "name": "好书"}, ensure_ascii=False), encoding="utf-8")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "project.json").write_text("not-json", encoding="utf-8")
    result = ProjectIssuesQuery(tmp_path).read()
    assert any(item["project_id"] == "ok" for item in result["issues"])
    assert any(item["code"] == "project_unavailable" for item in result["issues"])


def test_pagination_checks_only_page_and_duplicate_ids_keep_distinct_issue_ids(tmp_path, monkeypatch):
    for name in ("a", "b", "c"):
        path = tmp_path / name
        path.mkdir()
        (path / "project.json").write_text(json.dumps({"id": name, "name": "中文书"}), encoding="utf-8")
    from creative_os.author_home_query import AuthorHomeQuery
    original = AuthorHomeQuery.read
    checked = []
    def read(query):
        checked.append(query.root.name)
        return original(query)
    monkeypatch.setattr(AuthorHomeQuery, "read", read)
    value = ProjectIssuesQuery(tmp_path).read(offset=1, limit=1)
    assert checked == ["b"]
    assert value["checked_projects"] == 1 and value["total_projects"] == 3
    assert value["next_offset"] == 2
    for name in ("a", "b"):
        (tmp_path / name / "project.json").write_text(json.dumps({"id": "duplicate", "name": "同名"}), encoding="utf-8")
    warnings = [item for item in ProjectIssuesQuery(tmp_path).read()["items"] if item["code"] == "project_identity_ambiguous"]
    assert len(warnings) == 2 and len({row["issue_id"] for row in warnings}) == 2
