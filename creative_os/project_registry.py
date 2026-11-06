"""轻量项目路由；只打开 projects 的直接子目录，按写请求惰性恢复 Runtime。"""

from pathlib import Path
from threading import RLock
from urllib.parse import unquote, urlsplit

from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.novel_project_command import NovelProjectCreator
from creative_os.projection.repository import FileProjectionRepository
from creative_os.workspace_query import WorkspaceQueryAdapter
from creative_os.workspace_command import CommandBoundary, FileCommandResultStore
from creative_os.workspace_command_adapter import WorkspaceCommandAdapter
from creative_os.writer_command import WriterDraftCommandHandler
from creative_os.project_directory import validated_project
from creative_os.project_migration_activity import assert_persistent_idle


class ProjectRegistry:
    def __init__(self, projects_root, *, client_factory=None):
        self.root = Path(projects_root).resolve()
        self.creator = NovelProjectCreator(self.root)
        self.client_factory = client_factory
        self._entries = {}
        self._lock = RLock()

    def register(self, project_id, entry):
        """复用服务已装配的默认项目，避免同项目出现第二条模型队列。"""
        runtime = entry["agent_runtime"]
        root, _ = validated_project(self.root, project_id)
        if runtime.project_id != project_id or runtime.root.resolve() != root:
            raise ValueError("registry_project_scope_mismatch")
        with self._lock:
            if project_id in self._entries:
                raise ValueError("registry_project_already_registered")
            self._entries[project_id] = entry

    def get(self, project_id, *, writable=False):
        root, _ = validated_project(self.root, project_id)
        with self._lock:
            existing = self._entries.get(project_id)
            if existing is not None and existing["agent_runtime"].root.resolve() != root:
                raise ValueError("project_directory_changed_restart_required")
            if existing is not None and (not writable or not existing["agent_runtime"].read_only):
                return existing
            from creative_os.web_workspace import WorkspaceWebAdapter, WriterWebAdapter
            runtime = WriterAgentRuntime(root, project_id, client_factory=self.client_factory, read_only=not writable, recover=False)
            handler = WriterDraftCommandHandler(project_id, runtime.store)
            boundary = CommandBoundary(handler, version_reader=lambda target: self._draft_version(runtime, target),
                                       store=FileCommandResultStore(root), request_validator=handler.validate)
            entry = {"workspace_adapter": WorkspaceWebAdapter(WorkspaceQueryAdapter(FileProjectionRepository(root, expected_project_id=project_id)), project_id),
                     "writer_adapter": WriterWebAdapter(root, project_id), "writer_command_adapter": WorkspaceCommandAdapter(boundary),
                     "agent_runtime": runtime, "command_adapter": None, "review_command_adapter": None, "chapter_command_adapter": None}
            if existing is not None:
                existing["agent_runtime"]._pool.shutdown(wait=True)
            self._entries[project_id] = entry
            return entry

    @staticmethod
    def _draft_version(runtime, target):
        current = runtime.store.current(target["chapter_number"])
        return current[0].version if current else 0

    def assert_migration_idle(self, project_id):
        """仅读已持久证据及缓存，不因检查而创建Runtime。迁移方须先持租约。"""
        root, _ = validated_project(self.root, project_id)
        assert_persistent_idle(self.root, root, project_id)
        self.assert_cached_migration_idle(project_id)

    def assert_cached_migration_idle(self, project_id):
        """核对异常目录时只检查已缓存任务；源/目标持久检查由核对服务有界执行。"""
        with self._lock:
            entry = self._entries.get(project_id)
            if entry is not None:
                entry["agent_runtime"].assert_migration_idle()

    def invalidate_after_migration(self, project_id):
        """仅丢弃已证实空闲的缓存；不取消或接管创作任务。"""
        with self._lock:
            entry = self._entries.get(project_id)
            if entry is not None:
                runtime = entry["agent_runtime"]
                runtime.assert_migration_idle()
                runtime._pool.shutdown(wait=False)
                del self._entries[project_id]

    def close(self):
        for entry in self._entries.values():
            entry["agent_runtime"]._pool.shutdown(wait=True)


def select_project(handler, *, writable=False):
    request = urlsplit(handler.path)
    if not request.path.startswith("/p/"):
        return False
    parts = request.path.split("/", 3)
    if len(parts) != 4 or handler.project_registry is None:
        handler._agent_error(ValueError("project_route_unavailable"))
        return True
    try:
        project_id = unquote(parts[2])
        entry = handler.project_registry.get(project_id, writable=writable)
        for key, value in entry.items():
            setattr(handler, key, value)
        handler.routed_project_id = project_id
        handler.path = "/" + parts[3] + ("?" + request.query if request.query else "")
    except (ValueError, OSError) as error:
        handler._agent_error(error)
        return True
    return False
