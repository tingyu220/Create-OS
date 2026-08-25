import json
from dataclasses import replace

import pytest

from creative_os.domains.narrative_decision import (
    ArcPhase,
    ChapterContract,
    InformationPlan,
    NarrativeChangeRequest,
    NarrativeDecision,
    NarrativeProjectProfile,
    NarrativeValidationError,
    PressureCurve,
    ProtagonistChoice,
    ReaderChange,
    SceneContract,
    ScenePlan,
    StoryContract,
    StoryArc,
    StoryVolume,
    TechnologyContract,
    TechnologyPlan,
    PointOfViewPlan,
    SupportingAgencyContract,
    WrittenTextStrategy,
)


def _profile() -> NarrativeProjectProfile:
    return NarrativeProjectProfile(
        id="civilization-profile",
        story_contract=StoryContract(
            core_question="林子轩能否在九年窗口结束前确认文明升阶的代价？",
            reader_promise=("世界规则会逐步揭开", "主角的选择会改变局势"),
            theme_conflict="真相与安全如何取舍",
            invariants=("D-7 的事实不能被无记录改写",),
        ),
        volumes=(StoryVolume(id="volume-1", goal="确认龙渊隐瞒的代价", irreversible_change="林子轩失去普通生活"),),
        arcs=(StoryArc(id="arc-identity", volume_id="volume-1", goal="确认林子轩与 D-7 的关系", phase=ArcPhase.ESCALATION),),
    )


def _decision() -> NarrativeDecision:
    return NarrativeDecision(
        chapter=7,
        profile_id="civilization-profile",
        volume_id="volume-1",
        arc_id="arc-identity",
        arc_phase=ArcPhase.ESCALATION,
        arc_goal="将短信疑点转化为主角的主动调查",
        inherited_pressure="林子轩知道自己可能被当作投递工具",
        future_pressures=("第九区权限将被收紧",),
        chapter_contract=ChapterContract(
            functions=("推进主线", "改变人物关系"),
            dramatic_question="林子轩是否愿意违背父亲的安排追查短信？",
            protagonist_choice=ProtagonistChoice(
                actor="林子轩",
                action="主动要求查看第九区日志",
                alternatives=("留在安全宿舍等待",),
                cost="与林正弘的信任进一步受损",
                consequence="被纳入权限审查名单",
            ),
            reader_change=ReaderChange(
                before="读者怀疑短信来自内部泄露",
                after="读者确认林子轩本人也可能是投递链路的一部分",
            ),
            information=InformationPlan(
                reveal=("第九区日志存在人为覆盖痕迹",),
                withhold=("覆盖者身份",),
                misdirect=("表面嫌疑指向周远",),
            ),
            pressure_curve=PressureCurve(start="封控后的窒息", turn="主动违令", end="权限审查启动"),
            foreshadow_actions=("加深周远留下钥匙算法的异常性",),
            ending_shift="林子轩从被保护者变为被审查对象",
            target_chinese_chars=7000,
            forbidden=("不得确认短信发送者身份",),
        ),
    )


def test_profile_and_decision_round_trip_without_manuscript_content():
    profile = _profile()
    decision = _decision()

    payload = json.loads(decision.to_json())

    assert NarrativeProjectProfile.from_json(profile.to_json()) == profile
    assert NarrativeDecision.from_json(decision.to_json()) == decision
    assert payload["chapter_contract"]["target_chinese_chars"] == 7000
    assert "manuscript" not in payload


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("cost", ""),
        ("reader_after", ""),
        ("ending_shift", ""),
        ("target_chinese_chars", 0),
    ],
)
def test_decision_rejects_missing_required_chapter_contract_field(field, replacement):
    decision = _decision()
    contract = decision.chapter_contract
    choice = contract.protagonist_choice
    reader_change = contract.reader_change
    values = {
        "cost": choice.cost,
        "reader_after": reader_change.after,
        "ending_shift": contract.ending_shift,
        "target_chinese_chars": contract.target_chinese_chars,
    }
    values[field] = replacement
    invalid_contract = ChapterContract(
        functions=contract.functions,
        dramatic_question=contract.dramatic_question,
        protagonist_choice=ProtagonistChoice(
            actor=choice.actor,
            action=choice.action,
            alternatives=choice.alternatives,
            cost=values["cost"],
            consequence=choice.consequence,
        ),
        reader_change=ReaderChange(before=reader_change.before, after=values["reader_after"]),
        information=contract.information,
        pressure_curve=contract.pressure_curve,
        foreshadow_actions=contract.foreshadow_actions,
        ending_shift=values["ending_shift"],
        target_chinese_chars=values["target_chinese_chars"],
        forbidden=contract.forbidden,
    )

    with pytest.raises(NarrativeValidationError):
        NarrativeDecision(
            chapter=decision.chapter,
            profile_id=decision.profile_id,
            volume_id=decision.volume_id,
            arc_id=decision.arc_id,
            arc_phase=decision.arc_phase,
            arc_goal=decision.arc_goal,
            inherited_pressure=decision.inherited_pressure,
            future_pressures=decision.future_pressures,
            chapter_contract=invalid_contract,
        ).validate()


