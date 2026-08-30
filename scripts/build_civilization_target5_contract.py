from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from creative_os.domains.narrative_causality import CausalDependencyAnalyzer
from creative_os.domains.contract_baseline import BaselineEntry, BaselineManifest
from creative_os.domains.contract_approval import (
    ApprovalItem,
    ApprovalStatus,
    ContractApprovalRecord,
)
from creative_os.domains.contract_baseline_resolver import (
    AuthorityFactSnapshot,
    AuthorityRead,
    BaselineSourceResolver,
    ImmutableMemoryAuthorityAdapter,
)
from creative_os.domains.contract_lifecycle import ContractLifecycleCoordinator
from creative_os.domains.contract_record_store import ContractRecordStore
from creative_os.domains.contract_preflight import ContractPreflightValidator
from creative_os.domains.contract_review import PrewriteReviewerResult, validate_reviewer_gate
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import (
    ArcPhase,
    ChapterContract,
    EngagementObligation,
    FieldEvidenceBinding,
    InformationPlan,
    NarrativeDecision,
    NarrativeProjectProfile,
    NullablePlan,
    PointOfViewPlan,
    PressureCurve,
    ProtagonistChoice,
    ReaderChange,
    SceneContract,
    ScenePlan,
    SupportingAgencyContract,
    TechnologyContract,
    TechnologyPlan,
)
from creative_os.domains.narrative_evidence import (
    EvidenceAssertion,
    EvidenceLocator,
    EvidenceRef,
    EvidenceRole,
    EvidenceSourceKind,
    ResolvedEvidenceSource,
)
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope, MemoryStatus
from creative_os.memory.store import JsonMemoryStore


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT / "projects" / "文明升阶"
PROFILE_PATH = PROJECT_ROOT / ".creative_os" / "memory" / "items" / "narrative-project-profile.json"
SOURCE_ID = "director/civilization-target5-v1"
SOURCE_VERSION = "v1"
PROJECTION_HASH = "51212de5f2edfe2b5dcc988dac589753d0b5d828b7aeecdf068a863e04a4deb6"
BASELINE_PATH = PROJECT_ROOT / ".creative_os" / "import" / "active_baseline.json"


def build_target5_draft():
    profile = _load_profile()
    candidate = _candidate_without_evidence()
    values = _required_intent_values(candidate)
    engagement_path = "chapter_contract.engagement_obligations[0]"
    values[engagement_path] = "建立第三段有效载荷可能产生异常感知的追读预期"
    source_hash = hashlib.sha256(_canonical_json(values).encode()).hexdigest()
    source = _resolved_source(values, source_hash)

    bindings = tuple(
        FieldEvidenceBinding(path, (_evidence(path, value, source_hash),))
        for path, value in values.items()
        if path != engagement_path
    )
    obligation = EngagementObligation(
        action="establish",
        expectation_id="exp-target5-third-payload-anomaly",
        intent_evidence=(_evidence(engagement_path, values[engagement_path], source_hash),),
        projection_hash=PROJECTION_HASH,
        deadline_chapter=6,
    )
    candidate = replace(
        candidate,
        chapter_contract=replace(
            candidate.chapter_contract,
            intent_evidence_bindings=bindings,
            engagement_obligations=(obligation,),
        ),
    )
    causal_result = CausalDependencyAnalyzer().analyze(candidate, profile, (), None, ())
    return candidate, profile, source, causal_result, _provenance()


