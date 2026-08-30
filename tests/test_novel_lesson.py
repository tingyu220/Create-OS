import pytest

from creative_os.domains.novel_lesson import build_lesson_candidate
from creative_os.domains.novel_review_model import NovelReviewIssue


def _issue():
    return NovelReviewIssue(
        code="fragment_chapter",
        severity="error",
        scope="chapter_boundary",
        evidence=("片段位于问题与回应之间，戏剧单元未闭合",),
        repair_kind="merge_or_expand_scene",
        blocking=True,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"issue": None},
        {"repair_action": ""},
        {"validation_evidence": ()},
        {"after_hash": "f" * 63},
    ],
)
def test_lesson_requires_complete_failure_repair_validation_chain(changes):
    values = {
        "issue": _issue(),
        "context_fingerprint": "c" * 64,
        "repair_action": "将回答片段并入后续完整场景",
        "before_hash": "b" * 64,
        "after_hash": "a" * 64,
        "validation_evidence": ("重排后章节达到4516字且长段无重复",),
    }
    values.update(changes)

    with pytest.raises(ValueError, match="lesson_evidence_incomplete"):
        build_lesson_candidate(**values)


def test_lesson_candidate_is_stable_and_never_auto_approved():
    values = {
        "issue": _issue(),
        "context_fingerprint": "c" * 64,
        "repair_action": "将回答片段并入后续完整场景",
        "before_hash": "b" * 64,
        "after_hash": "a" * 64,
        "validation_evidence": ("重排后章节达到4516字且长段无重复",),
    }

    first = build_lesson_candidate(**values)
    second = build_lesson_candidate(**values)

    assert first == second
    assert first.status == "candidate"
    assert first.failure_code == "fragment_chapter"
    assert first.candidate_hash
