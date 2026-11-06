import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from creative_os.publication_models import ChapterSnapshot
from creative_os.publication_web import PublicationOrchestrator
from creative_os.tomato_browser_adapter import FakeTomatoPage, TomatoBrowserAdapter
from creative_os.web_workspace import WorkspaceWebAdapter, create_server


class EmptyQuery:
    def get_workspace(self, project_id):
        return {"project_id": project_id}


def test_workspace_publication_get_unknown_is_structured_404():
    page = FakeTomatoPage(work_id="book-a", title="临时作品")
    adapter = TomatoBrowserAdapter(page); adapter.connect()
    publication = PublicationOrchestrator(adapter)
    server = create_server(WorkspaceWebAdapter(EmptyQuery(), "book-a"), publication_orchestrator=publication, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        try:
            urlopen(f"http://127.0.0.1:{server.server_port}/api/publication?operation_id=missing")
            assert False
        except HTTPError as error:
            assert error.code == 404
            assert json.loads(error.read()) ["error"]["code"] == "operation_not_found"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_workspace_publication_post_accepts_tomato_target_and_checks():
    page = FakeTomatoPage(work_id="book-a", title="临时作品")
    adapter = TomatoBrowserAdapter(page); adapter.connect()
    publication = PublicationOrchestrator(adapter)
    server = create_server(WorkspaceWebAdapter(EmptyQuery(), "book-a"), publication_orchestrator=publication, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        snapshot = ChapterSnapshot("book-a", 1, "r1", "正文")
        body = {"action": "submit", "snapshot": snapshot.to_dict(), "target": {"work_id": "book-a", "title": "临时作品", "platform": "tomato", "chapter_number": 1, "chapter_title": "第一章"}, "work_id": "book-a", "platform_name": "tomato", "checks": {name: True for name in publication.CHECKS}}
        request = Request(f"http://127.0.0.1:{server.server_port}/api/publication", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
        result = json.loads(urlopen(request).read())
        assert result["status"] == "ready_to_publish"
        assert result["platform_name"] == "tomato"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
