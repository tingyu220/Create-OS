from dataclasses import replace
import json
import shutil

from creative_os.domains.contract_preflight import ContractPreflightValidator
from creative_os.domains.contract_lifecycle import ContractLifecycleCoordinator
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.writer_admission import PreAdmissionRequest, WriterAdmissionService
from creative_os.memory.model import MemoryEvidence
from creative_os.memory.model import MemoryItem, MemoryKind, MemoryScope
from creative_os.memory.store import JsonMemoryStore
from scripts.build_civilization_target5_contract import (
    BASELINE_PATH,
    PROFILE_PATH,
    PROJECT_ROOT,
    SOURCE_ID,
    build_target5_baseline_manifest,
    activate_target5_contract,
    build_target5_draft,
    build_target5_review_pack,
)


def test_target5_draft_is_exactly_bound_and_preflight_ready():
    candidate, profile, source, causal_result, provenance = build_target5_draft()

    assert candidate.contract_id == "narrative-chapter-005"
    assert candidate.chapter_contract.protagonist_choice.action == "明知无法退出仍继续配合脑纹校准与通路检验"
    assert candidate.chapter_contract.protagonist_choice.cost == "承受持续神经疲劳，并接受自己的身体信号由龙渊设备读取"
    assert max(item["paragraph"] for item in provenance) == 42
    assert all(item["source_chapter"] == 5 for item in provenance)

    encoded = NarrativeDecisionCodec.encode_v3(candidate)
    assert NarrativeDecisionCodec.decode(encoded) == candidate

    result = ContractPreflightValidator().validate(
        candidate,
        lambda source_id: source if source_id == source.source_id else None,
        causal_result,
    )
    assert result.issues == ()
    assert result.is_ready is True
    profile.validate()


def test_target5_review_pack_is_dry_run_only_and_content_addressed():
    pack = build_target5_review_pack()

    assert pack["status"] == "REVIEW"
    assert pack["approval_required"] is True
    assert pack["approval_recorded"] is False
    assert pack["writer_allowed"] is False
    assert pack["contract_hash"] == "c6a79b4526f15dc9107a399f55941ee35423dfed4c1a80b72ceb72e19f3ef9f6"
    assert pack["baseline_hash"] == "753e892225ce0db350d441e948f31996b4fe109798807d3cbef77ccc45233b1a"
    assert pack["gates"] == {
        "causal_resolved": True,
        "codec_roundtrip": True,
        "preflight_ready": True,
        "reviewer_dry_run_ready": True,
    }
    assert max(item["paragraph"] for item in pack["provenance"]) == 42


def test_lifecycle_persists_v3_contract_without_losing_engagement(tmp_path):
    candidate, *_ = build_target5_draft()
    lifecycle = ContractLifecycleCoordinator(tmp_path / "文明升阶")

    lifecycle.create_initial_candidate(
        candidate,
        evidence=(MemoryEvidence("human_approval", "target5_exact_contract_review_v1"),),
    )

    stored = lifecycle.list_contract_versions(candidate.contract_id)
    assert stored == (candidate,)
    assert stored[0].schema_version == 3
    assert stored[0].chapter_contract.engagement_obligations == candidate.chapter_contract.engagement_obligations


def test_v3_contract_hash_covers_engagement_obligation():
    candidate, *_ = build_target5_draft()
    obligation = candidate.chapter_contract.engagement_obligations[0]
    changed = replace(
        candidate,
        chapter_contract=replace(
            candidate.chapter_contract,
            engagement_obligations=(replace(obligation, deadline_chapter=7),),
        ),
    )

    assert NarrativeDecisionCodec.content_hash(changed) != NarrativeDecisionCodec.content_hash(candidate)


def test_target5_baseline_manifest_binds_all_authority_roles():
    manifest = build_target5_baseline_manifest()
    entries = {entry.role: entry for entry in manifest.entries}

    assert set(entries) == {"profile", "fact_snapshot", "previous_chapter", "outline_change"}
    assert entries["profile"].source_id == "narrative-project-profile"
    assert entries["fact_snapshot"].source_id == "target5-director-authority-v1"
    assert entries["previous_chapter"].source_id == "production/final_chapters/chapter_004.md"
    assert entries["outline_change"].source_id == ".creative_os/import/active_baseline.json"
    assert PROFILE_PATH.exists()
    assert BASELINE_PATH.exists()
    assert (PROJECT_ROOT / entries["previous_chapter"].source_id).exists()
    assert SOURCE_ID == "director/civilization-target5-v1"


def test_target5_authority_reopens_exactly_after_activation(tmp_path):
    project = tmp_path / "文明升阶"
    (project / ".creative_os" / "import").mkdir(parents=True)
    (project / "production" / "final_chapters").mkdir(parents=True)
    shutil.copy2(BASELINE_PATH, project / ".creative_os" / "import" / "active_baseline.json")
    shutil.copy2(
        PROJECT_ROOT / "production" / "final_chapters" / "chapter_004.md",
        project / "production" / "final_chapters" / "chapter_004.md",
    )
    profile_envelope = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    profile_item = MemoryItem.new_candidate(
        id="narrative-project-profile",
        kind=MemoryKind.PROJECT_DECISION,
        scope=MemoryScope.PROJECT,
        scope_id=project.name,
        title="项目叙事承诺与剧情阶段",
        content=profile_envelope["content"],
        evidence=(MemoryEvidence("approved_profile", "narrative-project-profile"),),
        applicability=("writing", "planning", "review"),
        tags=("narrative_project_profile",),
        confidence=1.0,
    ).activate(actor="tingyu")
    JsonMemoryStore(project / ".creative_os" / "memory").add_immutable(profile_item)

    result = activate_target5_contract(
        project,
        actor="tingyu",
        approval_pack_hash="99fe0b22745886d1ad105dee92e99ef98b48b9a35f38b2e5dfe8a490ed38bbc9",
    )

    reopened = ContractLifecycleCoordinator(project)
    current = reopened.load_current("narrative-chapter-005")
    pointer = reopened.read_pointer("narrative-chapter-005")
    assert current == result["decision"]
    assert pointer == result["pointer"]
    assert pointer.content_hash == NarrativeDecisionCodec.content_hash(current)
    assert pointer.baseline_fingerprint == result["baseline"].fingerprint

    service = WriterAdmissionService(project, result["resolver"])
    grant = service.pre_admit(PreAdmissionRequest("narrative-chapter-005"))
    projection = NarrativeDecisionCodec.decode(grant.projection.canonical_json)
    assert projection.schema_version == 3
    assert (
        projection.chapter_contract.engagement_obligations
        == result["decision"].chapter_contract.engagement_obligations
    )
