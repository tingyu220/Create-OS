from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class CurveIssue:
    code: str
    blocking: bool = True


class EngagementCurveValidator:
    def validate(self, curve: object) -> tuple[CurveIssue, ...]:
        if not isinstance(curve, dict):
            return (CurveIssue("curve_type"),)
        plan_hash = curve.get("plan_hash")
        if not isinstance(plan_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", plan_hash):
            return (CurveIssue("stale_plan_hash"),)
        values = curve.get("values")
        if not isinstance(values, tuple):
            values = tuple(values or ())
        issues: list[CurveIssue] = []
        low_run = 0
        peak_run = 0
        grounded = bool(curve.get("grounded"))
        if grounded and (not curve.get("arc_id") or not curve.get("expectation_obligation_ids") or not curve.get("causal_rationale") or not curve.get("evidence")):
            issues.append(CurveIssue("causal_binding_missing"))
        for value in values:
            if value == "low":
                low_run += 1
                peak_run = 0
            elif value == "peak":
                peak_run += 1
                low_run = 0
            else:
                low_run = peak_run = 0
            if low_run >= 4 and CurveIssue("prolonged_low") not in issues:
                issues.append(CurveIssue("prolonged_low"))
            if peak_run >= 3 and not grounded and CurveIssue("peak_fatigue") not in issues:
                issues.append(CurveIssue("peak_fatigue"))
        if any(value not in {"low", "medium", "high", "peak"} for value in values):
            issues.append(CurveIssue("invalid_intensity"))
        if values and any(value == "peak" for value in values) and not grounded:
            issues.append(CurveIssue("causal_binding_missing"))
        return tuple(issues)
