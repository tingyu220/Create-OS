from __future__ import annotations

import argparse
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.llm_writer import OpenAICompatibleClient, run_llm_writer_pilot


def parse_chapters(value: str) -> list[int]:
    chapters: list[int] = []
    for item in value.split(","):
        part = item.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            if end < start:
                raise ValueError(f"Invalid chapter range: {part}")
            chapters.extend(range(start, end + 1))
        else:
            chapters.append(int(part))
    return chapters


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default="projects/validation_novel/production")
    parser.add_argument("--target-chapter", type=int, default=5)
    parser.add_argument("--chapters", help=argparse.SUPPRESS)
    parser.add_argument("--resume", action="store_true", help="Skip chapters that already passed in the latest run record")
    parser.add_argument("--force", action="store_true", help="Run selected chapters even when prior run passed")
    parser.add_argument("--local-repair", action="store_true", help="Use local repair for reader-surface issues")
    parser.add_argument("--orchestrator", action="store_true", help="Run through the chapter orchestrator")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    args = parser.parse_args()

    if not args.orchestrator:
        parser.error("direct Writer entry is disabled; invoke the ChapterProductionOrchestrator")

    chapters = [args.target_chapter]
    if args.resume and not args.force:
        from creative_os.batch_runner import load_completed_chapters, select_pending_chapters

        run_path = Path(args.project_root) / "llm_writer_pilot" / "runs" / "llm_writer_pilot_run.json"
        chapters = select_pending_chapters(chapters, load_completed_chapters(run_path))

    if not chapters:
        print({"result": "pass", "chapters": [], "skipped": "all selected chapters already passed"})
        return

    import subprocess
    command = [sys.executable, str(ROOT / "scripts" / "produce_civilization_chapter.py"),
               "--project-root", args.project_root, "--chapter", str(args.target_chapter), "--write"]
    env = dict(os.environ)
    dotenv = Path(args.env_file)
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1); env.setdefault(key.strip(), value.strip())
    raise SystemExit(subprocess.call(command, env=env))


if __name__ == "__main__":
    main()
