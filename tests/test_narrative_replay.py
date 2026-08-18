import pytest

from creative_os.domains.narrative_replay import analyze_chapter, render_replay_report


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
