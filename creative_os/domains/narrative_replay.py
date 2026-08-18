from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from creative_os.domains.narrative_decision import NarrativeDecision
from creative_os.domains.narrative_review import TIME_OPENERS, review_narrative


@dataclass(frozen=True, slots=True)
class ReplayFinding:
    chapter_number: int
    source: str
    opening: str
    automatic_codes: tuple[str, ...]
    evidence: tuple[str, ...]
    manual_pending: tuple[str, ...]


def analyze_chapter(
    project_root: str | Path,
    chapter_number: int,
    decision: NarrativeDecision | None,
) -> ReplayFinding:
    if chapter_number < 1:
        raise ValueError("chapter_number must be positive")
    root = Path(project_root)
    path = root / "production" / "final_chapters" / f"chapter_{chapter_number:03d}.md"
    text = path.read_text(encoding="utf-8")
    opening = _opening(text)
    codes: list[str] = []
    evidence: list[str] = []
    pending: list[str] = []
    if any(opening.startswith(word) for word in TIME_OPENERS):
        codes.append("time_word_opening")
        evidence.append(f"opening: {opening}")
    scene_headings = [line.strip() for line in text.splitlines() if line.strip().startswith("##")]
    if scene_headings:
        codes.append("markdown_scene_headings_present")
        evidence.append("scene_headings: " + " | ".join(scene_headings[:3]))
    if decision is None:
        pending.append("missing_narrative_contract")
    else:
        issues = review_narrative(decision, recent_contracts=[], text=text)
        codes.extend(issue.code for issue in issues)
        evidence.extend(f"{issue.code}: {issue.evidence}" for issue in issues)
    return ReplayFinding(
        chapter_number=chapter_number,
        source=path.relative_to(root).as_posix(),
        opening=opening,
        automatic_codes=tuple(dict.fromkeys(codes)),
        evidence=tuple(evidence),
        manual_pending=tuple(pending),
    )


def render_replay_report(findings: list[ReplayFinding]) -> str:
    lines = ["# 《文明升阶》叙事回放报告", "", "本报告只读取正式正文；没有合同的章节不会被系统臆测。", ""]
    for finding in sorted(findings, key=lambda item: item.chapter_number):
        lines.extend([f"## 第 {finding.chapter_number} 章", "", f"- 来源：`{finding.source}`", f"- 开头：{finding.opening}"])
        lines.append(f"- 自动检测：{'、'.join(finding.automatic_codes) if finding.automatic_codes else '未发现'}")
        lines.append(f"- 人工待定：{'、'.join(finding.manual_pending) if finding.manual_pending else '无'}")
        if finding.evidence:
            lines.append("- 证据：")
            lines.extend(f"  - {evidence}" for evidence in finding.evidence)
        lines.append("")
    return "\n".join(lines)


def _opening(text: str) -> str:
    for line in text.splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            return value[:160]
    return ""
