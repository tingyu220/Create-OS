from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import NoReturn


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.projection.filesystem_source import FilesystemProjectSource
from creative_os.projection.repository import FileProjectionRepository, RepositoryRefreshBuilder
from creative_os.web_workspace import WorkspaceWebAdapter, create_server
from creative_os.workspace import CommandBoundary, FileCommandResultStore, ProjectionRefreshCoordinator, ProjectionSection
from creative_os.workspace_command_adapter import WorkspaceCommandAdapter, WorkspaceProjectionRefreshScheduler, WorkspaceRefreshCommandHandler
from creative_os.workspace_query import WorkspaceQueryAdapter


def _workspace_version_reader(_target: str) -> NoReturn:
    """当前项目未定义可用于命令并发控制的领域版本，故安全拒绝读取。"""
    raise RuntimeError("workspace_version_not_supported")


def main() -> None:
    parser = argparse.ArgumentParser(description="启动单小说项目只读 Creative OS Web Workspace")
    parser.add_argument("--project-root", required=True, help="projects/<小说项目> 路径")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--refresh", action="store_true", help="启动前重建一次可丢弃的投影缓存")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    project_id = FilesystemProjectSource(project_root).read_facts().project_id
    repository = FileProjectionRepository(project_root, expected_project_id=project_id)
    coordinator = ProjectionRefreshCoordinator(
        RepositoryRefreshBuilder(project_root, repository), repository.journal_path
    )
    if args.refresh:
        refresh = coordinator.refresh(project_id, set(ProjectionSection))
        if refresh.status.value != "succeeded":
            raise RuntimeError(refresh.diagnostic.message if refresh.diagnostic else "projection_refresh_failed")
    adapter = WorkspaceWebAdapter(WorkspaceQueryAdapter(repository), project_id)
    command_handler = WorkspaceRefreshCommandHandler(project_id)
    command_boundary = CommandBoundary(
        command_handler,
        version_reader=_workspace_version_reader,
        store=FileCommandResultStore(project_root),
        refresh_scheduler=WorkspaceProjectionRefreshScheduler(coordinator),
        request_validator=command_handler.validate,
    )
    server = create_server(
        adapter,
        command_adapter=WorkspaceCommandAdapter(command_boundary),
        host=args.host,
        port=args.port,
    )
    print(f"Creative OS Web Workspace: http://{args.host}:{server.server_address[1]}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
