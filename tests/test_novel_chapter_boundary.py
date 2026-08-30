import pytest

from creative_os.domains.novel_chapter_boundary import ChapterBoundary, assess_boundary


def _boundary(*, dialogue_closed=True, dramatic_unit_closed=True, chars=3400):
    return ChapterBoundary(
        entry_state="主角带着未解问题进入现场",
        exit_state="主角作出选择并承担后果",
        ending_function="decision",
        dialogue_closed=dialogue_closed,
        dramatic_unit_closed=dramatic_unit_closed,
        estimated_chinese_chars=chars,
    )


@pytest.mark.parametrize(
    "dialogue_closed,dramatic_unit_closed,expected",
    [
        (False, True, "dialogue_cut"),
        (True, False, "dramatic_unit_incomplete"),
        (False, False, "fragment_chapter"),
    ],
)
def test_boundary_rejects_incomplete_units(dialogue_closed, dramatic_unit_closed, expected):
    assessment = assess_boundary(_boundary(
        dialogue_closed=dialogue_closed,
        dramatic_unit_closed=dramatic_unit_closed,
        chars=1200 if not dialogue_closed and not dramatic_unit_closed else 3400,
    ))

    assert expected in assessment.blocking_codes


def test_boundary_accepts_complete_dramatic_unit():
    assessment = assess_boundary(_boundary())

    assert assessment.approved
    assert assessment.blocking_codes == ()
