from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.novel_project import create_novel_project


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", default="")
    parser.add_argument("--genre", default="")
    parser.add_argument("--projects-root", default="projects")
    args = parser.parse_args()

    project_path = create_novel_project(Path(args.projects_root), args.title, author=args.author, genre=args.genre)
    print(project_path)


if __name__ == "__main__":
    main()
