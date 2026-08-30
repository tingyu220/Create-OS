from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from creative_os.domains.publication_target_materializer import (
    materialize_approved_target,
    verify_materialized_target,
)
from creative_os.runtime.publication_split_approval_store import SplitPlanApprovalStore


def main() -> None:
    parser = argparse.ArgumentParser(description="批准并物化发布版章节拆分")
    parser.add_argument("command", choices=("approve", "materialize", "verify"))
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--migration-id", default="migration-civilization-v2")
    parser.add_argument("--actor", default="tingyu")
    parser.add_argument("--reason", default="批准按戏剧节点拆分目标版正文")
    args = parser.parse_args()

    if args.command == "approve":
        store = SplitPlanApprovalStore(args.project_root)
        try:
            candidate, _, _ = store.load_current_bundle(args.migration_id)
            decision = store.append_decision(
                candidate.candidate_hash, args.actor, args.reason, True,
            )
        finally:
            store.close()
        print(f"approved={decision.candidate_hash} decision={decision.decision_hash}")
        return
    if args.command == "materialize":
        manifest = materialize_approved_target(args.project_root, args.migration_id)
        print(f"materialized={len(manifest['chapters'])} manifest={manifest['manifest_hash']}")
        return
    manifest = verify_materialized_target(args.project_root)
    print(f"verified={len(manifest['chapters'])} manifest={manifest['manifest_hash']}")


if __name__ == "__main__":
    main()