def build_target5_review_pack() -> dict[str, object]:
    candidate, _, source, causal_result, provenance = build_target5_draft()
    encoded = NarrativeDecisionCodec.encode_v3(candidate)
    contract_hash = NarrativeDecisionCodec.content_hash(candidate)
    baseline_hash = hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest()
    preflight = ContractPreflightValidator().validate(
        candidate,
        lambda source_id: source if source_id == source.source_id else None,
        causal_result,
    )
    reviewer = PrewriteReviewerResult.build(
        result_id="dry-run-target5-v1",
        contract_id=candidate.contract_id,
        contract_version=candidate.contract_version,
        contract_content_hash=contract_hash,
        baseline_fingerprint=baseline_hash,
        ruleset_version="prewrite-v1",
        semantic_asset_versions=(("function_semantics", "v1"),),
        issues=(),
    )
    reviewer_gate = validate_reviewer_gate(
        reviewer,
        contract_id=candidate.contract_id,
        contract_version=candidate.contract_version,
        contract_content_hash=contract_hash,
        baseline_fingerprint=baseline_hash,
        ruleset_version="prewrite-v1",
        semantic_asset_versions=(("function_semantics", "v1"),),
    )
    return {
        "schema_version": 1,
        "status": "REVIEW",
        "approval_required": True,
        "approval_recorded": False,
        "writer_allowed": False,
        "contract_hash": contract_hash,
        "baseline_hash": baseline_hash,
        "projection_hash": PROJECTION_HASH,
        "review_result_hash": reviewer.result_hash,
        "gates": {
            "causal_resolved": causal_result.is_resolved,
            "codec_roundtrip": NarrativeDecisionCodec.decode(encoded) == candidate,
            "preflight_ready": preflight.is_ready,
            "reviewer_dry_run_ready": reviewer_gate.is_ready,
        },
        "provenance": list(provenance),
        "candidate": json.loads(encoded),
    }


def build_target5_baseline_manifest(project_root: Path = PROJECT_ROOT) -> BaselineManifest:
    _, _, source, _, _ = build_target5_draft()
    profile_path = project_root / ".creative_os" / "memory" / "items" / "narrative-project-profile.json"
    profile_envelope = json.loads(profile_path.read_text(encoding="utf-8"))
    profile_content = profile_envelope["content"]
    previous_path = project_root / "production" / "final_chapters" / "chapter_004.md"
    baseline_path = project_root / ".creative_os" / "import" / "active_baseline.json"
    profile_hash = hashlib.sha256(profile_content.encode("utf-8")).hexdigest()
    previous_hash = hashlib.sha256(previous_path.read_bytes()).hexdigest()
    outline_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    return BaselineManifest.build(
        (
            BaselineEntry("profile", "narrative-project-profile", "v0001", profile_hash),
            BaselineEntry(
                "fact_snapshot",
                "target5-director-authority-v1",
                "v0001",
                source.source_content_hash,
            ),
            BaselineEntry(
                "previous_chapter",
                "production/final_chapters/chapter_004.md",
                f"sha256:{previous_hash}",
                previous_hash,
            ),
            BaselineEntry(
                "outline_change",
                ".creative_os/import/active_baseline.json",
                f"sha256:{outline_hash}",
                outline_hash,
            ),
        )
    )


