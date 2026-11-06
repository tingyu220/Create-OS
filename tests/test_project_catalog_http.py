"""目录 HTTP Query 不装配 Runtime，也不产生文件。"""

from http.client import HTTPConnection
import json
from threading import Thread
import pytest
from creative_os.project_registry import ProjectRegistry
from creative_os.web_workspace import create_server
from test_story_http import EmptyWorkspace
from test_project_catalog import book, snapshot


@pytest.fixture
def catalog_api(tmp_path, monkeypatch):
    book(tmp_path, "现有作品")
    registry = ProjectRegistry(tmp_path)
    monkeypatch.setattr(registry, "get", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("目录不得装配 Runtime")))
    server = create_server(EmptyWorkspace(None, "none"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True); worker.start()
    def request(method, path, payload=None):
        connection = HTTPConnection(*server.server_address, timeout=5); connection.request(method, path, body=json.dumps(payload) if payload is not None else None, headers={"Content-Type": "application/json"})
        response = connection.getresponse(); raw = response.read(); data = json.loads(raw) if raw else {"location": response.getheader("Location")}; connection.close()
        return response.status, data
    get = lambda path: request("GET", path)
    get.post = lambda path, payload: request("POST", path, payload)
    yield get, tmp_path
    server.shutdown(); server.server_close(); worker.join(); registry.close()


def test_catalog_query_and_bad_parameters_never_write(catalog_api):
    get, root = catalog_api
    before = snapshot(root)
    status, data = get("/api/projects")
    assert status == 200 and data["total"] == 1
    for query in ("limit=0", "offset=-1", "limit=101", "limit=bad", "query=a&query=b", "unknown=x"):
        assert get("/api/projects?" + query)[0] == 400
    assert snapshot(root) == before


def test_recent_get_is_readonly_and_only_valid_post_records(catalog_api):
    get, root = catalog_api
    before = snapshot(root)
    assert get("/api/projects/recent")[1]["items"] == []
    assert snapshot(root) == before
    for payload in ({"project_id": "foreign", "page": "writer", "chapter_number": 1},
                    {"project_id": "现有作品", "page": "writer", "chapter_number": True},
                    {"project_id": "现有作品", "page": "story", "chapter_number": 1}):
        assert get.post("/api/projects/recent", payload)[0] == 400
    assert snapshot(root) == before
    project_before = snapshot(root / "现有作品")
    status, data = get.post("/api/projects/recent", {"project_id": "现有作品", "page": "writer", "chapter_number": 4, "source": "draft"})
    assert status == 200 and data["record"]["chapter_number"] == 4
    persisted = snapshot(root)
    status, data = get("/api/projects/recent")
    assert status == 200 and data["items"][0]["title"] == "现有作品"
    assert "source=draft" in data["items"][0]["url"]
    assert snapshot(root) == persisted and snapshot(root / "现有作品") == project_before


def test_project_entry_uses_recent_or_real_manuscript_without_runtime(catalog_api):
    from creative_os.writer_draft_store import WriterDraftStore
    get, root = catalog_api
    WriterDraftStore(root / "现有作品").save(3, "真实工作稿", actor="作者")
    path = "/p/" + __import__("urllib.parse", fromlist=["quote"]).quote("现有作品") + "/"
    before = snapshot(root)
    status, data = get(path)
    assert status == 302 and "chapter=3" in data["location"] and "source=draft" in data["location"]
    assert snapshot(root) == before
    get.post("/api/projects/recent", {"project_id": "现有作品", "page": "story", "chapter_number": None})
    before = snapshot(root)
    assert get(path)[1]["location"].endswith("/story")
    assert snapshot(root) == before


def test_malformed_session_does_not_disconnect_catalog_or_hide_healthy(catalog_api):
    get, root = catalog_api
    bad = book(root, "bad-session")
    directory = bad / ".creative_os/agent/conversations"; directory.mkdir(parents=True, exist_ok=True)
    (directory / "chapter_001.json").write_text(json.dumps({"project_id": "bad-session", "chapter_number": 1, "jobs": []}), encoding="utf-8")
    before = snapshot(root)
    status, result = get("/api/projects")
    assert status == 200
    assert any(item["project_id"] == "现有作品" and item["status"] == "fresh" for item in result["items"])
    assert any(item["project_id"] == "bad-session" and item["status"] == "partial" and item["notices"] for item in result["items"])
    assert result["warnings"]
    assert snapshot(root) == before


def test_corrupt_command_receipts_keep_healthy_catalog_visible(catalog_api):
    get, root = catalog_api
    bad = book(root, "bad-command")
    proposals = bad / ".creative_os/agent/proposals"; proposals.mkdir(parents=True, exist_ok=True)
    (proposals / ("proposal-" + "0" * 32 + ".json")).write_text(json.dumps({
        "project_id": bad.name, "chapter_number": 1, "status": "pending", "result": {"content": "候选"}}), encoding="utf-8")
    receipts = bad / ".creative_os/commands/results.json"
    receipts.parent.mkdir(parents=True, exist_ok=True); receipts.write_text("{broken", encoding="utf-8")
    before = snapshot(root)
    status, result = get("/api/projects")
    assert status == 200
    assert any(item["project_id"] == "现有作品" and item["status"] == "fresh" for item in result["items"])
    bad_item = next(item for item in result["items"] if item["project_id"] == bad.name)
    assert bad_item["status"] == "partial" and bad_item["notices"]
    assert bad_item["counts"] == {"formal": 0, "draft": 0, "candidate": None}
    assert result["warnings"] and snapshot(root) == before
