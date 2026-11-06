"""临时项目中的作者摘要验证；全程拒绝真实模型和外网。"""

from http.client import HTTPConnection
import json
from pathlib import Path
from threading import Thread

import pytest

from creative_os.author_home_query import AuthorHomeQuery
from creative_os.web_workspace import WorkspaceWebAdapter, WriterWebAdapter, create_server
from creative_os.workspace_query import WorkspaceQueryAdapter
from creative_os.writer_draft_store import WriterDraftStore
from scripts.fake_validation_guard import fake_validation_guard


@pytest.fixture(autouse=True)
def guarded():
    with fake_validation_guard() as blocked:
        yield
        assert blocked == []


def snapshot(root):
    return {str(path.relative_to(root)): (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
            for path in root.rglob("*")}


def seed(root, project_id="book"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.json").write_text(json.dumps({"id": project_id, "title": "海上的钟"}), encoding="utf-8")
    final = root / "production" / "final_chapters"
    final.mkdir(parents=True)
    (final / "chapter_001.md").write_text("正式稿", encoding="utf-8")
    (final / "chapter_003.md").write_text("另一章正式稿", encoding="utf-8")
    WriterDraftStore(root).save(1, "作者修改过的工作稿", actor="作者")
    WriterDraftStore(root).save(2, "只有工作稿", actor="作者")
    proposals = root / ".creative_os" / "agent" / "proposals"
    proposals.mkdir(parents=True)
    for index, status in enumerate(("pending", "reviewing", "accepted")):
        value = {"project_id": project_id, "chapter_number": 4, "status": status,
                 "result": {"content": "候选不能冒充工作稿"}}
        (proposals / f"proposal-{index:032x}.json").write_text(json.dumps(value), encoding="utf-8")
    session = root / ".creative_os" / "agent" / "conversations"
    session.mkdir(parents=True)
    (session / "chapter_002.json").write_text(json.dumps({"project_id": project_id, "chapter_number": 2,
        "jobs": {"old": {"status": "failed", "updated_at": "2026-01-01"},
                 "latest": {"status": "completed", "updated_at": "2026-01-02"}}}), encoding="utf-8")
    (session / "chapter_005.json").write_text(json.dumps({"project_id": project_id, "chapter_number": 5,
        "jobs": {"failed": {"status": "failed", "updated_at": "2026-01-03", "error": "private technical detail"}}}), encoding="utf-8")
    return root


def test_real_manuscripts_candidates_and_latest_failure_are_separate_and_read_only(tmp_path):
    seed(tmp_path)
    # 放入40章旧投影，不能改变真实稿件数量。
    projection = tmp_path / ".creative_os" / "projection"
    projection.mkdir()
    (projection / "bundle.json").write_text(json.dumps({"chapters": list(range(1, 41))}), encoding="utf-8")
    before = snapshot(tmp_path)
    payload = AuthorHomeQuery(tmp_path, "book").read()
    assert payload["counts"] == {"formal": 2, "draft": 2, "candidate": 2}
    assert payload["title"] == "海上的钟"
    assert {item["chapter_number"] for item in payload["chapters"]} == {1, 2, 3, 4}
    assert payload["resume"] == {"chapter_number": 4, "source": "candidate"}
    assert [item["chapter_number"] for item in payload["attention"] if item["kind"] == "failed"] == [5]
    assert "private technical detail" not in json.dumps(payload)
    assert snapshot(tmp_path) == before


def test_empty_query_creates_no_files_or_directories(tmp_path):
    before = snapshot(tmp_path)
    payload = AuthorHomeQuery(tmp_path, "empty").read()
    assert payload["counts"] == {"formal": 0, "draft": 0, "candidate": 0}
    assert payload["resume"] is None
    assert payload["status"] == "fresh"
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("jobs", [[], {"bad": []}, {"bad": {"status": []}}, {"bad": {"status": "failed", "updated_at": []}}])
def test_malformed_session_jobs_are_partial_and_readonly(tmp_path, jobs):
    seed(tmp_path)
    (tmp_path / ".creative_os/agent/conversations/chapter_001.json").write_text(json.dumps({
        "project_id": "book", "chapter_number": 1, "jobs": jobs}), encoding="utf-8")
    before = snapshot(tmp_path)
    result = AuthorHomeQuery(tmp_path, "book").read()
    assert result["status"] == "partial" and result["notices"]
    assert result["counts"] == {"formal": 2, "draft": 2, "candidate": 2}
    assert snapshot(tmp_path) == before


def test_terminal_proposal_with_reserved_receipt_remains_in_pending_directory(tmp_path):
    from creative_os.agent_proposal_store import AgentProposalStore
    from creative_os.workspace_command import FileCommandResultStore
    seed(tmp_path)
    store = AgentProposalStore(tmp_path, "book")
    proposal_id = "proposal-" + "0" * 32
    value = store.read(proposal_id)
    value.update(status="accepted", review={"identity": {"action": "accept", "reason": "原操作"}, "actor": "作者",
                 "feedback": {"id": "feedback-old"}, "job_id": "job-old", "commands": [{"key": "reserved-old"}]})
    value["proposal_id"] = proposal_id; store.write(value)
    FileCommandResultStore(tmp_path).reserve("reserved-old", "fingerprint")
    before = snapshot(tmp_path)
    result = AuthorHomeQuery(tmp_path, "book").read()
    assert result["counts"]["candidate"] == 2
    chapter = next(item for item in result["chapters"] if item["chapter_number"] == 4)
    assert chapter["pending_candidates"] == 2
    assert snapshot(tmp_path) == before


def test_corrupt_command_receipts_make_only_candidate_count_unknown(tmp_path):
    seed(tmp_path)
    receipts = tmp_path / ".creative_os/commands/results.json"
    receipts.parent.mkdir(parents=True, exist_ok=True); receipts.write_text("{broken", encoding="utf-8")
    before = snapshot(tmp_path)
    result = AuthorHomeQuery(tmp_path, "book").read()
    assert result["status"] == "partial" and result["notices"]
    assert result["counts"] == {"formal": 2, "draft": 2, "candidate": None}
    assert snapshot(tmp_path) == before


def test_corrupt_working_draft_is_unknown_not_zero_and_other_sources_remain_available(tmp_path):
    seed(tmp_path)
    (tmp_path / ".creative_os/writer/drafts/chapter_002.jsonl").write_text("{broken", encoding="utf-8")
    before = snapshot(tmp_path)
    payload = AuthorHomeQuery(tmp_path, "book").read()
    assert payload["status"] == "partial"
    assert payload["counts"]["draft"] is None
    assert payload["counts"]["formal"] == 2
    assert payload["counts"]["candidate"] == 2
    assert payload["notices"]
    assert snapshot(tmp_path) == before


class EmptyReader:
    def read_bundle(self, _project_id): return None
    def current_heads(self, _project_id): return ()


class ReadOnlyRegistry:
    """仅为路由隔离提供已绑定适配器，不创建运行时。"""
    def __init__(self, roots): self.roots = roots
    def get(self, project_id, *, writable=False):
        if writable or project_id not in self.roots:
            raise ValueError("project_scope_mismatch")
        return {"writer_adapter": WriterWebAdapter(self.roots[project_id], project_id),
                "workspace_adapter": WorkspaceWebAdapter(WorkspaceQueryAdapter(EmptyReader()), project_id),
                "agent_runtime": None}


def test_http_route_uses_selected_project_and_does_not_mutate_projects(tmp_path):
    first = seed(tmp_path / "first", "first")
    second = tmp_path / "second"
    second.mkdir()
    registry = ReadOnlyRegistry({"first": first, "second": second})
    adapter = WorkspaceWebAdapter(WorkspaceQueryAdapter(EmptyReader()), "first")
    server = create_server(adapter, writer_adapter=WriterWebAdapter(first, "first"), project_registry=registry, port=0)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    before = snapshot(tmp_path)
    try:
        for path, project_id, count in (("/api/author-home", "first", 2),
            ("/p/first/api/author-home", "first", 2), ("/p/second/api/author-home", "second", 0)):
            connection = HTTPConnection(*server.server_address)
            connection.request("GET", path)
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
            assert response.status == 200
            assert payload["project_id"] == project_id
            assert payload["counts"]["formal"] == count
        assert snapshot(tmp_path) == before
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_author_home_http_unavailable_without_writer():
    server = create_server(WorkspaceWebAdapter(WorkspaceQueryAdapter(EmptyReader()), "none"), port=0)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        connection = HTTPConnection(*server.server_address)
        connection.request("GET", "/api/author-home")
        response = connection.getresponse()
        assert response.status == 503
        response.read()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
