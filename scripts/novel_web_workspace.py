from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.projection.filesystem_source import FilesystemProjectSource
from creative_os.projection.repository import FileProjectionRepository, RepositoryRefreshBuilder
from creative_os.web_workspace import WorkspaceWebAdapter, create_server
from creative_os.workspace import ProjectionRefreshCoordinator, ProjectionSection
from creative_os.workspace_query import WorkspaceQueryAdapter


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
    if args.refresh:
        refresh = ProjectionRefreshCoordinator(
            RepositoryRefreshBuilder(project_root, repository), repository.journal_path
        ).refresh(project_id, set(ProjectionSection))
        if refresh.status.value != "succeeded":
            raise RuntimeError(refresh.diagnostic.message if refresh.diagnostic else "projection_refresh_failed")
    adapter = WorkspaceWebAdapter(WorkspaceQueryAdapter(repository), project_id)
    server = create_server(adapter, host=args.host, port=args.port)
    print(f"Creative OS Web Workspace: http://{args.host}:{server.server_address[1]}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