def test_profile_rejects_arc_that_does_not_belong_to_declared_volume():
    profile = _profile()
    invalid_profile = NarrativeProjectProfile(
        id=profile.id,
        story_contract=profile.story_contract,
        volumes=profile.volumes,
        arcs=(StoryArc(id="arc-invalid", volume_id="missing-volume", goal="无效", phase=ArcPhase.SETUP),),
    )

    with pytest.raises(NarrativeValidationError):
        invalid_profile.validate()


def test_change_request_round_trip_tracks_impact_without_rewriting_text():
    request = NarrativeChangeRequest(
        id="change-7",
        reason="林子轩的主动选择使原计划不可行",
        old_plan="等待父亲安排",
        new_plan="主动调查第九区日志",
        affected_chapters=(7, 8),
        affected_state_subjects=("林子轩", "林正弘"),
        affected_hooks=("第九区发送者",),
        written_text_strategy=WrittenTextStrategy.KEEP,
    )

    payload = json.loads(request.to_json())

    assert NarrativeChangeRequest.from_json(request.to_json()) == request
    assert payload["written_text_strategy"] == "keep"


def test_v2_decision_round_trip_preserves_scene_and_technology_plans():
    decision = _decision()
    contract = decision.chapter_contract
    planned = NarrativeDecision(
        chapter=decision.chapter,
        profile_id=decision.profile_id,
        volume_id=decision.volume_id,
        arc_id=decision.arc_id,
        arc_phase=decision.arc_phase,
        arc_goal=decision.arc_goal,
        inherited_pressure=decision.inherited_pressure,
        future_pressures=decision.future_pressures,
        chapter_contract=ChapterContract(
            functions=contract.functions,
            dramatic_question=contract.dramatic_question,
            protagonist_choice=contract.protagonist_choice,
            reader_change=contract.reader_change,
            information=contract.information,
            pressure_curve=contract.pressure_curve,
            foreshadow_actions=contract.foreshadow_actions,
            ending_shift=contract.ending_shift,
            target_chinese_chars=contract.target_chinese_chars,
            forbidden=contract.forbidden,
            scene_plan=ScenePlan(
                scenes=(SceneContract(
                    id="scene-1", order=1, place_id="gobi-test-site", place_label="西北试验场",
                    place_class="field", interior_exterior="exterior", time_window="深夜",
                    participants=("林子轩", "齐雨"), viewpoint="林子轩", ordinary_people_present=True,
                    goal="确认停机原因", conflict="工期与安全冲突", action="进入厂房复核偏滤器",
                    information_change="确认旧图缺失", state_change="试运行暂停",
                    entry_reason="远程数据不足", exit_trigger="故障树建立完成",
                ),),
                chapter_spatial_intent="让技术冲突落到工程现场", required_world_slice="工程劳动者",
                allowed_same_place_run=2,
            ),
            technology_plan=TechnologyPlan(technologies=(TechnologyContract(
                id="fusion-divertor", name="耐高热偏滤器", role="supporting",
                birth_reason="旧部件无法承受持续热流", source="人类根据CMB理论工程化",
                prerequisites=("耐高热材料", "真空制造"), validation_stage="现场复核",
                first_application="聚变试验堆", social_diffusion=("工业热交换",),
                cost="延误点火并增加材料争夺", changed_domains=("protagonist_capability", "power_relations"),
            ),)),
        ),
        schema_version=2,
    )

    assert NarrativeDecision.from_json(planned.to_json()) == planned


def test_pov_plan_round_trips_supporting_character_agency():
    decision = _decision()
    agency = SupportingAgencyContract("韩宁", "查明偏滤器裂纹", "工期封锁", "坚持停机", "承担延期责任", "首堆停机", "暴露旧图缺陷")
    scene = SceneContract("s1", 1, "plant", "十九号厂房", "field", "interior", "深夜", ("韩宁", "工人"), "韩宁", True, "查明裂纹", "工期压力", "拉下停机闸", "旧图缺陷", "首堆停机", "联调异常", "进入复盘")
    planned = replace(decision, schema_version=2, chapter_contract=replace(
        decision.chapter_contract,
        scene_plan=ScenePlan((scene,), "工程现场", "现场工人"),
        pov_plan=PointOfViewPlan("韩宁", "limited", False, (agency,), "工程现场配角POV"),
    ))

    assert NarrativeDecision.from_json(planned.to_json()) == planned
