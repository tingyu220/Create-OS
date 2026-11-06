"""临时项目的并发门禁证据；不调用模型或实际迁移服务。"""

from concurrent.futures import ThreadPoolExecutor, Future
import hashlib
import json
import multiprocessing
from pathlib import Path
from threading import Event
from contextlib import contextmanager
import threading

import pytest

from creative_os.domains.project_authority import project_authority_lock
from creative_os.project_write_gate import (migration_lease, project_write_lease,
                                          assert_directory_available)
from creative_os.project_migration_store import ProjectMigrationStore
from creative_os.project_registry import ProjectRegistry
from creative_os.writer_draft_store import WriterDraftStore
from creative_os.workspace_command import (FileCommandResultStore, CommandResult, CommandStatus,
                                          CommandResultRecord, CommandRecordState)
from creative_os.novel_project_command import NovelProjectCreator
from creative_os.agent_runtime import WriterAgentRuntime, AgentJob
from creative_os.agent_proposal_store import review_identity
from creative_os.workspace_command import CommandRequest


@pytest.fixture
def runtime(tmp_path):
    project = book(tmp_path)
    class FakeClient:
        def complete(self, *args, **kwargs):
            return "临时候选正文"
    value = WriterAgentRuntime(project, "stable", client_factory=FakeClient, recover=False)
    yield value
    value._pool.shutdown(wait=True)


@pytest.mark.parametrize("kind", ["cached_job", "queued_future", "running_future", "unknown_future"])
def test_registry_rejects_cached_or_queued_activity_without_get(runtime, kind, monkeypatch):
    registry = ProjectRegistry(runtime.root.parent)
    registry.register("stable", {"agent_runtime": runtime})
    monkeypatch.setattr(registry, "get", lambda *_a, **_k: pytest.fail("不能惰性创建Runtime"))
    if kind == "cached_job":
        runtime._jobs["j"] = AgentJob("j", "queued", "排队", 1)
    else:
        future = Future()
        if kind == "running_future":
            future.set_running_or_notify_cancel()
        runtime._futures = {"j": future if kind != "unknown_future" else object()}
    with pytest.raises(ValueError, match="project_migration_(active|state_unknown)"):
        registry.assert_migration_idle("stable")
    with pytest.raises(ValueError, match="project_migration_(active|state_unknown)"):
        registry.invalidate_after_migration("stable")
    assert "stable" in registry._entries


def test_registry_invalidates_idle_cache_without_cancel(runtime):
    registry = ProjectRegistry(runtime.root.parent)
    registry.register("stable", {"agent_runtime": runtime})
    registry.assert_migration_idle("stable")
    registry.invalidate_after_migration("stable")
    assert not registry._entries


def test_terminal_job_with_live_future_still_blocks_invalidation(runtime, monkeypatch):
    registry = ProjectRegistry(runtime.root.parent)
    registry.register("stable", {"agent_runtime": runtime})
    entered, release = Event(), Event()
    def blocked_run(job_id, *_args):
        runtime._set(job_id, status="completed")
        entered.set()
        assert release.wait(5)
    monkeypatch.setattr(runtime, "_run", blocked_run)
    try:
        runtime.submit("临时任务", 1)
        assert entered.wait(5)
        with pytest.raises(ValueError, match="project_migration_active"):
            registry.assert_migration_idle("stable")
    finally:
        release.set()
    runtime._pool.submit(lambda: None).result(5)
    registry.assert_migration_idle("stable")


def _finished_job(runtime):
    import time
    job = runtime.submit("生成临时候选", 1, mode="act")
    for _ in range(500):
        job = runtime.get(job.job_id)
        if job.status in {"completed", "failed"}:
            assert job.status == "completed", job.error
            runtime._pool.submit(lambda: None).result(5)
            return job
        time.sleep(0.01)
    pytest.fail("临时任务超时")


