import pytest

from creative_os.domains.narrative_evidence import EvidenceRef
from creative_os.domains.reader_engagement_model import (
    EngagementObligation,
    EngagementPlan,
    EngagementCurve,
    EngagementCurveEntry,
    EngagementIntensity,
    EngagementStatus,
    ChapterEngagementProjection,
    ExpectationTransitionCandidate,
    PlanDecisionRecord,
    EngagementReviewStatus,
    EngagementScope,
    ExpectationState,
    VolumeEngagement,
)


def test_public_engagement_enums_and_evidence_type_are_defined():
    assert {item.value for item in EngagementScope} == {"book", "volume", "arc", "chapter"}
    assert {item.value for item in ExpectationState} == {"open", "escalating", "paid", "abandoned"}
    assert {item.value for item in EngagementReviewStatus} == {"passed", "blocked"}
    assert EvidenceRef.__module__ == "creative_os.domains.narrative_evidence"


def test_task_one_public_authority_models_are_frozen_and_validate_hashes():
    obligation = EngagementObligation("ob-1", "exp-1", "pay", (3, 6), ())
    entry = EngagementCurveEntry(3, EngagementIntensity.HIGH, "arc-1", ("ob-1",), "causal")
    curve = EngagementCurve("plan-1", "a" * 64, (entry,))
    plan = EngagementPlan("project", 1, EngagementStatus.CANDIDATE, "b" * 64)
    projection = ChapterEngagementProjection("plan-1", 1, "b" * 64, "c" * 64, "d" * 64, 3, ("ob-1",), "{}", "e" * 64)
    assert plan.version == 1 and projection.chapter_number == 3 and curve.entries[0].arc_id == "arc-1"
    with pytest.raises(ValueError):
        EngagementObligation("ob-1", "exp-1", "invalid", (3, 6), ())
    with pytest.raises(ValueError):
        PlanDecisionRecord("plan-1", "bad", "curve-1", "bad", "actor", "reason")


def test_transition_candidate_cannot_mutate_nested_evidence():
    candidate = ExpectationTransitionCandidate("exp-1", "absent", "open", "a" * 64, ())
    with pytest.raises((AttributeError, TypeError)):
        candidate.evidence.append("x")


@pytest.mark.parametrize(
    ("objectives", "reason"),
    [
        ((), None),
        (("goal",), "not applicable"),
        ((), " "),
        ((True,), None),
    ],
)
def test_volume_requires_exactly_one_of_objectives_or_na_reason(objectives, reason):
    with pytest.raises(ValueError, match="volume"):
        VolumeEngagement(objectives=objectives, not_applicable_reason=reason)
