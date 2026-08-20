import json

import pytest

from creative_os.domains.narrative_evidence import ChapterEvidence, JsonArtifact
from creative_os.domains.narrative_replay import (
    analyze_chapter,
    render_replay_report,
    replay_chapter,
    replay_range,
)


def test_replay_reports_time_opening_and_missing_contract_as_separate_evidence(tmp_path):
    chapter = tmp_path / "production/final_chapters/chapter_001.md"
    chapter.parent.mkdir(parents=True)
    chapter.write_text("# 第1章\n凌晨，林子轩走进龙渊。", encoding="utf-8")

    finding = analyze_chapter(tmp_path, 1, decision=None)

    assert finding.chapter_number == 1
    assert "time_word_opening" in finding.automatic_codes
    assert "missing_narrative_contract" in finding.manual_pending
    report = render_replay_report([finding])
    assert "第 1 章" in report
    assert "人工待定" in report


def test_replay_refuses_to_fabricate_missing_chapter(tmp_path):
    with pytest.raises(FileNotFoundError):
        analyze_chapter(tmp_path, 2, decision=None)


def test_replay_marks_unproven_fields_unknown_without_inferring_from_prose():
    evidence = ChapterEvidence(
        chapter_id="chapter_001",
        prose="# 第一章\n\n林澈决定追查失踪事件。",
        contexts=(),
        reviews=(),
        knowledge=(),
        tasks=(),
        source_refs=("production/final_chapters/chapter_001.md",),
    )

    contract = replay_chapter(evidence)

    assert contract.functions == ("unknown",)
    assert contract.protagonist_choice is None
    assert contract.reader_before == "unknown"
    assert contract.reader_after == "unknown"
    assert contract.ending_shift == "unknown"
    assert contract.evidence


def test_replay_reads_only_explicit_structured_contract_fields():
    evidence = ChapterEvidence(
        chapter_id="chapter_001",
        prose="# 第一章\n\n正文定位。",
        contexts=(
            JsonArtifact(
                source_ref="production/chapter_001/contexts/contract.json",
                data={
                    "chapter_contract": {
                        "functions": ["建立主角困境"],
                        "dramatic_question": "主角是否承担调查风险？",
                        "protagonist_choice": {
                            "actor": "林澈",
                            "action": "继续调查",
                            "alternatives": ["离城"],
                            "cost": "暴露行踪",
                            "consequence": "进入监控名单",
                        },
                        "reader_change": {"before": "怀疑失踪", "after": "确认有人掩盖"},
                        "pressure_curve": {"start": "返城受阻", "end": "遭到监控"},
                        "ending_shift": "林澈被标记为异常人员",
                    }
                },
            ),
        ),
        reviews=(),
        knowledge=(),
        tasks=(),
        source_refs=(
            "production/final_chapters/chapter_001.md",
            "production/chapter_001/contexts/contract.json",
        ),
    )

    contract = replay_chapter(evidence)

    assert contract.functions == ("建立主角困境",)
    assert contract.protagonist_choice is not None
    assert contract.protagonist_choice.cost == "暴露行踪"
    assert contract.reader_after == "确认有人掩盖"
    assert contract.ending_shift == "林澈被标记为异常人员"
    assert any(item.source_ref.endswith("contract.json") for item in contract.evidence)


def test_replay_range_defaults_to_first_six_chapters(tmp_path):
    for chapter_number in range(1, 7):
        chapter_id = f"chapter_{chapter_number:03d}"
        prose = tmp_path / "production" / "final_chapters" / f"{chapter_id}.md"
        prose.parent.mkdir(parents=True, exist_ok=True)
        prose.write_text(f"# 第 {chapter_number} 章\n\n正文。", encoding="utf-8")
        tasks = tmp_path / "production" / chapter_id / "tasks"
        tasks.mkdir(parents=True)
        (tasks / "scene.json").write_text(
            json.dumps({"scene_spec": {"goal": f"功能 {chapter_number}", "outcome": f"结果 {chapter_number}"}}),
            encoding="utf-8",
        )

    contracts = replay_range(tmp_path)

    assert [item.chapter_id for item in contracts] == [f"chapter_{number:03d}" for number in range(1, 7)]
    assert contracts[-1].ending_shift == "结果 6"
