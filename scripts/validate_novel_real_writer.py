"""运行独立小说 Writer 的 fake 或 live 验收。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.domains.novel_validation_fixture import load_independent_validation_case
from creative_os.llm_writer import OpenAICompatibleClient
from creative_os.novel_writer_validation import run_independent_writer_validation


class _FixtureClient:
    """只返回夹具正文；不读取环境，也不发起网络请求。"""

    model = "fixture-writer"

    def __init__(self, content: str) -> None:
        self._content = content

    def complete(self, messages, *, temperature: float, max_tokens: int) -> str:
        return self._content


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="独立小说 Writer 验收")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--mode", choices=("fake", "live"), required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--env-file", default=".env")
    return parser.parse_args(argv)


def write_report_atomic(path: str | Path, payload: dict[str, object]) -> None:
    """同目录临时文件写完并落盘后，原子替换目标报告。"""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=report_path.parent,
            prefix=f".{report_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, report_path)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        case = load_independent_validation_case(args.fixture)
    except Exception as error:
        print(f"validation_fixture_invalid:{error}", file=sys.stderr)
        return 1

    if args.mode == "fake":
        client = _FixtureClient(case.fake_draft.content)
    else:
        try:
            client = OpenAICompatibleClient.from_env(args.env_file)
        except (OSError, ValueError) as error:
            print(f"live_writer_configuration_missing:{error}", file=sys.stderr)
            return 2

    try:
        report = run_independent_writer_validation(case, client, mode=args.mode)
        write_report_atomic(args.report, report.to_dict())
    except Exception as error:
        print(f"writer_validation_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