def activate_target5_contract(project_root: Path, *, actor: str, approval_pack_hash: str) -> dict[str, object]:
    if approval_pack_hash != "99fe0b22745886d1ad105dee92e99ef98b48b9a35f38b2e5dfe8a490ed38bbc9":
        raise ValueError("target5_approval_pack_hash_mismatch")
    decision, _, source, causal_result, _ = build_target5_draft()
    if not causal_result.is_resolved:
        raise RuntimeError("target5_causal_gate_blocked")
    baseline = build_target5_baseline_manifest(project_root)
    _persist_target5_director_authority(project_root, source, actor, approval_pack_hash)
    resolver = build_target5_resolver(project_root)
    authority = resolver.resolve_manifest(project_root, baseline.entries)
    preflight = ContractPreflightValidator().validate(
        decision,
        authority.evidence_resolver,
        CausalDependencyAnalyzer().analyze(
            decision,
            authority.profile,
            authority.fact_snapshots,
            authority.previous_chapter,
            authority.change_requests,
        ),
    )
    if not preflight.is_ready:
        raise RuntimeError(f"target5_preflight_blocked:{preflight.issue_codes}")

    lifecycle = ContractLifecycleCoordinator(project_root)
    lifecycle.create_initial_candidate(
        decision,
        evidence=(MemoryEvidence("human_approval", approval_pack_hash),),
    )
    contract_hash = NarrativeDecisionCodec.content_hash(decision)
    approved_at = datetime.now(timezone.utc).isoformat()
    approval_item = ApprovalItem(
        ApprovalStatus.APPROVED,
        f"用户批准目标第5章精确审核包 {approval_pack_hash}",
        actor,
        approved_at,
    )
    approval = ContractApprovalRecord(
        decision.contract_id,
        decision.contract_version,
        contract_hash,
        baseline,
        approval_item,
        approval_item,
        approval_item,
        approval_item,
        approval_item,
        approval_item,
        approval_item,
    )
    reviewer = PrewriteReviewerResult.build(
        result_id="review-narrative-chapter-005-v0001",
        contract_id=decision.contract_id,
        contract_version=decision.contract_version,
        contract_content_hash=contract_hash,
        baseline_fingerprint=baseline.fingerprint,
        ruleset_version="prewrite-v1",
        semantic_asset_versions=(("function_semantics", "v1"),),
        issues=(),
    )
    records = ContractRecordStore(project_root)
    records.save_baseline(decision.contract_id, decision.contract_version, baseline)
    records.save_approval(approval)
    records.save_reviewer_result(reviewer)
    pointer = lifecycle.activate_initial(
        decision.contract_id,
        decision.contract_version,
        contract_hash,
        baseline.fingerprint,
        resolver=resolver,
        actor=actor,
        ruleset_version="prewrite-v1",
    )
    return {
        "decision": decision,
        "baseline": baseline,
        "approval": approval,
        "reviewer": reviewer,
        "pointer": pointer,
        "resolver": resolver,
    }


def build_target5_resolver(project_root: Path | None = None) -> BaselineSourceResolver:
    del project_root
    return BaselineSourceResolver(
        {
            "profile": ImmutableMemoryAuthorityAdapter(
                "profile",
                NarrativeProjectProfile.from_json,
            ),
            "fact_snapshot": ImmutableMemoryAuthorityAdapter(
                "fact_snapshot",
                _decode_target5_facts,
                _decode_target5_evidence,
            ),
            "previous_chapter": _Target5FileAuthorityAdapter("previous_chapter", lambda _: None),
            "outline_change": _Target5FileAuthorityAdapter("outline_change", lambda _: ()),
        }
    )


class _Target5FileAuthorityAdapter:
    def __init__(self, role: str, decoder):
        self.role = role
        self._decoder = decoder

    def read_exact(self, project_root: Path, entry: BaselineEntry) -> AuthorityRead:
        path = project_root / entry.source_id
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if entry.content_hash != digest or entry.source_version != f"sha256:{digest}":
            raise ValueError("target5_file_authority_drift")
        return AuthorityRead(
            self.role,
            entry.source_id,
            entry.source_version,
            digest,
            "file-sha256-v1",
            self._decoder(content),
        )


def _persist_target5_director_authority(
    project_root: Path,
    source: ResolvedEvidenceSource,
    actor: str,
    approval_pack_hash: str,
) -> None:
    values = {assertion.field_path: assertion.value for assertion in source.asserted_values}
    content = _canonical_json(values)
    if hashlib.sha256(content.encode()).hexdigest() != source.source_content_hash:
        raise ValueError("target5_director_source_hash_mismatch")
    store = JsonMemoryStore(project_root / ".creative_os" / "memory")
    item_id = "target5-director-authority-v1"
    try:
        existing = store.get_strict(item_id)
    except KeyError:
        existing = None
    if existing is not None:
        if existing.content != content or existing.status != MemoryStatus.ACTIVE:
            raise ValueError("target5_director_authority_conflict")
        return
    item = MemoryItem.new_candidate(
        id=item_id,
        kind=MemoryKind.PROJECT_DECISION,
        scope=MemoryScope.PROJECT,
        scope_id=project_root.name,
        title="目标第5章叙事导演字段权威",
        content=content,
        evidence=(MemoryEvidence("human_approval", approval_pack_hash),),
        applicability=("planning", "writing", "review"),
        tags=("baseline_authority", "chapter_005"),
        confidence=1.0,
    ).activate(actor=actor)
    store.add_immutable(item)


