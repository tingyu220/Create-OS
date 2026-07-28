import pytest

from creative_os.foundation.project import (
    Milestone,
    MilestoneStatus,
    Project,
    ProjectLifecycleError,
    ProjectPhase,
)


def test_project_phase_transitions_are_explicit_and_ordered():
    project = Project(id="p1", name="文明升阶", domain="novel")

    with pytest.raises(ProjectLifecycleError):
        project.transition_to(ProjectPhase.DRAFTING)

    project.transition_to(ProjectPhase.PROPOSAL)
    project.transition_to(ProjectPhase.PLANNING)
    project.transition_to(ProjectPhase.DRAFTING)

    assert project.phase == ProjectPhase.DRAFTING


def test_project_progress_is_derived_from_milestones():
    project = Project(
        id="p2",
        name="长篇文章项目",
        domain="article",
        milestones=[
            Milestone(id="m1", title="确定主题", status=MilestoneStatus.DONE),
            Milestone(id="m2", title="完成大纲", status=MilestoneStatus.ACTIVE),
            Milestone(id="m3", title="完成初稿", status=MilestoneStatus.PENDING),
            Milestone(id="m4", title="发布", status=MilestoneStatus.PENDING),
        ],
    )

    assert project.progress == 0.25

    project.complete_milestone("m2")

    assert project.progress == 0.5


def test_project_is_domain_neutral_and_does_not_store_knowledge_content():
    project = Project(id="p3", name="课程项目", domain="course")
    milestone = project.add_milestone("lesson-outline", "课程大纲")

    assert project.domain == "course"
    assert milestone.status == MilestoneStatus.PENDING

    with pytest.raises(ValueError):
        Project(id="p4", name="错误项目", domain="", content="长期正文不能进入 Project")
