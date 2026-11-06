"""任务6隔离书架夹具：保留临时证据，不接触正式projects。"""

from contextlib import contextmanager
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import time
from threading import Event, Thread

from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.project_directory_inventory import build_inventory
from creative_os.project_registry import ProjectRegistry
from creative_os.web_workspace import create_server, WriterWebAdapter
from creative_os.writer_draft_store import WriterDraftStore
from scripts.validate_bookshelf_issues_ui import EmptyWorkspace, snapshot


class PhaseGate:
    def __init__(self, points):
        self.events = {point: (Event(), Event()) for point in points}
        self.seen = set()

    def __call__(self, point, _record):
        if point in self.events and point not in self.seen:
            self.seen.add(point)
            entered, release = self.events[point]
            entered.set()
            if not release.wait(30):
                raise RuntimeError("隔离测试阶段等待超时")

    def wait(self, point, page):
        # 同步Playwright必须泵送路由回调，不能阻塞等待HTTP服务线程事件。
        deadline = time.monotonic() + 8
        while not self.events[point][0].is_set() and time.monotonic() < deadline:
            page.wait_for_timeout(20)
        assert self.events[point][0].is_set(), point

    def release(self, point=None):
        for name, (_entered, release) in self.events.items():
            if point is None or name == point:
                release.set()


def seed_book(projects, directory, project_id, title):
    root = projects / directory
    root.mkdir(parents=True)
    (root / "project.json").write_text(json.dumps({"id": project_id, "name": title}, ensure_ascii=False), encoding="utf-8")
    formal = root / "production/final_chapters"
    formal.mkdir(parents=True)
    (formal / "chapter_001.md").write_text("# 第1章\n" + title + "临时正式稿", encoding="utf-8")
    return root


class IsolatedBookshelf:
    def __init__(self, output, label, *, mixed=False):
        fixtures = output / "fixtures"
        fixtures.mkdir(parents=True, exist_ok=True)
        self.workspace = Path(tempfile.mkdtemp(prefix=label + "-", dir=fixtures)).resolve()
        self.projects = self.workspace / "projects"
        self.healthy = seed_book(self.projects, "正常书", "healthy-book", "正常书")
        self.source = seed_book(self.projects, "technical_book", "stable-book", "海风与钟声")
        WriterDraftStore(self.source).save(1, "海风与钟声临时工作稿", actor="隔离验收")
        (self.source / ".hidden").write_bytes(b"hidden\x00sentinel")
        (self.source / "empty/nested").mkdir(parents=True)
        if mixed:
            seed_book(self.projects, "简称", "short-book", "中文简称故事全名")
            bad = self.projects / "bad_metadata"
            bad.mkdir(); (bad / "project.json").write_text("broken-json", encoding="utf-8")
            seed_book(self.projects, "duplicate_a", "duplicated-id", "冲突甲")
            seed_book(self.projects, "duplicate_b", "duplicated-id", "冲突乙")
            summary = seed_book(self.projects, "摘要异常", "summary-book", "摘要异常")
            proposals = summary / ".creative_os/agent/proposals"
            proposals.mkdir(parents=True)
            (proposals / ("proposal-" + "a" * 32 + ".json")).write_text("bad-json", encoding="utf-8")
            conversations = summary / ".creative_os/agent/conversations"
            conversations.mkdir(parents=True)
            (conversations / "chapter_001.json").write_text('{"jobs":[]}', encoding="utf-8")
        self.model_attempts = []
        def no_model():
            self.model_attempts.append(True)
            raise AssertionError("隔离验收禁止模型调用")
        self.registry = ProjectRegistry(self.projects, client_factory=no_model)
        self.old_runtime = WriterAgentRuntime(self.source, "stable-book", client_factory=no_model, read_only=True, recover=False)
        self.server = create_server(EmptyWorkspace(None, "stable-book"), writer_adapter=WriterWebAdapter(self.source, "stable-book"), project_registry=self.registry, port=0)
        self.service = self.server.RequestHandlerClass.migration_service
        self.base = "http://127.0.0.1:" + str(self.server.server_address[1])
        self.worker = Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.original = build_inventory(self.source)
        self.other_roots = {root: snapshot(root) for root in self.projects.iterdir() if root.is_dir() and root.name not in {"technical_book", ".creative_os"}}

    def request(self, method, path, body=None):
        connection = HTTPConnection(*self.server.server_address, timeout=8)
        connection.request(method, path, body=json.dumps(body) if body is not None else None, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        return response.status, json.loads(raw) if raw else None

    def verify_success(self, operation):
        target = self.projects / "海风与钟声"
        backup = self.service.backup_root / operation / "project"
        assert not self.source.exists()
        assert build_inventory(target) == build_inventory(backup) == self.original
        assert json.loads((target / "project.json").read_text(encoding="utf-8"))["id"] == "stable-book"
        assert len(list(self.service.backup_root.glob("*/project"))) == 1
        before = snapshot(target)
        for write in (lambda: self.old_runtime.store.save(2, "禁止写入", actor="隔离验收"),
                      lambda: self.old_runtime._write_decision("decision-old", {"analysis": "禁止写入"})):
            try:
                write()
            except ValueError as error:
                assert str(error) == "project_directory_moved"
            else:
                raise AssertionError("旧写实例未被门禁拒绝")
        assert not self.source.exists() and snapshot(target) == before
        for root, original in self.other_roots.items():
            assert snapshot(root) == original
        assert self.request("GET", "/api/author-home")[0] == 503
        assert self.request("POST", "/api/commands/save-writer-draft", {})[0] == 409
        assert self.request("GET", "/p/stable-book/api/author-home")[1]["counts"]["formal"] == 1
        assert not self.model_attempts
        return str(backup)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join(); self.registry.close()
        self.old_runtime._pool.shutdown(wait=True)


@contextmanager
def isolated_bookshelf(output, label, *, mixed=False):
    case = IsolatedBookshelf(output, label, mixed=mixed)
    try:
        yield case
    finally:
        case.close()
