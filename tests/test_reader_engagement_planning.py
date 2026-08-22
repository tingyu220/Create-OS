import pytest

from creative_os.domains.reader_engagement_planning import ReaderEngagementPlanningService


def test_planning_service_only_proposes_and_projects():
    service = ReaderEngagementPlanningService()
    assert hasattr(service, "propose")
    assert hasattr(service, "project_chapter")
    assert not hasattr(service, "approve")
    assert not hasattr(service, "activate")


def test_projection_rejects_batch_or_unknown_active_plan():
    service = ReaderEngagementPlanningService()
    with pytest.raises(ValueError, match="active"):
        service.project_chapter("project", 1)


def test_activation_requires_matching_plan_curve_composite_and_projection_is_single_chapter(tmp_path):
    service = ReaderEngagementPlanningService(tmp_path)
    candidate = service.propose(None, {"id": "plan-1", "project_id": "project", "content_hash": "a" * 64})
    recorder = service.plan_decision_recorder()
    decision = recorder.record("plan-1", "a" * 64, "curve-1", "b" * 64, "reviewer", "approved")
    activation = service.plan_activation_service().activate_plan("plan-1", decision.record_id, "0" * 64)
    assert activation.payload["plan_hash"] == "a" * 64
    with pytest.raises(ValueError, match="active"):
        service.project_chapter("project", (1, 2))
