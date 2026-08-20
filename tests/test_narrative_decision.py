import json
from dataclasses import replace

import pytest

from creative_os.domains.narrative_decision import (
    ArcPhase,
    ChapterContract,
    ChoiceStatus,
    FieldEvidenceBinding,
    InformationPlan,
    NarrativeChangeRequest,
    NarrativeDecision,
    NarrativeProjectProfile,
    NarrativeValidationError,
    NullablePlan,
    OptionalCandidateResolution,
    PressureCurve,
    ProtagonistChoice,
    ReaderChange,
    StoryContract,
    StoryArc,
    StoryVolume,
    WrittenTextStrategy,
)
from creative_os.domains.narrative_evidence import EvidenceLocator, EvidenceRef, EvidenceRole


CONTRACT_ID = "narrative-chapter-007"
CONTRACT_VERSION = 2


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


def _evidence(field_path: str, role: EvidenceRole = EvidenceRole.INTENT) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=f"ev-{field_path}",
        contract_id=CONTRACT_ID,
        contract_version=CONTRACT_VERSION,
        field_path=field_path,
        role=role,
        source_id="outline/chapter-007",
        source_version="3",
        source_content_hash="a" * 64,
        locator=EvidenceLocator(kind="json_pointer", value="/chapter_contract"),
        excerpt="第七章推进主动调查。",
        assertion=f"该来源约束 {field_path}",
    )


