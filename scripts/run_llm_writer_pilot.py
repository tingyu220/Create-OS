from __future__ import annotations

import argparse
import sys
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
    parser.add_argument("--chapters", default="4,5,6")
    parser.add_argument("--resume", action="store_true", help="Skip chapters that already passed in the latest run record")
    parser.add_argument("--force", action="store_true", help="Run selected chapters even when prior run passed")
    parser.add_argument("--local-repair", action="store_true", help="Use local repair for reader-surface issues")
    args = parser.parse_args()

    chapters = parse_chapters(args.chapters)
    if args.resume and not args.force:
        from creative_os.batch_runner import load_completed_chapters, select_pending_chapters

        run_path = Path(args.project_root) / "llm_writer_pilot" / "runs" / "llm_writer_pilot_run.json"
        chapters = select_pending_chapters(chapters, load_completed_chapters(run_path))

    if not chapters:
        print({"result": "pass", "chapters": [], "skipped": "all selected chapters already passed"})
        return

    record = run_llm_writer_pilot(
        Path(args.project_root),
        OpenAICompatibleClient.from_env(ROOT / ".env"),
        chapters=chapters,
        use_local_repair=args.local_repair,
    )
    print(record)


if __name__ == "__main__":
    main()
