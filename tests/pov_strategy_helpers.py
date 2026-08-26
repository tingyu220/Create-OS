from creative_os.domains.pov_strategy_model import (
    ArcState, ChapterNeeds, CharacterPressure, EvidenceRef, MainlineCapability,
    MainlineChangeProposal, POVOption, POVStrategyCandidateSet, POVStrategyInput,
    ProtagonistLoad, RhythmOutlook, StateRef, StorylineState, SupportingAgencyBoundary,
    TransitionReason,
)
from creative_os.domains.narrative_evidence import EvidenceLocator

HASH = "a" * 64


def evidence(source="chapter-001"):
    return EvidenceRef(
        source_id=source,
        source_version="1",
        source_content_hash=HASH,
        locator=EvidenceLocator("text_anchor", "line:1"),
        assertion="测试证据",
    )


def state_ref(key="goal", value="推进目标"):
    return StateRef(key, value, (evidence(),))


def option(owner="lin-zixuan", protagonist=True, capability="integrate", function="整合后果"):
    ref = state_ref()
    return POVOption(
        id=f"option-{owner}", primary_owner=owner, protagonist_present=protagonist,
        rationale="能够承接当前后果", function_fits=(function,), benefits=("推进主线",), tradeoffs=(), cannot_serve=(),
        mainline_change=MainlineChangeProposal("mainline", "choose", capability, (evidence(),)),
        agency=SupportingAgencyBoundary(owner, ref, ref, "必须作出选择", ref),
        transition=TransitionReason("previous", "承接Arc后果", (evidence(),)), evidence_refs=(evidence(),),
    )


def strategy_input(target=27, needs_function="整合后果", pressures=None, history=()):
    pressures = pressures if pressures is not None else (
        CharacterPressure("lin-zixuan", (state_ref(),), (state_ref("choice"),), (state_ref("cost"),),
                          (MainlineCapability("integrate", (needs_function,), "mainline", (evidence(),)),)),
    )
    value = POVStrategyInput(
        "project", target, "2026-08-25T00:00:00Z", "v1", tuple(history),
        ProtagonistLoad(3, 0, False, ()), tuple(pressures),
        ArcState("arc", "setup", "如何整合文明升级后果", "三线后果待承接", (evidence(),)),
        (StorylineState("engineering", "active", (state_ref(),), (evidence(),)),), (),
        ChapterNeeds((needs_function,), "谁来整合后果", (), "", ()), (evidence(),), "",
    )
    return value.with_fingerprint()


def candidate_set():
    input_value = strategy_input()
    return POVStrategyCandidateSet(
        "pov-strategy-027", 27, input_value.baseline_fingerprint, "v1", input_value.assembled_at,
        ("source_or_policy_changed", "target_chapter_changed", "contract_activated"),
        option(), (), RhythmOutlook(3, ("承接工程后果",), ("integrate",), ("每章重算",)), (),
    )
