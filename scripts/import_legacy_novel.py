from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.importing.materializer import approve_import, materialize_project, report_project, scan_into_project


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a legacy novel without modifying its source directory")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("--source", required=True)
    scan.add_argument("--projects-root", required=True)
    scan.add_argument("--title", required=True)
    for name in ("report", "materialize"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", required=True)
    approve = commands.add_parser("approve")
    approve.add_argument("--project-root", required=True)
    approve.add_argument("--actor", required=True)
    approve.add_argument("--decisions", required=True)
    args = parser.parse_args()
    if args.command == "scan":
        print(scan_into_project(args.source, args.projects_root, args.title))
    elif args.command == "report":
        _, conflicts = report_project(args.project_root)
        print(f"conflicts={len(conflicts)}")
    elif args.command == "approve":
        approve_import(args.project_root, actor=args.actor, decisions_path=args.decisions)
        print("approved")
    else:
        copied = materialize_project(args.project_root)
        print(f"materialized={len(copied)}")


if __name__ == "__main__":
    main()
