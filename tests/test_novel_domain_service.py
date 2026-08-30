from creative_os.domains.novel import NovelDomainPackage
from creative_os.domains.novel_domain_service import NovelDomainService
from creative_os.domains.novel_lesson import NovelLessonBuilder
from creative_os.domains.novel_review_model import NovelReviewIssue


class _Collaborator:
    pass


def _service() -> NovelDomainService:
    dependency = _Collaborator()
    return NovelDomainService(
        planner=dependency,
        admission=dependency,
        writer=dependency,
        reviewer=dependency,
        compiler=dependency,
        lesson_builder=dependency,
    )


def test_novel_domain_exposes_executable_capabilities():
    expected = (
        "chapter_planning",
        "writer_admission",
        "draft_writing",
        "draft_review",
        "approved_compile",
        "lesson_candidate",
    )

    assert _service().capabilities().names == expected
    assert NovelDomainPackage().capability_names == expected


def test_novel_domain_service_requires_every_collaborator():
    dependency = _Collaborator()

    try:
        NovelDomainService(
            planner=None,
            admission=dependency,
            writer=dependency,
            reviewer=dependency,
            compiler=dependency,
            lesson_builder=dependency,
        )
    except ValueError as error:
        assert str(error) == "novel_domain_collaborator_missing:planner"
    else:
        raise AssertionError("缺少 Planner 时必须失败关闭")


def test_lesson_capability_is_executable_through_domain_service():
    dependency = _Collaborator()
    service = NovelDomainService(
        planner=dependency,
        admission=dependency,
        writer=dependency,
        reviewer=dependency,
        compiler=dependency,
        lesson_builder=NovelLessonBuilder(),
    )
    issue = NovelReviewIssue(
        "fragment_chapter", "error", "chapter", ("片段未闭合",),
        "merge_or_expand_scene", True,
    )

    lesson = service.build_lesson_candidate(
        issue=issue,
        context_fingerprint="c" * 64,
        repair_action="合并到后续完整场景",
        before_hash="b" * 64,
        after_hash="a" * 64,
        validation_evidence=("重排后通过章节边界审查",),
    )

    assert lesson.status == "candidate"