def domain_write(runtime, action):
    if action == "story":
        candidate = runtime.story.propose(runtime.story.session_id, [{"key": "theme", "title": "主题", "text": "冒险"}], [], expected_revision=0, actor="作者", operation_id="p")
        return lambda: runtime.story.confirm(runtime.story.session_id, 1, candidate["hash"], expected_confirmed_version=0, actor="作者", operation_id="confirm")
    job = _finished_job(runtime)
    target = {"project_id": "stable", "chapter_number": 1, "session_id": job.session_id, "proposal_id": job.proposal_id}
    if action == "proposal_review":
        return lambda: runtime.proposal_commands.execute(CommandRequest("review_writer_proposal", "review", "作者", target, {"action": "accept"}, idempotency_key="review"))
    if action in {"proposal_reconcile", "lesson"}:
        result = runtime.proposal_commands.execute(CommandRequest("review_writer_proposal", "review", "作者", target, {"action": "reject", "reason": "动机不足"}, idempotency_key="review"))
        assert result.status == "accepted"
        proposal = runtime.proposals.read(job.proposal_id)
        if action == "proposal_reconcile":
            return lambda: runtime.proposal_commands.execute(CommandRequest("reconcile_writer_proposal", "reconcile", "作者", target, review_identity(proposal["review"]), idempotency_key="reconcile"))
        lesson_target = {key: target[key] for key in ("project_id", "chapter_number", "session_id")}
        lesson_target["feedback_id"] = proposal["review"]["feedback"]["id"]
        return lambda: runtime.lesson_commands.execute(CommandRequest("manage_writer_lesson", "lesson", "作者", lesson_target, {"action": "create", "title": "动机", "content": "动作体现动机", "range": "chapter"}, idempotency_key="lesson"))
    if action == "agent_submit":
        return lambda: runtime.submit("只分析", 2)
    if action == "agent_update":
        return lambda: runtime._set(job.job_id, message="后台更新")
    if action == "decision_write":
        return lambda: runtime._write_decision("decision-test", {"analysis": "临时分析"})
    if action == "conversation":
        session = runtime.conversations.read(1)
        return lambda: runtime.conversations.write(session)
    proposal = runtime.proposals.read(job.proposal_id)
    return lambda: runtime.proposals.write(proposal)


@pytest.mark.parametrize("action", ["story", "proposal_review", "proposal_reconcile", "lesson", "agent_submit", "agent_update", "conversation", "proposal_write", "decision_write"])
def test_domain_writes_wait_for_migration_lease(runtime, action):
    write = domain_write(runtime, action)
    entered, finished = Event(), Event()
    def execute():
        entered.set()
        result = write()
        finished.set()
        return result
    with ThreadPoolExecutor(1) as pool:
        with migration_lease(runtime.root.parent, "stable"):
            future = pool.submit(execute)
            assert entered.wait(5)
            assert not finished.wait(0.1)
        result = future.result(5)
    if action in {"proposal_review", "proposal_reconcile", "lesson"}:
        assert result.status == "accepted", result.error


@pytest.mark.parametrize("action", ["story", "proposal_review", "proposal_reconcile", "lesson", "agent_submit", "agent_update", "conversation", "proposal_write", "decision_write"])
def test_domain_writes_at_old_path_do_not_recreate_directory(runtime, action):
    write = domain_write(runtime, action)
    source, workspace = runtime.root, runtime.root.parent
    source.rename(workspace / "new")
    moved_record(workspace)
    with pytest.raises(ValueError, match="project_directory_moved"):
        write()
    assert not source.exists()


def test_waiting_writer_rechecks_moved_path_after_acquiring_identity_lock(tmp_path, monkeypatch):
    project = book(tmp_path)
    entered = Event()
    import creative_os.project_write_gate as gate
    original_lease = gate._lease
    owner = threading.get_ident()
    @contextmanager
    def observed_lease(path, **kwargs):
        # 等到写方已读取身份、正要取得外置锁，再rename；不与临时metadata读句柄竞争。
        if threading.get_ident() != owner and path.name != "workspace.lock":
            entered.set()
        with original_lease(path, **kwargs):
            yield
    monkeypatch.setattr(gate, "_lease", observed_lease)
    def write():
        WriterDraftStore(project).save(1, "旧路径写入", actor="作者")
    with ThreadPoolExecutor(1) as pool:
        with migration_lease(tmp_path, "stable"):
            future = pool.submit(write)
            assert entered.wait(5)
            # 测试租约内整体rename，确认没有源内锁句柄跨rename。
            project.rename(tmp_path / "new")
            moved_record(tmp_path)
        with pytest.raises(ValueError, match="project_directory_moved"):
            future.result(5)
    assert not project.exists()


def test_migration_blocks_new_book_intent_until_lease_release(tmp_path):
    book(tmp_path)
    entered, finished = Event(), Event()
    def create():
        entered.set()
        result = NovelProjectCreator(tmp_path).create("other")
        finished.set()
        return result
    with ThreadPoolExecutor(1) as pool:
        with migration_lease(tmp_path, "stable"):
            future = pool.submit(create)
            assert entered.wait(5)
            assert not finished.wait(0.1)
            assert not (tmp_path / ".creative_os/new-books.json").exists()
        assert future.result(5).is_dir()


