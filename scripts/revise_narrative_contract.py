from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.domains.narrative_memory import save_narrative_candidate
from creative_os.memory.approval import approve_candidate
from creative_os.memory.model import MemoryEvidence
from creative_os.memory.store import JsonMemoryStore
from scripts.prepare_narrative_validation import build_decisions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--actor", default="tingyu")
    args = parser.parse_args()
    root = Path(args.project_root)
    decision = next(item for item in build_decisions() if item.chapter == args.chapter)
    store = JsonMemoryStore(root / ".creative_os" / "memory")
    item_id = f"narrative-chapter-{args.chapter:03d}"
    revised = store.save_revision(item_id, content=decision.to_json(), actor=args.actor)
    approve_candidate(store, revised.id, actor=args.actor, note=f"修订第{args.chapter}章阶段标注，修复剧情阶段误判")
    print(f"revised={revised.id} status=active")


if __name__ == "__main__":
    main()
