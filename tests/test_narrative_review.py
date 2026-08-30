from dataclasses import replace

import pytest

from creative_os.domains.narrative_decision import (
    ArcPhase,
    ChapterContract,
    InformationPlan,
    NarrativeDecision,
    PressureCurve,
    ProtagonistChoice,
    ChoiceStatus,
    ReaderChange,
)
from creative_os.domains.narrative_review import review_narrative
from creative_os.domains.narrative_replay_model import (
    EvidenceRef, ReplayedChapterContract, ReplayedProtagonistChoice,
)
from creative_os.domains.narrative_review import review_replayed_contract


def _decision(functions=("推进主线",), *, foreshadow_actions=("加深钥匙线索",), forbidden=("周远是发送者",)):
    return NarrativeDecision(
        chapter=7,
        profile_id="profile",
        volume_id="volume-1",
        arc_id="arc-1",
        arc_phase=ArcPhase.ESCALATION,
        arc_goal="调查第九区日志",
        inherited_pressure="封控",
        future_pressures=("审查",),
        chapter_contract=ChapterContract(
            functions=functions,
            dramatic_question="主角是否调查？",
            protagonist_choice=ProtagonistChoice("林子轩", "调查日志", ("等待",), "关系受损", "进入审查"),
            reader_change=ReaderChange("读者怀疑", "读者确认风险"),
            information=InformationPlan(("日志覆盖",), ("覆盖者身份",), ()),
            pressure_curve=PressureCurve("封控", "违令", "审查"),
            foreshadow_actions=foreshadow_actions,
            ending_shift="主角被审查",
            target_chinese_chars=7000,
            forbidden=forbidden,
        ),
    )


def _codes(issues):
    return {issue.code for issue in issues}


def test_review_reports_repeated_function_time_opening_and_forbidden_reveal():
    contract = _decision()
    issues = review_narrative(
        contract,
        recent_contracts=[_decision()],
        text="凌晨，林子轩确认周远是发送者。",
    )

    assert {"duplicate_recent_function", "repeated_time_opening", "forbidden_information_revealed"} <= _codes(issues)
    assert all(issue.evidence for issue in issues)


def test_review_reports_missing_foreshadow_action_without_modifying_contract():
    contract = _decision(foreshadow_actions=())
    before = contract

    issues = review_narrative(contract, recent_contracts=[], text="林子轩走进走廊。")

    assert "missing_foreshadow_action" in _codes(issues)
    assert contract == before


def test_formal_reviewer_splits_partial_choice_into_exact_field_issues():
    original = _decision()
    partial_choice = ProtagonistChoice(
        "林子轩",
        "调查日志",
        (),
        None,
        None,
        status=ChoiceStatus.PARTIAL,
        missing_fields=("alternatives", "cost", "consequence"),
    )
    contract = replace(
        original,
        chapter_contract=replace(original.chapter_contract, protagonist_choice=partial_choice),
    )

    issues = review_narrative(contract, recent_contracts=[], text="林子轩走进走廊。")
    by_code = {issue.code: issue for issue in issues}

    assert {
        "partial_protagonist_choice",
        "missing_choice_alternatives",
        "missing_choice_cost",
        "missing_choice_consequence",
    } <= by_code.keys()
    assert by_code["missing_choice_alternatives"].evidence.endswith(".alternatives")
    assert by_code["missing_choice_cost"].evidence.endswith(".cost")
    assert by_code["missing_choice_consequence"].evidence.endswith(".consequence")


def test_formal_partial_choice_binds_each_actual_missing_field_separately():
    original = _decision()
    partial_choice = ProtagonistChoice(
        None,
        None,
        ("等待",),
        "关系受损",
        "进入审查",
        status=ChoiceStatus.PARTIAL,
        missing_fields=("actor", "action"),
    )
    contract = replace(
        original,
        chapter_contract=replace(original.chapter_contract, protagonist_choice=partial_choice),
    )

    issues = review_narrative(contract, recent_contracts=[], text="林子轩继续调查。")
    partial_issues = tuple(issue for issue in issues if issue.code == "partial_protagonist_choice")

    assert tuple(issue.evidence for issue in partial_issues) == (
        "chapter_contract.protagonist_choice.actor",
        "chapter_contract.protagonist_choice.action",
    )
    assert len({issue.evidence for issue in partial_issues}) == 2