def test_new_book_initialization_excludes_migration(tmp_path, monkeypatch):
    book(tmp_path)
    import creative_os.novel_project as novel
    original = novel.initialize_novel_project
    entered, release = Event(), Event()
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(novel, "initialize_novel_project", blocked)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(NovelProjectCreator(tmp_path).create, "other")
        try:
            assert entered.wait(5)
            with pytest.raises(ValueError, match="project_migration_busy"):
                with migration_lease(tmp_path, "stable"):
                    pass
        finally:
            release.set()
        assert future.result(5).name == "other"


def test_old_path_reuse_with_replaced_metadata_is_still_rejected(tmp_path):
    project = book(tmp_path)
    project.rename(tmp_path / "new")
    moved_record(tmp_path)
    replacement = book(tmp_path, "old", "replacement")
    before = sorted(replacement.iterdir())
    with pytest.raises(ValueError, match="project_directory_moved"):
        WriterDraftStore(replacement).save(1, "错误作品", actor="作者")
    assert sorted(replacement.iterdir()) == before


@pytest.mark.parametrize("directory", ["OLD", "Old"])
def test_old_path_case_alias_cannot_be_reused(tmp_path, directory):
    project = book(tmp_path)
    project.rename(tmp_path / "new")
    moved_record(tmp_path)
    with pytest.raises(ValueError, match="project_directory_moved"):
        NovelProjectCreator(tmp_path).create(directory)
    with pytest.raises(ValueError, match="project_directory_moved"):
        WriterDraftStore(tmp_path / directory).save(1, "不能复用", actor="作者")
    assert not (tmp_path / directory).exists()


def book(root, name="old", project_id="stable"):
    path = root / name
    path.mkdir(parents=True)
    (path / "project.json").write_text(json.dumps({"id": project_id, "name": name}), encoding="utf-8")
    return path


def moved_record(root, source="old", stage="verified"):
    ProjectMigrationStore(root).write_operation({
        "operation_id": "op", "project_id": "stable", "plan_fingerprint": "f" * 64,
        "source_directory": source, "target_directory": "new",
        "backup_directory": ".backup/project-directory-migrations/op/project",
        "stage": stage, "continuation_no": 0, "reason": None})


def hold_authority(root, ready, release):
    with project_authority_lock(root):
        ready.set()
        if not release.wait(10):
            raise RuntimeError("测试屏障超时")


def process_write(root, attempted, finished):
    attempted.set()
    WriterDraftStore(root).save(1, "跨进程写入", actor="作者")
    finished.set()


