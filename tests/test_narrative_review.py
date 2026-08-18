from creative_os.domains.narrative_decision import (
    ArcPhase,
    ChapterContract,
    InformationPlan,
    NarrativeDecision,
    PressureCurve,
    ProtagonistChoice,
    ReaderChange,
)
from creative_os.domains.narrative_review import review_narrative


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
