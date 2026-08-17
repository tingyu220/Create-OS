from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.llm_writer import OpenAICompatibleClient
from creative_os.novel_continuation_runner import continue_one_chapter


def main() -> None:
    parser = argparse.ArgumentParser(description="Continue exactly one approved legacy novel chapter")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=1)
    args = parser.parse_args()
    client = None if args.dry_run else OpenAICompatibleClient.from_env()
    result = continue_one_chapter(args.project_root, client=client, dry_run=args.dry_run, max_attempts=args.max_attempts)
    print(f"chapter={result.chapter_number} status={result.status}")


if __name__ == "__main__":
    main()
