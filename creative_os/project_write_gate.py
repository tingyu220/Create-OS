"""源目录外的稳定身份写锁；迁移持锁期间不持有源内文件句柄。"""

from contextlib import contextmanager
from functools import wraps
import hashlib
import os
from pathlib import Path
import threading
import time

from creative_os.project_directory import read_project_metadata, validated_project, validate_project_id
from creative_os.project_migration_store import ProjectMigrationStore

if os.name == "nt":
    import msvcrt
else:
    import fcntl

_LOCKS = {}
_GUARD = threading.Lock()
_LOCAL = threading.local()


def _state():
    if not hasattr(_LOCAL, "depths"):
        _LOCAL.depths, _LOCAL.migrations = {}, set()
    return _LOCAL


def _key(path):
    return os.path.normcase(str(path.absolute()))


def _safe_path(path):
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise ValueError("project_path_invalid")


@contextmanager
def _lease(path, *, blocking=True):
    key = _key(path)
    with _GUARD:
        lock = _LOCKS.setdefault(key, threading.RLock())
    if not lock.acquire(blocking=blocking):
        raise ValueError("project_migration_busy")
    state = _state()
    try:
        if state.depths.get(key, 0):
            state.depths[key] += 1
            try:
                yield
            finally:
                state.depths[key] -= 1
            return
        for ancestor in (path.parent.parent, path.parent, path):
            _safe_path(ancestor)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            while True:
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as error:
                    if error.errno not in {11, 13, 35, 36}:
                        raise
                    if not blocking:
                        raise ValueError("project_migration_busy") from error
                    time.sleep(0.01)
            state.depths[key] = 1
            try:
                yield
            finally:
                state.depths.pop(key, None)
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        lock.release()


def _identity_path(root, project_id):
    name = hashlib.sha256(project_id.casefold().encode("utf-8")).hexdigest()
    return root / ".creative_os" / "project-write-locks" / (name + ".lock")


def acquire_record_lease(path, attempts):
    """记录锁沿用同一系统互斥原语；文件存在不代表仍有执行所有者。"""
    for _ in range(attempts):
        lease = _lease(Path(path).absolute(), blocking=False)
        try:
            lease.__enter__()
        except ValueError as error:
            if str(error) != "project_migration_busy":
                raise
        else:
            return lease
    raise ValueError("record_store_busy")


def assert_operation_lease(projects_root, project_id):
    key = _key(_identity_path(Path(projects_root).resolve(), project_id))
    if key not in _state().migrations or not _state().depths.get(key):
        raise ValueError("migration_command_ownership_required")


def _operations(root):
    # Store不导入CommandBoundary或Runtime，读取损坏证据时一律拒绝写入。
    return ProjectMigrationStore(root).read_operations()


def assert_directory_available(projects_root, directory):
    """纯查询；已迁移旧路径永久保留，不允许新书复用。"""
    for record in _operations(Path(projects_root)).values():
        if directory.casefold() == record["source_directory"].casefold() and record["stage"] in {"moving", "verified", "needs_reconciliation"}:
            raise ValueError("project_directory_moved")
        if directory.casefold() in {record["source_directory"].casefold(), record["target_directory"].casefold()} and record["stage"] not in {"failed", "verified"}:
            raise ValueError("project_migration_busy")


def _binding(root):
    _safe_path(root)
    records = _operations(root.parent)
    for record in records.values():
        if record["source_directory"].casefold() == root.name.casefold() and record["stage"] in {"moving", "verified", "needs_reconciliation"}:
            raise ValueError("project_directory_moved")
    if (root / "project.json").exists():
        return read_project_metadata(root.parent, root)["id"]
    if any(root.name.casefold() in {row["source_directory"].casefold(), row["target_directory"].casefold()} for row in records.values()):
        raise ValueError("project_migration_busy")
    return None


@contextmanager
def project_write_lease(project_root):
    root = Path(project_root).absolute()
    project_id = _binding(root)
    if project_id is None:
        # 独立领域测试根无metadata，沿用原项目锁，不擅自推断为工作区。
        yield
        return
    path = _identity_path(root.parent, project_id)
    if _key(path) in _state().migrations:
        raise ValueError("project_migration_busy")
    with _lease(path):
        if _binding(root) != project_id:
            raise ValueError("project_scope_mismatch")
        for row in _operations(root.parent).values():
            if row["project_id"].casefold() == project_id.casefold() and row["stage"] not in {"failed", "verified"}:
                raise ValueError("project_migration_busy")
        yield


@contextmanager
def workspace_write_lease(projects_root):
    root = Path(projects_root).resolve()
    with _lease(root / ".creative_os/project-write-locks/workspace.lock"):
        yield


@contextmanager
def migration_lease(projects_root, project_id):
    with operation_migration_lease(projects_root, project_id):
        root = Path(projects_root).resolve()
        source, _ = validated_project(root, project_id)
        from creative_os.project_migration_activity import assert_persistent_idle
        assert_persistent_idle(root, source, project_id)
        yield source


@contextmanager
def operation_migration_lease(projects_root, project_id):
    """已验证持久操作专用：允许双存/双失核对，调用方必须绑定完整操作证据。"""
    validate_project_id(project_id)
    root = Path(projects_root).resolve()
    path = _identity_path(root, project_id)
    # 不允许持源内权威锁时升级；同线程RLock重入不能绕过迁移互斥。
    if _state().depths.get(_key(path)):
        raise ValueError("project_migration_busy")
    with _lease(root / ".creative_os/project-write-locks/workspace.lock", blocking=False):
        with _lease(path, blocking=False):
            _state().migrations.add(_key(path))
            try:
                yield
            finally:
                _state().migrations.discard(_key(path))


def project_write_method(root_attribute):
    """先取得外置身份锁，再允许方法获取自己的内部锁。"""
    def decorate(method):
        @wraps(method)
        def guarded(self, *args, **kwargs):
            with project_write_lease(getattr(self, root_attribute)):
                return method(self, *args, **kwargs)
        return guarded
    return decorate
