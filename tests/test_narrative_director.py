import pytest
from dataclasses import replace

from creative_os.domains.narrative_decision import (
    ArcPhase,
    ChapterContract,
    InformationPlan,
    NarrativeDecision,
    NarrativeProjectProfile,
    PressureCurve,
    ProtagonistChoice,
    ReaderChange,
    SceneContract,
    ScenePlan,
    StoryArc,
    StoryContract,
    StoryVolume,
    TechnologyContract,
    TechnologyPlan,
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
        chapter=chapter,
        profile_id="civilization-profile",
        volume_id="volume-1",
        arc_id="arc-identity",
        arc_phase=ArcPhase.ESCALATION,
        arc_goal="剧情段目标",
        inherited_pressure="上一章的压力",
        future_pressures=("下一章压力",),
        chapter_contract=ChapterContract(
            functions=("推进主线",),
            dramatic_question="主角是否主动调查？",
            protagonist_choice=ProtagonistChoice("林子轩", "调查日志", ("等待",), "关系受损", "进入审查"),
            reader_change=ReaderChange("读者怀疑", "读者确认风险"),
            information=InformationPlan(("日志被覆盖",), ("覆盖者身份",), ()),
            pressure_curve=PressureCurve("封控", "违令", "审查"),
            foreshadow_actions=("加深钥匙线索",),
            ending_shift="主角成为审查对象",
            target_chinese_chars=7000,
            forbidden=("不得确认发送者",),
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
    assert decision.chapter_contract.target_chinese_chars == 7000
    assert not hasattr(decision, "manuscript")


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


def test_director_blocks_v2_scene_without_change_and_incomplete_technology_chain():
    decision = _decision()
    contract = decision.chapter_contract
    proposal = replace(
        decision,
        schema_version=2,
        chapter_contract=replace(
            contract,
            scene_plan=ScenePlan(scenes=(SceneContract(
                "scene-1", 1, "base-room", "基地房间", "base", "interior", "夜晚",
                ("林子轩",), "林子轩", False, "查看屏幕", "没有冲突", "查看数据", "", "", "继续工作", "看完",
            ),), chapter_spatial_intent="推进", required_world_slice="外部世界", allowed_same_place_run=2),
            technology_plan=TechnologyPlan(technologies=(TechnologyContract(
                "fusion", "聚变", "core", "应对能源危机", "CMB", (), "直接完成", "聚变堆", (), "无", (),
            ),)),
        ),
    )

    with pytest.raises(NarrativeDirectorBlockedError, match="scene|technology"):
        NarrativeDirector().propose(_input(), proposal)


def _v2_decision(chapter=7, *, place_id="base-room", ordinary=True, allowed=2, exception=""):
    decision = _decision(chapter)
    return replace(
        decision,
        schema_version=2,
        chapter_contract=replace(
            decision.chapter_contract,
            scene_plan=ScenePlan(scenes=(SceneContract(
                "scene-1", 1, place_id, "基地房间", "base", "interior", "夜晚",
                ("林子轩", "工人"), "林子轩", ordinary, "查故障", "工期冲突", "现场停机",
                "确认旧图缺失", "试验暂停", "远程数据不足", "完成复盘",
            ),), chapter_spatial_intent="现场行动", required_world_slice="普通劳动者",
                allowed_same_place_run=allowed, exception_reason=exception),
            pov_plan=PointOfViewPlan(
                "工人", "limited", False,
                (SupportingAgencyContract("工人", "查故障", "工期冲突", "现场停机", "承担延期", "试验暂停", "旧图进入复盘"),),
                "配角主导工程现场",
            ),
        ),
    )


def test_director_blocks_required_world_slice_without_ordinary_people_scene():
    with pytest.raises(NarrativeDirectorBlockedError, match="ordinary-people"):
        NarrativeDirector().propose(_input(), _v2_decision(ordinary=False))


def test_director_blocks_excessive_same_place_run_without_exception():
    previous = replace(_v2_decision(chapter=6, allowed=1), chapter=6)
    with pytest.raises(NarrativeDirectorBlockedError, match="same place run"):
        NarrativeDirector().propose(_input(active_decisions=(previous,)), _v2_decision(allowed=1))

    accepted = NarrativeDirector().propose(
        _input(active_decisions=(previous,)), _v2_decision(allowed=1, exception="连续封锁审讯"),
    )
    assert accepted.chapter_contract.scene_plan.exception_reason == "连续封锁审讯"


def test_director_keeps_v1_read_compatibility_but_rejects_it_for_new_production():
    restored = NarrativeDecision.from_json(_decision().to_json())
    assert restored.schema_version == 1

    with pytest.raises(NarrativeDirectorBlockedError, match="schema v2"):
        NarrativeDirector().propose(_input(), restored)


def test_director_requires_pov_and_supporting_agency_for_new_v2_production():
    missing = replace(_v2_decision(), chapter_contract=replace(
        _v2_decision().chapter_contract, pov_plan=PointOfViewPlan(),
    ))
    with pytest.raises(NarrativeDirectorBlockedError, match="POV|agency"):
        NarrativeDirector().propose(_input(), missing)

    agency = SupportingAgencyContract("工人", "阻止带病联调", "工期压力", "拉下停机闸", "承担处分", "联调停止", "主线进入故障复盘")
    proposal = replace(_v2_decision(), chapter_contract=replace(
        _v2_decision().chapter_contract,
        pov_plan=PointOfViewPlan("工人", "limited", False, (agency,), "配角主导工程决策"),
    ))
    assert NarrativeDirector().propose(_input(), proposal) == proposal


def test_director_rejects_pov_candidate_not_used_by_scene():
    from tests.pov_strategy_helpers import option

    with pytest.raises(NarrativeDirectorBlockedError, match="POV candidate"):
        NarrativeDirector().propose(_input(), _v2_decision(), pov_candidate=option("不在场人物"))


def test_director_accepts_only_candidate_aligned_with_scene_and_agency():
    from tests.pov_strategy_helpers import option
    candidate = option("工人", False, function="推进主线")
    candidate = replace(
        candidate,
        agency=replace(candidate.agency, choice_boundary="现场停机"),
        mainline_change=replace(candidate.mainline_change, target_state_ref="旧图进入复盘"),
    )
    proposal = _v2_decision()
    scene = replace(proposal.chapter_contract.scene_plan.scenes[0], viewpoint="工人")
    proposal = replace(proposal, chapter_contract=replace(
        proposal.chapter_contract,
        scene_plan=replace(proposal.chapter_contract.scene_plan, scenes=(scene,)),
    ))
    assert NarrativeDirector().propose(_input(), proposal, pov_candidate=candidate) == proposal

    bad = replace(candidate, agency=replace(candidate.agency, choice_boundary="绕过停机"))
    with pytest.raises(NarrativeDirectorBlockedError, match="agency"):
        NarrativeDirector().propose(_input(), proposal, pov_candidate=bad)


def test_enabled_project_cannot_bypass_selected_pov_strategy(tmp_path):
    runtime = tmp_path / ".creative_os"
    runtime.mkdir()
    (runtime / "pov_strategy_policy.json").write_text('{"version":"v1"}', encoding="utf-8")
    with pytest.raises(NarrativeDirectorBlockedError, match="selected POV strategy"):
        NarrativeDirector().propose(_input(project_root=tmp_path), _v2_decision())
