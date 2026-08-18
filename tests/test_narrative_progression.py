from dataclasses import replace

from creative_os.domains.narrative_decision import ArcPhase
from creative_os.domains.narrative_progression import evaluate_progression
from tests.test_narrative_review import _decision


def test_progression_detects_phase_regression_and_flat_pressure():
    previous = replace(_decision(), chapter=6, arc_phase=ArcPhase.TURN)
    current = replace(_decision(), chapter=7, arc_phase=ArcPhase.ESCALATION)

    report = evaluate_progression(current, [previous])

    codes = {issue.code for issue in report.issues}
    assert {"arc_phase_regression", "flat_pressure_curve"} <= codes
    assert report.phase_changed


def test_progression_detects_repeated_choice_and_unchanged_foreshadowing():
    previous = replace(_decision(), chapter=6)
    current = replace(_decision(), chapter=7)

    report = evaluate_progression(current, [previous])

    codes = {issue.code for issue in report.issues}
    assert {"repeated_protagonist_choice", "stagnant_foreshadow_action"} <= codes


def test_progression_does_not_compare_different_arcs():
    previous = replace(_decision(), chapter=6, arc_id="arc-other")
    current = replace(_decision(), chapter=7)

    report = evaluate_progression(current, [previous])

    assert not report.issues
