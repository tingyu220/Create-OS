import pytest

from creative_os.domains.engagement_curve import EngagementCurveValidator


def test_curve_allows_grounded_peak_but_blocks_prolonged_low_and_ungrounded_peaks():
    validator = EngagementCurveValidator()
    assert validator.validate(grounded_curve()) == ()
    assert "prolonged_low" in codes(validator.validate(curve_with_intensities(("low", "low", "low", "low"))))
    assert "peak_fatigue" in codes(validator.validate(curve_with_intensities(("peak", "peak", "peak"))))


def test_curve_requires_arc_obligation_rationale_and_evidence_binding():
    curve = curve_with_intensities(("high",), grounded=True)
    curve.update({"arc_id": "arc-1", "expectation_obligation_ids": ("ob-1",), "causal_rationale": "turn", "evidence": ("e" * 64,)})
    assert validator().validate(curve) == ()
    curve["evidence"] = ()
    assert "causal_binding_missing" in codes(validator().validate(curve))


def test_curve_rejects_stale_hash_and_invalid_intensity():
    assert "stale_plan_hash" in codes(validator().validate({"plan_hash": "x", "values": ()}))
    assert "invalid_intensity" in codes(validator().validate({"plan_hash": "a" * 64, "values": ("unknown",)}))


def validator():
    return EngagementCurveValidator()


def grounded_curve():
    return curve_with_intensities(("high", "low", "peak"), grounded=True)


def curve_with_intensities(values, grounded=False):
    return {"plan_hash": "a" * 64, "values": values, "grounded": grounded,
            "arc_id": "arc-1" if grounded else None,
            "expectation_obligation_ids": ("ob-1",) if grounded else (),
            "causal_rationale": "turn" if grounded else "",
            "evidence": ("e" * 64,) if grounded else ()}


def codes(issues):
    return {issue.code for issue in issues}