def test_migration_excludes_writer_in_other_process(tmp_path):
    project = book(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    attempted, finished = ctx.Event(), ctx.Event()
    process = ctx.Process(target=process_write, args=(project, attempted, finished))
    try:
        with migration_lease(tmp_path, "stable"):
            process.start()
            assert attempted.wait(10)
            assert not finished.wait(0.1)
            assert not (project / ".creative_os").exists()
        process.join(10)
        assert process.exitcode == 0
        assert finished.is_set()
        assert WriterDraftStore(project).current(1)[1] == "跨进程写入"
    finally:
        if process.is_alive():
            process.terminate()
            process.join()


def test_thread_writer_reentry_and_nonblocking_migration(tmp_path):
    project = book(tmp_path)
    ready, release = Event(), Event()
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(hold_authority, project, ready, release)
        try:
            assert ready.wait(5)
            with pytest.raises(ValueError, match="project_migration_busy"):
                with migration_lease(tmp_path, "stable"):
                    pytest.fail("不能进入迁移")
        finally:
            release.set()
        future.result(5)
    with project_authority_lock(project):
        with project_authority_lock(project):
            WriterDraftStore(project).save(1, "稿件", actor="作者")
        with pytest.raises(ValueError, match="project_migration_busy"):
            with migration_lease(tmp_path, "stable"):
                pass
    external = tmp_path / ".creative_os/project-write-locks" / (hashlib.sha256(b"stable").hexdigest() + ".lock")
    assert external.exists()


def test_cross_process_writer_blocks_migration_without_waiting(tmp_path):
    project = book(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    process = ctx.Process(target=hold_authority, args=(project, ready, release))
    process.start()
    try:
        assert ready.wait(10)
        with pytest.raises(ValueError, match="project_migration_busy"):
            with migration_lease(tmp_path, "stable"):
                pytest.fail("跨进程锁没有互斥")
    finally:
        release.set()
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join()
    assert process.exitcode == 0


@pytest.mark.parametrize("action", ["save", "publish", "reserve", "complete", "release"])
def test_migration_excludes_each_write_and_allows_other_book(tmp_path, action):
    project = book(tmp_path)
    other = book(tmp_path, "other", "other-id")
    drafts = WriterDraftStore(project)
    drafts.save(1, "初稿", actor="作者")
    commands = FileCommandResultStore(project)
    if action in {"complete", "release"}:
        commands.reserve("key", "f")
    # 原回执保留会阻止迁移；这里在已取得迁移租约后制造写入竞争。
    if action in {"complete", "release"}:
        commands.release("key", "f")
    entered, finished = Event(), Event()
    def write():
        entered.set()
        try:
            if action == "save":
                drafts.save(1, "新版", actor="作者", expected_version=1)
            elif action == "publish":
                drafts.promote(1, version_number=1, actor="作者", expected_version=1)
            elif action == "reserve":
                commands.reserve("new-key", "f")
            elif action == "complete":
                commands.complete("key", "f", CommandResult(CommandStatus.ACCEPTED, "save", "request"))
            else:
                commands.release("key", "f")
        finally:
            finished.set()
    with ThreadPoolExecutor(1) as pool:
        with migration_lease(tmp_path, "stable"):
            if action in {"complete", "release"}:
                # 仅准备测试回执，不调用被测门禁来构造同线程升级。
                commands._write_records({"key": CommandResultRecord("f", CommandRecordState.RESERVED)})
            future = pool.submit(write)
            assert entered.wait(5)
            assert not finished.wait(0.1)
            WriterDraftStore(other).save(1, "另一书", actor="作者")
        future.result(5)
    if action == "complete":
        assert commands.read("key").state == CommandRecordState.COMPLETED
    if action == "release":
        assert commands.read("key") is None
    assert WriterDraftStore(other).current(1)[1] == "另一书"


@pytest.mark.parametrize("action", ["save", "reserve", "complete", "release", "authority", "create"])
def test_old_path_rejected_before_mkdir_and_name_cannot_be_reused(tmp_path, action):
    project = book(tmp_path)
    drafts, commands = WriterDraftStore(project), FileCommandResultStore(project)
    project.rename(tmp_path / "new")
    moved_record(tmp_path)
    with pytest.raises(ValueError, match="project_directory_moved"):
        if action == "save":
            drafts.save(1, "不得重建", actor="作者")
        elif action == "reserve":
            commands.reserve("key", "f")
        elif action == "complete":
            commands.complete("key", "f", CommandResult(CommandStatus.ACCEPTED, "save", "r"))
        elif action == "release":
            commands.release("key", "f")
        elif action == "create":
            NovelProjectCreator(tmp_path).create("old")
        else:
            with project_authority_lock(project):
                pass
    assert not project.exists()
    with pytest.raises(ValueError, match="project_directory_moved"):
        assert_directory_available(tmp_path, "old")


def test_reads_and_unmanaged_root_are_compatible(tmp_path):
    project = book(tmp_path)
    registry = ProjectRegistry(tmp_path)
    def snapshot():
        return {str(p.relative_to(tmp_path)): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                for p in tmp_path.rglob("*")}
    before = snapshot()
    registry.assert_migration_idle("stable")
    FileCommandResultStore(project).read("missing")
    assert_directory_available(tmp_path, "unused")
    registry.get("stable")["agent_runtime"].story.view()
    registry.close()
    assert snapshot() == before
    isolated = tmp_path / "isolated"
    WriterDraftStore(isolated).save(1, "独立领域测试", actor="作者")
    assert WriterDraftStore(isolated).current(1)[1] == "独立领域测试"


@pytest.mark.parametrize("kind", ["job", "bad_jobs", "jobs_path_file", "receipt", "bad_receipt", "bad_completed_receipt", "initializing", "bad_creation"])
def test_persistent_activity_and_unknown_state_refuse_migration(tmp_path, kind):
    project = book(tmp_path)
    if kind == "jobs_path_file":
        path, value = project / ".creative_os/agent/conversations", {}
    elif kind in {"job", "bad_jobs"}:
        path = project / ".creative_os/agent/conversations/chapter_001.json"
        value = {"project_id": "stable", "jobs": {"j": {"job_id": "j", "status": "queued"}}} if kind == "job" else {"jobs": []}
    elif kind in {"receipt", "bad_receipt", "bad_completed_receipt"}:
        if kind == "receipt":
            FileCommandResultStore(project).reserve("r", "f")
            path = None
        else:
            path, value = project / ".creative_os/commands/results.json", {}
            if kind == "bad_completed_receipt":
                value = {"schema_version": 1, "records": {"key": {"fingerprint": "f", "state": "completed", "result": {"status": "accepted"}}}}
    else:
        path = tmp_path / ".creative_os/new-books.json"
        value = {"op": {"folder": "old", "status": "initializing"}} if kind == "initializing" else []
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="project_migration_(active|state_unknown)"):
        with migration_lease(tmp_path, "stable"):
            pytest.fail("活动或未知状态不得开始备份")
