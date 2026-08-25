from creative_os.domains.narrative_decision import (
    ArcPhase,
    ChapterContract,
    InformationPlan,
    NarrativeDecision,
    PressureCurve,
    ProtagonistChoice,
    ReaderChange,
    SceneContract,
    ScenePlan,
    TechnologyContract,
    TechnologyPlan,
    PointOfViewPlan,
    SupportingAgencyContract,
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


def test_review_reports_declared_location_world_slice_and_technology_not_dramatized():
    contract = _decision()
    planned = replace(
        contract,
        schema_version=2,
        chapter_contract=replace(
            contract.chapter_contract,
            scene_plan=ScenePlan(scenes=(SceneContract(
                   "scene-1", 1, "gobi", "西北戈壁试验场", "field", "exterior", "深夜",
                   ("林子轩", "工人"), "林子轩", True, "查故障", "工期冲突", "现场停机",
                   "确认旧图缺失", "试验暂停", "远程数据不足", "完成复盘",
            ),), chapter_spatial_intent="现场行动", required_world_slice="普通工人", allowed_same_place_run=2),
            technology_plan=TechnologyPlan(technologies=(TechnologyContract(
                   "fusion", "耐高热偏滤器", "core", "解决热流烧蚀", "CMB理论工程化", ("耐热材料",),
                   "现场试验", "试验堆停机复核", ("工业热交换",), "工期延期", ("ordinary_life",),
            ),)),
        ),
    )

    codes = _codes(review_narrative(planned, recent_contracts=[], text="林子轩留在基地会议室查看数据。"))

    assert {"declared_location_not_dramatized", "external_world_slice_missing", "technology_application_missing"} <= codes


def test_review_does_not_accept_isolated_location_and_technology_name_mentions():
    contract = _decision()
    planned = replace(
        contract,
        schema_version=2,
        chapter_contract=replace(
            contract.chapter_contract,
            scene_plan=ScenePlan(scenes=(SceneContract(
                "scene-1", 1, "gobi", "西北戈壁试验场", "field", "exterior", "深夜",
                ("林子轩", "工人"), "林子轩", True, "查故障", "工期冲突", "现场停机",
                "确认旧图缺失", "试验暂停", "远程数据不足", "完成复盘",
            ),), chapter_spatial_intent="现场行动", required_world_slice="普通工人", allowed_same_place_run=2),
            technology_plan=TechnologyPlan(technologies=(TechnologyContract(
                "fusion", "耐高热偏滤器", "core", "解决热流烧蚀", "CMB理论工程化", ("耐热材料",),
                "现场试验", "试验堆停机复核", ("工业热交换",), "工期延期", ("ordinary_life",),
            ),)),
        ),
    )

    codes = _codes(review_narrative(
        planned, recent_contracts=[], text="报告页脚列着西北戈壁试验场和耐高热偏滤器。",
    ))

    assert "declared_location_not_dramatized" in codes
    assert "external_world_slice_missing" in codes
    assert "technology_application_missing" in codes


def test_review_requires_supporting_character_choice_to_change_mainline():
    contract = _decision()
    agency = SupportingAgencyContract("韩宁", "查明裂纹", "工期压力", "拉下停机闸", "承担延期", "首堆停机", "旧图进入复盘")
    scene = SceneContract("s1", 1, "plant", "十九号厂房", "field", "interior", "深夜", ("韩宁", "工人"), "韩宁", True, "查明裂纹", "工期压力", "拉下停机闸", "旧图缺陷", "首堆停机", "联调异常", "进入复盘")
    planned = replace(contract, schema_version=2, chapter_contract=replace(
        contract.chapter_contract,
        scene_plan=ScenePlan((scene,), "工程现场", "现场工人"),
        pov_plan=PointOfViewPlan("韩宁", "limited", False, (agency,), "配角主导"),
    ))

    codes = _codes(review_narrative(planned, [], "十九号厂房里，韩宁查明裂纹，但没有作出选择。"))
    assert "supporting_agency_not_dramatized" in codes
from dataclasses import replace
