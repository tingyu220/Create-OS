from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.memory.approval import approve_candidate, archive_memory, reject_candidate
from creative_os.memory.store import JsonMemoryStore, _item_to_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Review Creative OS memory candidates")
    parser.add_argument("--memory-root", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list")
    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("memory_id")

    for name in ("approve", "reject", "archive"):
        command_parser = subparsers.add_parser(name)
        command_parser.add_argument("memory_id")
        command_parser.add_argument("--actor", required=True)
        command_parser.add_argument("--note", default="")

    args = parser.parse_args()
    store = JsonMemoryStore(args.memory_root)
    if args.command == "list":
        for item in store.list():
            print(f"{item.id}\t{item.status.value}\t{item.title}")
        return
    if args.command == "show":
        print(json.dumps(_item_to_dict(store.get(args.memory_id)), ensure_ascii=False, indent=2))
        return

    operation = {
        "approve": approve_candidate,
        "reject": reject_candidate,
        "archive": archive_memory,
    }[args.command]
    item = operation(store, args.memory_id, actor=args.actor, note=args.note)
    print(f"{item.id}\t{item.status.value}")


if __name__ == "__main__":
    main()