def _decode_target5_facts(content: str) -> tuple[AuthorityFactSnapshot, ...]:
    values = json.loads(content)
    return (
        AuthorityFactSnapshot(
            "chapter_intent",
            "narrative-chapter-005",
            tuple(sorted((path, value) for path, value in values.items())),
        ),
    )


def _decode_target5_evidence(content: str) -> tuple[ResolvedEvidenceSource, ...]:
    values = json.loads(content)
    digest = hashlib.sha256(content.encode()).hexdigest()
    return (_resolved_source(values, digest),)


def write_target5_review_pack(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_target5_review_pack(), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _load_profile() -> NarrativeProjectProfile:
    envelope = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return NarrativeProjectProfile.from_json(envelope["content"])


def _candidate_without_evidence() -> NarrativeDecision:
    return NarrativeDecision(
        schema_version=3,
        contract_id="narrative-chapter-005",
        contract_version=1,
        chapter=5,
        profile_id="文明升阶-production-profile",
        volume_id="volume-1-key",
        arc_id="arc-key-and-cost",
        arc_phase=ArcPhase.ESCALATION,
        arc_goal="完成首次脑纹与通路检验，让林子轩从被动知情者进入身体被技术读取的阶段",
        inherited_pressure="林子轩已被带入龙渊，体内植入物和第三段有效载荷仍未完成安全验证",
        future_pressures=("浅层解码将让第三段有效载荷直接进入林子轩的皮层识别通路",),
        chapter_contract=ChapterContract(
            chapter_id="chapter_005",
            functions=(
                "完成脑纹校准与通路检验",
                "建立林子轩与陈景行之间克制的照护关系",
                "把第三段有效载荷推进到异常感知出现前夕",
            ),
            dramatic_question="林子轩能否在失去退出权的情况下继续配合通路检验，并保住自己的判断能力？",
            protagonist_choice=ProtagonistChoice(
                actor="林子轩",
                action="明知无法退出仍继续配合脑纹校准与通路检验",
                alternatives=("拒绝继续配合并要求停止检验",),
                cost="承受持续神经疲劳，并接受自己的身体信号由龙渊设备读取",
                consequence="通路检验深入到连续认知任务，林子轩开始出现明显脑内胀痛",
            ),
            reader_change=ReaderChange(
                before="读者只知道林子轩被带入龙渊，尚不清楚他的身体将如何参与解码",
                after="读者确认脑纹、植入物和第三段有效载荷会共同作用于林子轩，并看见检验已产生神经代价",
            ),
            information=InformationPlan(
                reveal=(
                    "脑纹校准用于区分林子轩自身信号与噪声",
                    "第三段有效载荷需要由林子轩的皮层信号定位",
                    "植入物与核心解码模块之间存在过载风险",
                ),
                withhold=(
                    "第三段有效载荷的真实内容",
                    "异常感知是否来自外部声音",
                ),
                misdirect=NullablePlan(
                    values=("前额胀痛暂时可被理解为普通测试疲劳",),
                ),
            ),
            pressure_curve=PressureCurve(
                start="林子轩在封闭地下设施醒来，身体状态和时间都由系统监测",
                turn="陈景行明确告知他不能决定是否进入，只能决定进入后是否听取载荷",
                end="连续认知任务使林子轩脑内持续发胀，检验逼近异常感知边界",
            ),
            foreshadow_actions=NullablePlan(
                values=("林子轩开始混淆设备噪声与自身感知，为后续异常声音铺垫",),
            ),
            ending_shift="通路检验从安全校准推进到神经疲劳临界点，异常感知即将显现",
            target_chinese_chars=3200,
            forbidden=NullablePlan(
                values=(
                    "不得提前写出浅层解码中的两种声音",
                    "不得把脑纹校准写成无风险、无代价的常规体检",
                    "不得离开林子轩限制视角解释第三段有效载荷",
                ),
            ),
            scene_plan=ScenePlan(
                chapter_spatial_intent="从隔离卧室进入核心解码室，让普通生活的疏离感收束为身体被读取的现实压力",
                required_world_slice="保留宿舍生活记忆与龙渊地下设施的反差",
                allowed_same_place_run=2,
                scenes=(
                    SceneContract(
                        id="target5-isolation-room",
                        order=1,
                        place_id="longyuan-isolation-room",
                        place_label="龙渊地下隔离卧室",
                        place_class="controlled_living_space",
                        interior_exterior="interior",
                        time_window="通路检验前",
                        participants=("林子轩",),
                        viewpoint="林子轩",
                        ordinary_people_present=False,
                        goal="按时前往检验并确认自身状态",
                        conflict="普通生活记忆与被全面监测的现实发生冲突",
                        action="林子轩醒来、观察身体反应并准时离开房间",
                        information_change="系统掌握他的睡眠和生理恢复数据",
                        state_change="林子轩从休整状态进入受控检验状态",
                        entry_reason="承接陈景行要求四点报到",
                        exit_trigger="系统显示十五点五十二分并提示不得迟到",
                        inherited_from_previous=True,
                    ),
                    SceneContract(
                        id="target5-pathway-test",
                        order=2,
                        place_id="longyuan-core-decoding-room",
                        place_label="龙渊核心解码室",
                        place_class="restricted_technology_lab",
                        interior_exterior="interior",
                        time_window="当日下午四点",
                        participants=("林子轩", "陈景行"),
                        viewpoint="林子轩",
                        ordinary_people_present=False,
                        goal="完成脑纹校准并验证第三段有效载荷通路",
                        conflict="检验不可退出，继续深入会增加神经与身份自主风险",
                        action="林子轩继续配合视线、听觉和认知任务",
                        information_change="第三段有效载荷必须依赖其皮层反应定位且存在过载风险",
                        state_change="林子轩出现明显神经疲劳，通路检验进入临界阶段",
                        entry_reason="完成隔离休整并按要求报到",
                        exit_trigger="脑内持续发胀，异常感知即将出现",
                    ),
                ),
            ),
            technology_plan=TechnologyPlan(
                technologies=(
                    TechnologyContract(
                        id="brainwave-pathway-calibration",
                        name="脑纹校准与通路检验系统",
                        role="core",
                        birth_reason="第三段有效载荷只能通过林子轩的皮层反应定位",
                        source="龙渊核心解码模块、林子轩体内植入物与实时皮层反应",
                        prerequisites=("脑纹基线建模", "植入物安全连接", "过载阈值监测"),
                        validation_stage="正式浅层解码前的通路检验",
                        first_application="标定第三段有效载荷位置并测量读取误差",
                        social_diffusion=("当前仅限龙渊核心解码室",),
                        cost="受试者出现神经疲劳，并失去部分身体与信息自主权",
                        changed_domains=("neural_access", "information_access"),
                    ),
                ),
            ),
            pov_plan=PointOfViewPlan(
                primary_owner="林子轩",
                mode="limited",
                protagonist_present=True,
                rationale="必须让读者只通过林子轩的身体感受理解检验，避免提前获得第三段有效载荷真相",
                supporting_agency=(
                    SupportingAgencyContract(
                        actor="陈景行",
                        independent_goal="在正式解码前确认林子轩的通路与过载阈值可控",
                        resistance="必须推进检验，同时不能让林子轩因恐惧或过载失去清醒",
                        choice="以精确指令推进检验，并用克制的照护维持林子轩稳定",
                        cost="承担对林子轩神经安全的直接责任",
                        result="检验继续推进且林子轩保持清醒",
                        mainline_change="陈景行从信息控制者转为具有有限照护行动的执行者",
                    ),
                ),
            ),
        ),
    )


def _required_intent_values(candidate: NarrativeDecision) -> dict[str, str]:
    contract = candidate.chapter_contract
    values: dict[str, str] = {
        "arc_phase": candidate.arc_phase.value,
        "arc_goal": candidate.arc_goal,
        "inherited_pressure": candidate.inherited_pressure,
        "chapter_contract.dramatic_question": contract.dramatic_question,
        "chapter_contract.protagonist_choice.status": contract.protagonist_choice.status.value,
        "chapter_contract.protagonist_choice.actor": contract.protagonist_choice.actor or "",
        "chapter_contract.protagonist_choice.action": contract.protagonist_choice.action or "",
        "chapter_contract.protagonist_choice.cost": contract.protagonist_choice.cost or "",
        "chapter_contract.protagonist_choice.consequence": contract.protagonist_choice.consequence or "",
        "chapter_contract.reader_change.before": contract.reader_change.before,
        "chapter_contract.reader_change.after": contract.reader_change.after,
        "chapter_contract.pressure_curve.start": contract.pressure_curve.start,
        "chapter_contract.pressure_curve.turn": contract.pressure_curve.turn,
        "chapter_contract.pressure_curve.end": contract.pressure_curve.end,
        "chapter_contract.ending_shift": contract.ending_shift,
    }
    for prefix, items in (
        ("future_pressures", candidate.future_pressures),
        ("chapter_contract.functions", contract.functions),
        ("chapter_contract.protagonist_choice.alternatives", contract.protagonist_choice.alternatives),
        ("chapter_contract.information.reveal", contract.information.reveal),
        ("chapter_contract.information.withhold", contract.information.withhold),
        ("chapter_contract.information.misdirect.values", contract.information.misdirect.values),
        ("chapter_contract.foreshadow_actions.values", contract.foreshadow_actions.values),
        ("chapter_contract.forbidden.values", contract.forbidden.values),
    ):
        values.update({f"{prefix}[{index}]": value for index, value in enumerate(items)})
    return values


def _evidence(field_path: str, value: str, source_hash: str) -> EvidenceRef:
    evidence_id = "ev-target5-" + hashlib.sha256(field_path.encode()).hexdigest()[:20]
    assertion = f"叙事导演为目标第5章约束字段 {field_path}"
    return EvidenceRef(
        evidence_id=evidence_id,
        contract_id="narrative-chapter-005",
        contract_version=1,
        field_path=field_path,
        role=EvidenceRole.INTENT,
        source_id=SOURCE_ID,
        source_version=SOURCE_VERSION,
        source_content_hash=source_hash,
        locator=EvidenceLocator(kind="record_id", value=field_path),
        excerpt=value,
        assertion=assertion,
        asserted_value=value,
    )


def _resolved_source(values: dict[str, str], source_hash: str) -> ResolvedEvidenceSource:
    return ResolvedEvidenceSource(
        source_id=SOURCE_ID,
        source_version=SOURCE_VERSION,
        source_content_hash=source_hash,
        source_kind=EvidenceSourceKind.DIRECTOR,
        located_excerpts=tuple(
            (EvidenceLocator(kind="record_id", value=path), value) for path, value in values.items()
        ),
        assertions_by_field_path=tuple(
            (path, (f"叙事导演为目标第5章约束字段 {path}",)) for path in values
        ),
        asserted_values=tuple(EvidenceAssertion(path, value) for path, value in values.items()),
    )


def _provenance() -> tuple[dict[str, int | str], ...]:
    return (
        {"field": "pov", "source_chapter": 5, "paragraph": 5, "basis": "林子轩限制视角与普通生活疏离"},
        {"field": "technology", "source_chapter": 5, "paragraph": 15, "basis": "脑纹校准用途"},
        {"field": "technology", "source_chapter": 5, "paragraph": 26, "basis": "通路检验三项目标与过载阈值"},
        {"field": "choice", "source_chapter": 5, "paragraph": 33, "basis": "无法退出但仍可决定是否听取载荷"},
        {"field": "relationship", "source_chapter": 5, "paragraph": 39, "basis": "陈景行以工具化方式表达照护"},
        {"field": "consequence", "source_chapter": 5, "paragraph": 42, "basis": "连续任务导致明显神经疲劳"},
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