def _v2_decision(*, evidence_role: EvidenceRole = EvidenceRole.INTENT) -> NarrativeDecision:
    field_path = "chapter_contract.functions[0]"
    return NarrativeDecision(
        contract_id=CONTRACT_ID,
        contract_version=CONTRACT_VERSION,
        chapter=7,
        profile_id="civilization-profile",
        volume_id="volume-1",
        arc_id="arc-identity",
        arc_phase=ArcPhase.ESCALATION,
        arc_goal="将短信疑点转化为主角的主动调查",
        inherited_pressure="林子轩知道自己可能被当作投递工具",
        future_pressures=("第九区权限将被收紧",),
        chapter_contract=ChapterContract(
            chapter_id="chapter_007",
            functions=("推进主线", "改变人物关系"),
            dramatic_question="林子轩是否愿意违背父亲的安排追查短信？",
            protagonist_choice=ProtagonistChoice(
                status=ChoiceStatus.COMPLETE,
                actor="林子轩",
                action="主动要求查看第九区日志",
                alternatives=("留在安全宿舍等待",),
                cost="与林正弘的信任进一步受损",
                consequence="被纳入权限审查名单",
                missing_fields=(),
            ),
            reader_change=ReaderChange(
                before="读者怀疑短信来自内部泄露",
                after="读者确认林子轩本人也可能是投递链路的一部分",
            ),
            information=InformationPlan(
                reveal=("第九区日志存在人为覆盖痕迹",),
                withhold=("覆盖者身份",),
                misdirect=NullablePlan(values=("表面嫌疑指向周远",)),
            ),
            pressure_curve=PressureCurve(start="封控后的窒息", turn="主动违令", end="权限审查启动"),
            foreshadow_actions=NullablePlan(values=("加深周远留下钥匙算法的异常性",)),
            ending_shift="林子轩从被保护者变为被审查对象",
            target_chinese_chars=7000,
            forbidden=NullablePlan(values=("不得确认短信发送者身份",)),
            optional_candidates=(
                OptionalCandidateResolution(
                    candidate_id="candidate-scene-transition",
                    kind="scene_transition",
                    value_state="known",
                    proposed_value="从日志室转入权限听证",
                    dependency_inputs=("chapter_contract.pressure_curve.end",),
                    affects_current_chapter="yes",
                    rationale="结尾必须落到本章后果。",
                    decided_by="rule",
                    decision_ref="causal-rules-v1",
                ),
            ),
            intent_evidence_bindings=(
                FieldEvidenceBinding(field_path=field_path, evidence=(_evidence(field_path, evidence_role),)),
            ),
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


@pytest.mark.parametrize(
    "choice",
    [
        ProtagonistChoice(
            status=ChoiceStatus.COMPLETE,
            actor="林子轩",
            action="调查日志",
            alternatives=("等待",),
            cost="关系受损",
            consequence="进入审查",
            missing_fields=(),
        ),
        ProtagonistChoice(
            status=ChoiceStatus.PARTIAL,
            actor="林子轩",
            action=None,
            alternatives=(),
            cost="关系受损",
            consequence=None,
            missing_fields=("action", "alternatives", "consequence"),
        ),
        ProtagonistChoice(
            status=ChoiceStatus.UNKNOWN,
            actor=None,
            action=None,
            alternatives=(),
            cost=None,
            consequence=None,
            missing_fields=("actor", "action", "alternatives", "cost", "consequence"),
        ),
    ],
)
def test_choice_three_states_accept_only_state_consistent_values(choice):
    choice.validate()


@pytest.mark.parametrize(
    "choice",
    [
        ProtagonistChoice(
            actor="林子轩",
            action="调查",
            alternatives=(),
            cost="代价",
            consequence="后果",
            status=ChoiceStatus.COMPLETE,
            missing_fields=(),
        ),
        ProtagonistChoice(
            actor="林子轩",
            action=None,
            alternatives=(),
            cost="代价",
            consequence=None,
            status=ChoiceStatus.PARTIAL,
            missing_fields=("action",),
        ),
        ProtagonistChoice(
            actor="臆测角色",
            action=None,
            alternatives=(),
            cost=None,
            consequence=None,
            status=ChoiceStatus.UNKNOWN,
            missing_fields=("actor", "action", "alternatives", "cost", "consequence"),
        ),
    ],
)
def test_choice_rejects_incomplete_missing_field_lists_or_unknown_guesses(choice):
    with pytest.raises(NarrativeValidationError):
        choice.validate()


def test_nullable_plan_keeps_values_and_not_applicable_reason_mutually_exclusive():
    NullablePlan(values=("伏笔动作",)).validate()
    NullablePlan(values=(), not_applicable_reason="本章没有需要处理的既有伏笔").validate()
    NullablePlan(values=()).validate()  # candidate unresolved; preflight will block it

    with pytest.raises(NarrativeValidationError):
        NullablePlan(values=("伏笔动作",), not_applicable_reason="不适用").validate()
    with pytest.raises(NarrativeValidationError):
        NullablePlan(values=(), not_applicable_reason=" ").validate()


def test_v2_decision_requires_coherent_contract_chapter_identity_and_positive_version():
    decision = _v2_decision()
    decision.validate()

    for invalid in (
        replace(decision, contract_id="narrative-chapter-008"),
        replace(decision, contract_version=0),
        replace(decision, chapter_contract=replace(decision.chapter_contract, chapter_id="chapter_008")),
    ):
        with pytest.raises(NarrativeValidationError):
            invalid.validate()


@pytest.mark.parametrize("role", [EvidenceRole.INTENT, EvidenceRole.NON_APPLICABILITY])
def test_frozen_contract_accepts_only_prewrite_evidence_roles(role):
    _v2_decision(evidence_role=role).validate()


@pytest.mark.parametrize(
    "role",
    [EvidenceRole.VERIFICATION, EvidenceRole.REALIZATION, EvidenceRole.DECISION],
)
def test_frozen_contract_rejects_postwrite_or_decision_evidence(role):
    with pytest.raises(NarrativeValidationError, match="intent or non_applicability"):
        _v2_decision(evidence_role=role).validate()


def test_v2_uses_only_reader_change_and_pressure_curve_field_names():
    content = _v2_decision().to_json()
    payload = json.loads(content)

    assert payload["chapter_contract"]["reader_change"] == {
        "after": "读者确认林子轩本人也可能是投递链路的一部分",
        "before": "读者怀疑短信来自内部泄露",
    }
    assert payload["chapter_contract"]["pressure_curve"] == {
        "end": "权限审查启动",
        "start": "封控后的窒息",
        "turn": "主动违令",
    }
    assert "reader_before" not in content
    assert "pressure_start" not in content
