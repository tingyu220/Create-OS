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
from creative_os.domains.narrative_replay_model import EvidenceRef, ReplayedChapterContract
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


def _replayed_contract(
    *,
    functions=("推进主线",),
    choice=None,
    reader_before="unknown",
    reader_after="unknown",
    ending_shift="unknown",
):
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
    assert all(issue.evidence and issue.repair_hint for issue in issues)


def test_replay_reviewer_reports_missing_cost_and_repeated_function_without_mutation():
    choice = ProtagonistChoice("林澈", "继续调查", (), "unknown", "进入监控名单")
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
