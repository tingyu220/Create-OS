from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.domains.pov_strategy_model import ChapterNeeds
from creative_os.pov_strategy_shadow import run_pov_strategy_shadow


def main() -> None:
    parser = argparse.ArgumentParser(description="只读检查下一章POV策略候选")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--chapter-needs", required=True, help="ChapterNeeds JSON 文件")
    parser.add_argument("--no-write", action="store_true", help="不写runtime审计工件")
    args = parser.parse_args()
    payload = json.loads(Path(args.chapter_needs).read_text(encoding="utf-8"))
    needs = ChapterNeeds(
        tuple(payload["functions"]), payload["dramatic_question"],
        tuple(payload.get("required_scene_capabilities", ())), payload.get("required_world_slice", ""),
        tuple(payload.get("technology_roles", ())),
    )
    result = run_pov_strategy_shadow(args.project_root, args.chapter, needs, write_audit=not args.no_write)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
