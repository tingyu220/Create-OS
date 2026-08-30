import pytest
from dataclasses import replace

from creative_os.domains.narrative_decision import (
    ArcPhase,
    ChapterContract,
    InformationPlan,
    NarrativeDecision,
    NarrativeProjectProfile,
    NullablePlan,
    PressureCurve,
    ProtagonistChoice,
    ReaderChange,
    SceneContract,
    ScenePlan,
    StoryArc,
    StoryContract,
    StoryVolume,
    PointOfViewPlan,
    SupportingAgencyContract,
)
from creative_os.domains.narrative_director import DirectorInput, NarrativeDirector, NarrativeDirectorBlockedError


def _profile() -> NarrativeProjectProfile:
    return NarrativeProjectProfile(
        id="civilization-profile",
        story_contract=StoryContract("核心问题", ("读者承诺",), "主题冲突", ("事实边界",)),
        volumes=(StoryVolume("volume-1", "分卷目标", "不可逆变化"),),
        arcs=(StoryArc("arc-identity", "volume-1", "剧情段目标", ArcPhase.ESCALATION),),
    )


def _decision(chapter: int = 7) -> NarrativeDecision:
    return NarrativeDecision(
        contract_id=f"narrative-chapter-{chapter:03d}",
        contract_version=1,
        chapter=chapter,
        profile_id="civilization-profile",
        volume_id="volume-1",
        arc_id="arc-identity",
        arc_phase=ArcPhase.ESCALATION,
        arc_goal="剧情段目标",
        inherited_pressure="上一章的压力",
        future_pressures=("下一章压力",),
        chapter_contract=ChapterContract(
            chapter_id=f"chapter_{chapter:03d}",
            functions=("推进主线",),
            dramatic_question="主角是否主动调查？",
            protagonist_choice=ProtagonistChoice("林子轩", "调查日志", ("等待",), "关系受损", "进入审查"),
            reader_change=ReaderChange("读者怀疑", "读者确认风险"),
            information=InformationPlan(("日志被覆盖",), ("覆盖者身份",), NullablePlan(values=())),
            pressure_curve=PressureCurve("封控", "违令", "审查"),
            foreshadow_actions=NullablePlan(values=("加深钥匙线索",)),
            ending_shift="主角成为审查对象",
            target_chinese_chars=7000,
            forbidden=NullablePlan(values=("不得确认发送者",)),
        ),
    )


def _v2_decision(chapter=7, *, place_id="base-room", ordinary=True, allowed=2, exception=""):
    decision = _decision(chapter)
    return replace(
        decision,
        schema_version=2,
        chapter_contract=replace(
            decision.chapter_contract,
            scene_plan=ScenePlan(
                scenes=(SceneContract(
                    "scene-1", 1, place_id, "基地房间", "base", "interior", "夜晚",
                    ("林子轩", "工人"), "林子轩", ordinary, "查故障", "工期冲突", "现场停机",
                    "确认旧图缺失", "试验暂停", "远程数据不足", "完成复盘",
                ),),
                chapter_spatial_intent="现场行动",
                required_world_slice="普通劳动者",
                allowed_same_place_run=allowed,
                exception_reason=exception,
            ),
            pov_plan=PointOfViewPlan(
                "工人", "limited", False,
                (SupportingAgencyContract("工人", "查故障", "工期冲突", "现场停机", "承担延期", "试验暂停", "旧图进入复盘"),),
                "配角主导工程现场",
            ),
        ),
    )


def _input(**overrides) -> DirectorInput:
    values = {
        "project_root": "projects/文明升阶",
        "chapter_number": 7,
        "profile": _profile(),
        "fact_snapshots": ({"kind": "character", "subject": "林子轩", "fields": {"current_goal": "查短信"}},),
        "previous_ending": "林子轩收到第三条短信。",
        "active_decisions": (),
        "target_chinese_chars": 7000,
    }
    values.update(overrides)
    return DirectorInput(**values)


def test_director_accepts_a_contract_aligned_with_profile_and_facts():
    decision = NarrativeDirector().propose(_input(), _v2_decision())

    assert decision == _v2_decision()
    assert decision.contract_id == "narrative-chapter-007"
    assert decision.chapter_contract.chapter_id == "chapter_007"
    assert decision.chapter_contract.target_chinese_chars == 7000
    assert not hasattr(decision, "manuscript")
    assert not hasattr(decision, "approval")
    assert not hasattr(decision, "preflight_result")


@pytest.mark.parametrize(
    ("input_overrides", "proposal", "reason"),
    [
        ({"chapter_number": 8}, _decision(7), "chapter"),
        ({"fact_snapshots": ()}, _decision(), "fact"),
        ({"previous_ending": ""}, _decision(), "ending"),
        ({"active_decisions": (_decision(),)}, _decision(), "already"),
    ],
)
def test_director_blocks_unusable_or_overwriting_proposal(input_overrides, proposal, reason):
    with pytest.raises(NarrativeDirectorBlockedError, match=reason):
        NarrativeDirector().propose(_input(**input_overrides), proposal)


@pytest.mark.parametrize(
    "proposal",
    [
        replace(_decision(), volume_id="unknown-volume"),
        replace(_decision(), arc_id="unknown-arc"),
        replace(_decision(), arc_phase=ArcPhase.TURN),
        replace(_decision(), arc_goal="伪造的剧情段目标"),
    ],
)
def test_director_blocks_contracts_that_do_not_match_profile_scale(proposal):
    with pytest.raises(NarrativeDirectorBlockedError, match="profile"):
        NarrativeDirector().propose(_input(), proposal)
