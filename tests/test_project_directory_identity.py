"""稳定项目身份与目录名解耦；只使用临时作品，禁止真实模型。"""

from http.client import HTTPConnection
import json
from threading import Thread
from urllib.parse import quote

import pytest

from creative_os.novel_project_command import NovelProjectCreator
from creative_os.project_catalog import ProjectCatalog
from creative_os.project_registry import ProjectRegistry, validated_project
from creative_os.web_workspace import create_server, WriterWebAdapter
from creative_os.workspace_recent_store import WorkspaceRecentStore
from test_story_http import EmptyWorkspace


def snapshot(root):
    return {str(path.relative_to(root)): (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
            for path in root.rglob("*")}


def seed(root, folder, stable_id):
    path = NovelProjectCreator(root).create(folder, "隔离想法", operation_id=folder, story_mode=False)
    metadata = json.loads((path / "project.json").read_text(encoding="utf-8"))
    metadata["id"] = stable_id
    (path / "project.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    (path / "production/final_chapters/chapter_001.md").write_text(folder + "隔离正文", encoding="utf-8")
    return path


def forbidden():
    raise AssertionError("不得构造真实客户端")


def test_stable_ids_resolve_three_named_books_without_writes(tmp_path):
    pairs = [("雾城回声", "novel-validation-001"), ("末班钟表店", "novel-domain-validation"), ("文明升阶", "文明升阶")]
    roots = [seed(tmp_path, name, stable_id) for name, stable_id in pairs]
    before = snapshot(tmp_path)
    catalog = ProjectCatalog(tmp_path).list_projects()
    assert catalog["total"] == 3 and catalog["warnings"] == []
    assert {item["project_id"] for item in catalog["items"]} == {stable_id for _, stable_id in pairs}
    for (name, stable_id), root in zip(pairs, roots):
        assert validated_project(tmp_path, stable_id)[0] == root
        assert ProjectCatalog(tmp_path).project(stable_id)["title"] == name
        if name != stable_id:
            with pytest.raises(ValueError): validated_project(tmp_path, name)
    assert snapshot(tmp_path) == before


def test_duplicate_identity_is_rejected_without_hiding_unrelated_book(tmp_path):
    seed(tmp_path, "甲书", "duplicate"); seed(tmp_path, "乙书", "duplicate"); seed(tmp_path, "正常书", "healthy")
    before = snapshot(tmp_path)
    with pytest.raises(ValueError): validated_project(tmp_path, "duplicate")
    catalog = ProjectCatalog(tmp_path).list_projects()
    assert [item["project_id"] for item in catalog["items"]] == ["healthy"]
    assert len(catalog["warnings"]) == 2
    assert snapshot(tmp_path) == before


def test_casefold_duplicate_ids_cannot_select_one_arbitrarily(tmp_path):
    seed(tmp_path, "甲书", "Stable-A"); seed(tmp_path, "乙书", "stable-a")
    with pytest.raises(ValueError): validated_project(tmp_path, "Stable-A")
    with pytest.raises(ValueError): validated_project(tmp_path, "stable-a")
    assert ProjectCatalog(tmp_path).list_projects()["items"] == []


@pytest.mark.parametrize("identity", [None, [], "", ".", "..", "../outside", "other\\book", "bad\nidentity", " padded "])
def test_invalid_metadata_identity_is_isolated_without_writes(tmp_path, identity):
    root = seed(tmp_path, "异常书", "stable-a")
    metadata = json.loads((root / "project.json").read_text(encoding="utf-8")); metadata["id"] = identity
    (root / "project.json").write_text(json.dumps(metadata), encoding="utf-8")
    before = snapshot(tmp_path)
    result = ProjectCatalog(tmp_path).list_projects()
    assert result["items"] == [] and len(result["warnings"]) == 1
    assert snapshot(tmp_path) == before


def test_directory_alias_cannot_occupy_other_stable_identity(tmp_path):
    seed(tmp_path, "stable-b", "stable-a"); seed(tmp_path, "乙书", "stable-b")
    with pytest.raises(ValueError): validated_project(tmp_path, "stable-b")
    assert ProjectCatalog(tmp_path).list_projects()["items"] == []


def test_creator_rejects_existing_stable_id_before_creating_directory(tmp_path):
    seed(tmp_path, "旧目录", "新书")
    before = snapshot(tmp_path)
    with pytest.raises((ValueError, FileExistsError)):
        NovelProjectCreator(tmp_path).create("新书", "新想法", operation_id="new")
    assert snapshot(tmp_path) == before and not (tmp_path / "新书").exists()


def test_registry_register_uses_metadata_identity_and_detects_stale_directory(tmp_path):
    root = seed(tmp_path, "甲书", "stable-a")
    registry = ProjectRegistry(tmp_path, client_factory=forbidden)
    try:
        entry = registry.get("stable-a")
        assert entry["agent_runtime"].project_id == "stable-a" and entry["agent_runtime"].root == root
        other = ProjectRegistry(tmp_path, client_factory=forbidden)
        other.register("stable-a", entry)
        moved = tmp_path / "甲书新目录"; root.rename(moved)
        with pytest.raises(ValueError, match="restart_required"):
            registry.get("stable-a")
    finally:
        registry.close()


def test_recent_locations_keep_stable_identity_after_directory_change(tmp_path):
    root = seed(tmp_path, "旧目录", "stable-a")
    store = WorkspaceRecentStore(tmp_path)
    store.record("stable-a", "writer", 1, source="formal")
    root.rename(tmp_path / "中文书名")
    before = snapshot(tmp_path)
    assert store.read()[0]["project_id"] == "stable-a"
    assert ProjectCatalog(tmp_path).project("stable-a")["entry_url"] == "/p/stable-a/"
    assert snapshot(tmp_path) == before


def test_scoped_http_and_default_writer_keep_three_stable_identities(tmp_path):
    pairs = [("雾城回声", "novel-validation-001"), ("末班钟表店", "novel-domain-validation"), ("文明升阶", "文明升阶")]
    roots = [seed(tmp_path, *pair) for pair in pairs]
    registry = ProjectRegistry(tmp_path, client_factory=forbidden)
    server = create_server(EmptyWorkspace(None, pairs[2][1]), writer_adapter=WriterWebAdapter(roots[2], pairs[2][1]), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True); worker.start()
    def request(method, path, body=None):
        connection = HTTPConnection(*server.server_address, timeout=5)
        connection.request(method, path, body=json.dumps(body) if body else None, headers={"Content-Type": "application/json"})
        response = connection.getresponse(); raw = response.read(); status = response.status
        value = json.loads(raw) if raw else {"location": response.getheader("Location")}; connection.close()
        return status, value
    try:
        before = snapshot(tmp_path)
        for name, stable_id in pairs:
            prefix = "/p/" + quote(stable_id)
            status, context = request("GET", prefix + "/api/writer/context")
            assert status == 200 and context["project_id"] == stable_id
            status, chapter = request("GET", prefix + "/api/writer/chapters/1?source=formal")
            assert status == 200 and chapter["chapter"]["project_id"] == stable_id
            assert chapter["chapter"]["content"] == name + "隔离正文"
            assert request("GET", prefix + "/")[0] == 302
        assert request("GET", "/api/writer/chapters/1?source=formal")[1]["chapter"]["project_id"] == "文明升阶"
        assert snapshot(tmp_path) == before
        status, _ = request("POST", "/api/projects/recent", {"project_id": "novel-validation-001", "page": "writer", "chapter_number": 1, "source": "formal"})
        assert status == 200
        recent = request("GET", "/api/projects/recent")[1]["items"][0]
        assert recent["project_id"] == "novel-validation-001" and recent["title"] == "雾城回声"
        assert "/p/novel-validation-001/writer" in recent["url"]
    finally:
        server.shutdown(); server.server_close(); worker.join(); registry.close()


def test_create_response_uses_metadata_id_even_when_directory_differs(tmp_path, monkeypatch):
    root = seed(tmp_path, "中文书名", "stable-created")
    registry = ProjectRegistry(tmp_path, client_factory=forbidden)
    monkeypatch.setattr(registry.creator, "create", lambda *args, **kwargs: root)
    server = create_server(EmptyWorkspace(None, "none"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True); worker.start()
    try:
        connection = HTTPConnection(*server.server_address, timeout=5)
        connection.request("POST", "/api/projects/create", body=json.dumps({"title": "中文书名", "idea": "想法", "operation_id": "create"}), headers={"Content-Type": "application/json"})
        response = connection.getresponse(); data = json.loads(response.read()); connection.close()
        assert response.status == 201 and data["project_id"] == "stable-created"
    finally:
        server.shutdown(); server.server_close(); worker.join(); registry.close()
