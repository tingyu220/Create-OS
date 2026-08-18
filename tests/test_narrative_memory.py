from creative_os.domains.narrative_decision import (
    ArcPhase,
    ChapterContract,
    InformationPlan,
    NarrativeChangeRequest,
    NarrativeDecision,
    NarrativeProjectProfile,
    PressureCurve,
    ProtagonistChoice,
    ReaderChange,
    StoryArc,
    StoryContract,
    StoryVolume,
    WrittenTextStrategy,
)
from creative_os.domains.narrative_memory import (
    load_active_narrative_decision,
    load_active_narrative_profile,
    save_change_request_candidate,
    save_narrative_candidate,
    save_project_profile_candidate,
)
from creative_os.memory.approval import approve_candidate
from creative_os.memory.model import MemoryEvidence, MemoryStatus
from creative_os.memory.store import JsonMemoryStore


def _decision(chapter: int = 7) -> NarrativeDecision:
    return NarrativeDecision(
        chapter=chapter,
        profile_id="civilization-profile",
        volume_id="volume-1",
        arc_id="arc-identity",
        arc_phase=ArcPhase.ESCALATION,
        arc_goal="确认第九区日志被覆盖的原因",
        inherited_pressure="林子轩发现自己可能被当作投递工具",
        future_pressures=("权限审查即将启动",),
        chapter_contract=ChapterContract(
            functions=("推进主线",),
            dramatic_question="林子轩是否主动调查第九区日志？",
            protagonist_choice=ProtagonistChoice(
                actor="林子轩",
                action="要求查看日志",
                alternatives=("等待父亲安排",),
                cost="父子关系进一步紧张",
                consequence="进入权限审查名单",
            ),
            reader_change=ReaderChange(before="读者怀疑内部泄露", after="读者确认主角也在投递链路中"),
            information=InformationPlan(reveal=("日志被覆盖",), withhold=("覆盖者身份",), misdirect=()),
            pressure_curve=PressureCurve(start="封控", turn="违令", end="审查启动"),
            foreshadow_actions=("加深周远线索",),
            ending_shift="主角成为被审查对象",
            target_chinese_chars=7000,
            forbidden=("不得确认发送者",),
        ),
    )


def _profile() -> NarrativeProjectProfile:
    return NarrativeProjectProfile(
        id="civilization-profile",
        story_contract=StoryContract(
            core_question="林子轩能否成为主动选择的人，而非被设计的钥匙？",
            reader_promise=("每次解码都要付出代价",),
            theme_conflict="命运设计与自主选择",
            invariants=("解码会伤害林子轩",),
        ),
        volumes=(StoryVolume("volume-1", "接受代价", "林子轩失去普通生活"),),
        arcs=(StoryArc("arc-identity", "volume-1", "确认神经介入的代价", ArcPhase.ESCALATION),),
    )


def test_narrative_candidate_requires_human_approval_before_loading(tmp_path):
    project = tmp_path / "文明升阶"
    item = save_narrative_candidate(
        project,
        _decision(),
        evidence=[MemoryEvidence(source_type="chapter", source_id="production/final_chapters/chapter_006.md")],
    )

    assert item.status == MemoryStatus.CANDIDATE
    assert load_active_narrative_decision(project, 7) is None

    store = JsonMemoryStore(project / ".creative_os" / "memory")
    approve_candidate(store, item.id, actor="tingyu", note="批准第七章叙事合同")

    assert load_active_narrative_decision(project, 7) == _decision()


def test_active_narrative_decision_does_not_leak_to_other_project_or_chapter(tmp_path):
    source_project = tmp_path / "文明升阶"
    other_project = tmp_path / "另一部小说"
    item = save_narrative_candidate(
        source_project,
        _decision(7),
        evidence=[MemoryEvidence(source_type="director", source_id="proposal-7")],
    )
    store = JsonMemoryStore(source_project / ".creative_os" / "memory")
    approve_candidate(store, item.id, actor="tingyu", note="批准")

    assert load_active_narrative_decision(source_project, 8) is None
    assert load_active_narrative_decision(other_project, 7) is None


def test_project_profile_requires_approval_before_loading(tmp_path):
    project = tmp_path / "文明升阶"
    item = save_project_profile_candidate(
        project,
        _profile(),
        evidence=[MemoryEvidence(source_type="brief", source_id="project.json")],
    )

    assert load_active_narrative_profile(project) is None

    approve_candidate(JsonMemoryStore(project / ".creative_os" / "memory"), item.id, actor="tingyu", note="批准项目承诺")

    assert load_active_narrative_profile(project) == _profile()


def test_change_request_is_saved_as_auditable_candidate(tmp_path):
    project = tmp_path / "文明升阶"
    request = NarrativeChangeRequest(
        id="move-reveal",
        reason="第十章揭露会削弱前期悬念",
        old_plan="第十章确认发送者身份",
        new_plan="第十章只确认内部权限被篡改",
        affected_chapters=(7, 8, 9, 10),
        affected_state_subjects=("林子轩", "第九区服务器"),
        affected_hooks=("第九区发送者",),
        written_text_strategy=WrittenTextStrategy.LOCAL_REVISION,
    )

    item = save_change_request_candidate(
        project,
        request,
        evidence=[MemoryEvidence(source_type="review", source_id="chapter-006-review")],
    )

    assert item.status == MemoryStatus.CANDIDATE
    assert item.content == request.to_json()
    assert item.evidence[0].source_id == "chapter-006-review"
