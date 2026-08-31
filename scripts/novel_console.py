from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.console_dashboard import render_console_dashboard
from creative_os.projection.builder import ProjectProjectionBuilder, ProjectProjectionRequest
from creative_os.projection.filesystem_source import FilesystemProjectSource


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root)
    source = FilesystemProjectSource(project_root)
    project_id = source.read_facts().project_id
    result = ProjectProjectionBuilder(source).build(ProjectProjectionRequest(project_id=project_id))
    print(render_console_dashboard(result.snapshot))


if __name__ == "__main__":
    main()
