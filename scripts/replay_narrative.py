from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.domains.narrative_replay import replay_range
from creative_os.domains.narrative_replay_model import ReplayedChapterContract, UNKNOWN
from creative_os.domains.narrative_review import review_replayed_contract


def run(project_root: Path, start: int, end: int, output_dir: Path) -> dict[str, object]:
    contracts = replay_range(project_root, start=start, end=end)
    chapters: list[dict[str, object]] = []
    issue_count = 0
    unknown_field_count = 0
    for index, contract in enumerate(contracts):
        issues = review_replayed_contract(contract, recent=contracts[max(0, index - 3):index])
        unknown_fields = _unknown_fields(contract)
        issue_count += len(issues)
        unknown_field_count += len(unknown_fields)
        chapters.append({
            "chapter_id": contract.chapter_id,
            "contract": asdict(contract),
            "issues": [asdict(issue) for issue in issues],
            "unknown_fields": list(unknown_fields),
        })

    payload: dict[str, object] = {
        "project_id": project_root.name,
        "start": start,
        "end": end,
        "chapter_count": len(contracts),
        "issue_count": issue_count,
        "unknown_field_count": unknown_field_count,
        "traceable": all(contract.evidence for contract in contracts),
        "chapters": chapters,
    }
    json_content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown_content = _render_markdown(payload, contracts)

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"narrative_replay_{start:03d}_{end:03d}"
    _atomic_write(output_dir / f"{stem}.json", json_content)
    _atomic_write(output_dir / f"{stem}.md", markdown_content)
    return payload


def _unknown_fields(contract: ReplayedChapterContract) -> tuple[str, ...]:
    values = {
        "functions": contract.functions == (UNKNOWN,),
        "dramatic_question": contract.dramatic_question == UNKNOWN,
        "protagonist_choice": contract.protagonist_choice is None,
        "reader_before": contract.reader_before == UNKNOWN,
        "reader_after": contract.reader_after == UNKNOWN,
        "pressure_start": contract.pressure_start == UNKNOWN,
        "pressure_end": contract.pressure_end == UNKNOWN,
        "ending_shift": contract.ending_shift == UNKNOWN,
    }
    return tuple(name for name, unknown in values.items() if unknown)


def _render_markdown(payload: dict[str, object], contracts: tuple[ReplayedChapterContract, ...]) -> str:
    chapter_payloads = payload["chapters"]
    if not isinstance(chapter_payloads, list):
        raise TypeError("chapters payload must be a list")
    lines = [
        "# 章节叙事回放报告",
        "",
        f"- 项目：`{payload['project_id']}`",
        f"- 范围：{payload['start']}-{payload['end']}",
        f"- 章节数：{payload['chapter_count']}",
        f"- Issue 数：{payload['issue_count']}",
        f"- 不确定字段数：{payload['unknown_field_count']}",
        f"- 结论可追溯：{'是' if payload['traceable'] else '否'}",
        "",
    ]
    for contract, chapter_payload in zip(contracts, chapter_payloads, strict=True):
        if not isinstance(chapter_payload, dict):
            raise TypeError("chapter payload must be an object")
        issues = chapter_payload.get("issues", [])
        unknown_fields = chapter_payload.get("unknown_fields", [])
        choice = contract.protagonist_choice
        lines.extend([
            f"## {contract.chapter_id}",
            "",
            f"- 章节功能：{'；'.join(contract.functions)}",
            f"- 戏剧问题：{contract.dramatic_question}",
            f"- 主角选择：{choice.action if choice else UNKNOWN}",
            f"- 选择代价：{choice.cost if choice else UNKNOWN}",
            f"- 读者变化：{contract.reader_before} -> {contract.reader_after}",
            f"- 压力变化：{contract.pressure_start} -> {contract.pressure_end}",
            f"- 结尾变化：{contract.ending_shift}",
            f"- 不确定项：{'、'.join(str(item) for item in unknown_fields) if unknown_fields else '无'}",
            f"- Issue：{'、'.join(str(item.get('code')) for item in issues if isinstance(item, dict)) if issues else '无'}",
            "- 证据：",
        ])
        lines.extend(
            f"  - `{item.source_ref}`：{item.excerpt}"
            for item in contract.evidence
        )
        lines.append("")
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay existing chapters into evidence-backed narrative contracts")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=6)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or args.project_root / "production" / "reports"
    result = run(args.project_root, args.start, args.end, output_dir)
    print(
        f"chapters={result['chapter_count']} issues={result['issue_count']} "
        f"unknown={result['unknown_field_count']} traceable={result['traceable']}"
    )


if __name__ == "__main__":
    main()
