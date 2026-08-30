from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from creative_os.domains.publication_reflow_materializer import materialize_publication_reflow


def main() -> None:
    parser = argparse.ArgumentParser(description="按已批准方案重排发布版章节")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    manifest = materialize_publication_reflow(args.project_root, spec_path=args.spec)
    print(f"materialized={len(manifest['chapters'])} manifest={manifest['manifest_hash']}")


if __name__ == "__main__":
    main()