@pytest.mark.parametrize(
    ("alternatives", "expected_path"),
    (
        (("unknown",), "chapter_contract.protagonist_choice.alternatives[0]"),
        (("等待", "  "), "chapter_contract.protagonist_choice.alternatives[1]"),
    ),
)
def test_formal_reviewer_reports_each_unknown_or_blank_complete_choice_alternative(
    alternatives: tuple[str, ...],
    expected_path: str,
):
    original = _decision()
    choice = replace(original.chapter_contract.protagonist_choice, alternatives=alternatives)
    contract = replace(
        original,
        chapter_contract=replace(original.chapter_contract, protagonist_choice=choice),
    )

    issues = review_narrative(contract, recent_contracts=[], text="林子轩继续调查。")
    alternative_issues = tuple(issue for issue in issues if issue.code == "missing_choice_alternatives")

    assert len(alternative_issues) == 1
    assert alternative_issues[0].severity == "high"
    assert alternative_issues[0].evidence == expected_path


def _replayed_contract(
    *,
    functions=("推进主线",),
    choice=None,
    reader_before="unknown",
    reader_after="unknown",
    ending_shift="unknown",
):
    if choice is None:
        choice = ReplayedProtagonistChoice(ChoiceStatus.UNKNOWN)
    return ReplayedChapterContract(
        chapter_id="chapter_001",
        functions=functions,
        dramatic_question="unknown",
        protagonist_choice=choice,
        evidence=(EvidenceRef("task", "production/chapter_001/tasks/scene.json", "goal: 推进主线"),),
        reader_before=reader_before,
        reader_after=reader_after,
        ending_shift=ending_shift,
    )


def test_replay_reviewer_reports_unknown_fields_with_evidence_and_repair_hint():
    contract = _replayed_contract()

    issues = review_replayed_contract(contract)

    assert {
        "missing_protagonist_choice",
        "unknown_reader_change",
        "unknown_ending_shift",
    } <= {issue.code for issue in issues}
    assert all(issue.severity == "warning" for issue in issues)
    assert all(issue.repair_hint for issue in issues)
    choice_issue = next(issue for issue in issues if issue.code == "missing_protagonist_choice")
    assert choice_issue.evidence == ()


def test_replay_reviewer_reports_missing_cost_and_repeated_function_without_mutation():
    choice = ReplayedProtagonistChoice(
        ChoiceStatus.PARTIAL, "林澈", "继续调查", (), "unknown", "进入监控名单",
        ("alternatives", "cost"),
    )
    previous = _replayed_contract(
        choice=choice,
        reader_before="怀疑",
        reader_after="确认",
        ending_shift="被监控",
    )
    current = _replayed_contract(
        choice=choice,
        reader_before="怀疑",
        reader_after="确认",
        ending_shift="被监控",
    )
    before = current

    issues = review_replayed_contract(current, recent=(previous,))

    assert {"missing_choice_cost", "repeated_chapter_function"} <= {issue.code for issue in issues}
    assert "missing_protagonist_choice" not in {issue.code for issue in issues}
    assert current == before


def test_replay_reviewer_splits_partial_and_each_missing_choice_field_without_generic_evidence():
    choice = ReplayedProtagonistChoice(
        ChoiceStatus.PARTIAL, "林澈", "继续调查", (), "unknown", "unknown",
        ("alternatives", "cost", "consequence"),
    )
    contract = _replayed_contract(
        choice=choice,
        reader_before="怀疑",
        reader_after="确认",
        ending_shift="被监控",
    )

    issues = review_replayed_contract(contract)

    choice_issues = tuple(issue for issue in issues if "choice" in issue.code or "protagonist_choice" in issue.code)
    assert {issue.code for issue in choice_issues} == {
        "partial_protagonist_choice",
        "missing_choice_alternatives",
        "missing_choice_cost",
        "missing_choice_consequence",
    }
    assert all(issue.evidence == () for issue in choice_issues)
    partial = next(issue for issue in choice_issues if issue.code == "partial_protagonist_choice")
    assert "alternatives" in partial.message and "cost" in partial.message and "consequence" in partial.message


def test_replay_reviewer_treats_explicit_unknown_choice_as_missing_choice_only():
    choice = ReplayedProtagonistChoice(ChoiceStatus.UNKNOWN)
    contract = _replayed_contract(
        choice=choice,
        reader_before="怀疑",
        reader_after="确认",
        ending_shift="被监控",
    )

    issues = review_replayed_contract(contract)

    assert {issue.code for issue in issues} == {"missing_protagonist_choice"}
    assert issues[0].evidence == ()
