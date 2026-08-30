from dataclasses import replace

from creative_os.domains.narrative_decision import ArcPhase
from creative_os.domains.narrative_progression import evaluate_progression
from tests.test_narrative_review import _decision


def test_progression_detects_phase_regression_and_flat_pressure():
    previous = replace(_decision().with_chapter(6), arc_phase=ArcPhase.TURN)
    current = replace(_decision().with_chapter(7), arc_phase=ArcPhase.ESCALATION)

    report = evaluate_progression(current, [previous])

    codes = {issue.code for issue in report.issues}
    assert {"arc_phase_regression", "flat_pressure_curve"} <= codes
    assert report.phase_changed


def test_progression_detects_repeated_choice_and_unchanged_foreshadowing():
    previous = _decision().with_chapter(6)
    current = _decision().with_chapter(7)

    report = evaluate_progression(current, [previous])

    codes = {issue.code for issue in report.issues}
    assert {"repeated_protagonist_choice", "stagnant_foreshadow_action"} <= codes


def test_progression_does_not_compare_different_arcs():
    previous = replace(_decision().with_chapter(6), arc_id="arc-other")
    current = _decision().with_chapter(7)

    report = evaluate_progression(current, [previous])

    assert not report.issues


def test_progression_uses_semantic_relation_and_keeps_legal_upgrade_non_blocking():
    previous = replace(
        _decision(functions=("建立主角调查",)).with_chapter(6),
        arc_phase=ArcPhase.SETUP,
    )
    repeated = replace(
        _decision(functions=("塑造主角追查",)).with_chapter(7),
        arc_phase=ArcPhase.SETUP,
    )
    upgraded = replace(
        _decision(functions=("升级主角追查",)).with_chapter(7),
        arc_phase=ArcPhase.ESCALATION,
    )
    repeated_report = evaluate_progression(repeated, [previous])
    upgraded_report = evaluate_progression(upgraded, [previous])
    assert "repeated_chapter_function" in {item.code for item in repeated_report.issues}
    assert "repeated_chapter_function" not in {item.code for item in upgraded_report.issues}
    assert any(item.relation.value == "progression"
               for item in upgraded_report.semantic_comparisons)


def test_progression_blocks_uncertain_function_vocabulary():
    previous = _decision(functions=("量子跃迁主角",)).with_chapter(6)
    current = _decision(functions=("量子跃迁主角",)).with_chapter(7)
    report = evaluate_progression(current, [previous])
    assert "uncertain_function_similarity" in {item.code for item in report.issues}
