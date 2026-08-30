from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.release_exporter import export_novel_release


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--output-root", default="releases")
    args = parser.parse_args()

    release_path = export_novel_release(Path(args.project_root), Path(args.output_root))
    print(release_path)


if __name__ == "__main__":
    main()
