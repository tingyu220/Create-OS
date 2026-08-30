from dataclasses import replace
import json
import hashlib

import pytest

from creative_os.domains.contract_lifecycle import (
    ContractLifecycleCoordinator, ContractPointer, ContractStorageError,
)
from creative_os.domains.contract_revision import ContractRevisionRequest
from creative_os.domains.contract_approval import ApprovalStatus
from creative_os.domains.contract_baseline_resolver import AuthoritativeBaselineSnapshot, AuthorityRead
from creative_os.domains.contract_record_store import ContractRecordStore
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_memory import build_narrative_candidate_item
from creative_os.memory.model import MemoryEvidence, MemoryStatus
from tests.test_contract_preflight import AUTHORITATIVE_VALUES, _candidate, _profile, _source
from tests.test_contract_revision import _approved_change, _replacement
from tests.test_contract_record_store import _approval, _baseline, _review


def _pointer(decision, suffix, *, baseline_fingerprint=None):
    return ContractPointer.build(
        physical_key=f"{decision.contract_id}-v{decision.contract_version:04d}",
        contract_version=decision.contract_version,
        content_hash=NarrativeDecisionCodec.content_hash(decision),
        baseline_fingerprint=baseline_fingerprint or suffix * 64,
        approval_record_id=f"approval-{decision.contract_version}",
        approval_record_hash=("a" if suffix != "a" else "c") * 64,
        reviewer_result_id=f"review-{decision.contract_version}",
        reviewer_result_hash=("d" if suffix != "d" else "e") * 64,
        ruleset_version="rules-v1", semantic_asset_versions=(("semantics", "v1"),),
        disposition_set_hash="f" * 64,
    )


def _setup(project, *, create_replacement=True, replacement_baseline_fingerprint=None):
    lifecycle = ContractLifecycleCoordinator(project)
    current = _candidate()
    current_item = build_narrative_candidate_item(
        project, current, evidence=(MemoryEvidence("test", "current"),),
        item_id=f"{current.contract_id}-v{current.contract_version:04d}",
    ).activate(actor="editor")
    lifecycle.store.add_immutable(current_item)
    old_pointer = _pointer(current, "b")
    lifecycle.write_pointer(old_pointer)
    replacement = _replacement(current, arc_goal="新目标")
    approved = _approved_change(current.arc_goal, "新目标")
    replacement_baseline = replacement_baseline_fingerprint or "c" * 64
    revision = ContractRevisionRequest.build(
        current, replacement, base_baseline_fingerprint=old_pointer.baseline_fingerprint,
        replacement_baseline_fingerprint=replacement_baseline, causal_impact_paths=("arc_goal",),
        scene_impact="目标修订", approved_change_requests=(approved,),
    )
    if create_replacement:
        lifecycle.create_replacement_candidate(
            replacement, revision, authority_causal_impact_paths=("arc_goal",),
            authority_approved_change_requests=(approved,),
            evidence=(MemoryEvidence("test", "replacement"),),
        )
    new_pointer = _pointer(replacement, "c", baseline_fingerprint=replacement_baseline)
    return lifecycle, current, replacement, old_pointer, new_pointer, revision, approved


def _switch(lifecycle, old_pointer, new_pointer):
    return lifecycle.switch_replacement(
        old_pointer.physical_key.rsplit("-v", 1)[0], new_pointer.contract_version,
        new_pointer.content_hash, new_pointer.baseline_fingerprint,
        expected_pointer=old_pointer, resolver=object(), actor="editor",
        ruleset_version="rules-v1",
    )


def test_replacement_candidate_coexists_with_old_active_and_versions_are_contiguous(tmp_path):
    lifecycle, current, replacement, old_pointer, _, _, _ = _setup(tmp_path / "project")
    assert lifecycle.read_pointer(current.contract_id) == old_pointer
    assert lifecycle.store.get_strict(old_pointer.physical_key).status == MemoryStatus.ACTIVE
    assert lifecycle.store.get_strict(f"{replacement.contract_id}-v{replacement.contract_version:04d}").status == MemoryStatus.CANDIDATE
    assert tuple(item.contract_version for item in lifecycle.list_contract_versions(current.contract_id)) == (2, 3)


def test_switch_activates_new_before_cas_then_archives_old(monkeypatch, tmp_path):
    lifecycle, current, replacement, old_pointer, new_pointer, _, _ = _setup(tmp_path / "project")
    monkeypatch.setattr(ContractLifecycleCoordinator, "_prepare_replacement_pointer_locked",
                        lambda self, *args, **kwargs: new_pointer)
    assert _switch(lifecycle, old_pointer, new_pointer) == new_pointer
    assert lifecycle.read_pointer(current.contract_id) == new_pointer
    assert lifecycle.store.get_strict(old_pointer.physical_key).status == MemoryStatus.ARCHIVED
    assert lifecycle.store.get_strict(new_pointer.physical_key).status == MemoryStatus.ACTIVE


def test_pointer_cas_conflict_has_no_side_effect(monkeypatch, tmp_path):
    lifecycle, current, _, old_pointer, new_pointer, _, _ = _setup(tmp_path / "project")
    wrong = _pointer(current, "e")
    with pytest.raises(ContractStorageError, match="conflict|binding_mismatch"):
        _switch(lifecycle, wrong, new_pointer)
    assert lifecycle.read_pointer(old_pointer.physical_key.rsplit("-v", 1)[0]) == old_pointer
    assert lifecycle.store.get_strict(new_pointer.physical_key).status == MemoryStatus.CANDIDATE


@pytest.mark.parametrize("fault", (
    "after_prepare", "after_new_active", "after_pointer", "after_old_archive", "after_commit",
))
def test_every_switch_fault_recovers_deterministically(monkeypatch, tmp_path, fault):
    project = tmp_path / fault
    lifecycle, current, _, old_pointer, new_pointer, _, _ = _setup(project)
    monkeypatch.setattr(ContractLifecycleCoordinator, "_prepare_replacement_pointer_locked",
                        lambda self, *args, **kwargs: new_pointer)
    fired = False

    def crash(stage):
        nonlocal fired
        if stage == fault and not fired:
            fired = True
            raise RuntimeError(fault)

    monkeypatch.setattr("creative_os.domains.contract_lifecycle._switch_hook", crash)
    with pytest.raises(RuntimeError, match=fault):
        _switch(lifecycle, old_pointer, new_pointer)
    monkeypatch.setattr("creative_os.domains.contract_lifecycle._switch_hook", lambda stage: None)
    reopened = ContractLifecycleCoordinator(project)
    assert _switch(reopened, old_pointer, new_pointer) == new_pointer
    assert reopened.read_pointer(current.contract_id) == new_pointer
    assert reopened.store.get_strict(old_pointer.physical_key).status == MemoryStatus.ARCHIVED


def test_tampered_switch_state_cannot_skip_real_persisted_steps(monkeypatch, tmp_path):
    project = tmp_path / "project"
    lifecycle, current, _, old_pointer, new_pointer, _, _ = _setup(project)
    monkeypatch.setattr(ContractLifecycleCoordinator, "_prepare_replacement_pointer_locked",
                        lambda self, *args, **kwargs: new_pointer)
    monkeypatch.setattr(
        "creative_os.domains.contract_lifecycle._switch_hook",
        lambda stage: (_ for _ in ()).throw(RuntimeError(stage)) if stage == "after_prepare" else None,
    )
    with pytest.raises(RuntimeError):
        _switch(lifecycle, old_pointer, new_pointer)
    path = lifecycle._switch_journal_path(current.contract_id, new_pointer.contract_version)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["state"] = "pointer_switched"
    canonical = json.dumps(envelope["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    envelope["entry_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    path.write_bytes((json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
    monkeypatch.setattr("creative_os.domains.contract_lifecycle._switch_hook", lambda stage: None)
    assert _switch(ContractLifecycleCoordinator(project), old_pointer, new_pointer) == new_pointer
    assert ContractLifecycleCoordinator(project).store.get_strict(old_pointer.physical_key).status == MemoryStatus.ARCHIVED


def test_revision_authority_tamper_and_version_gap_fail_closed(tmp_path):
    lifecycle, current, replacement, old_pointer, new_pointer, _, _ = _setup(tmp_path / "project")
    path = lifecycle._revision_authority_path(current.contract_id, replacement.contract_version)
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'"schema_version":1', b'"schema_version":true'))
    with pytest.raises(ContractStorageError, match="invalid_revision_authority"):
        _switch(lifecycle, old_pointer, new_pointer)

    other = tmp_path / "history"
    history, current, _, _, _, _, _ = _setup(other)
    v4 = _replacement(_replacement(current, arc_goal="新目标"), arc_goal="再新目标")
    v5 = _replacement(v4, arc_goal="第三目标")
    item = build_narrative_candidate_item(
        other, v5, evidence=(MemoryEvidence("test", "gap"),),
        item_id=f"{v5.contract_id}-v{v5.contract_version:04d}",
    )
    history.store.add_immutable(item)
    with pytest.raises(ContractStorageError, match="history_gap"):
        history.list_contract_versions(current.contract_id)


def test_real_replacement_authority_is_reread_and_required_approval_na_is_blocked(tmp_path):
    baseline = _baseline()
    lifecycle, _, replacement, old_pointer, _, _, _ = _setup(
        tmp_path / "project", replacement_baseline_fingerprint=baseline.fingerprint,
    )
    digest = NarrativeDecisionCodec.content_hash(replacement)
    approval = replace(
        _approval(baseline, contract_id=replacement.contract_id),
        contract_version=replacement.contract_version,
        contract_content_hash=digest,
    )
    review_source = _review(baseline, contract_id=replacement.contract_id, issues=())
    review = review_source.__class__.build(
        result_id=review_source.result_id, contract_id=replacement.contract_id,
        contract_version=replacement.contract_version, contract_content_hash=digest,
        baseline_fingerprint=baseline.fingerprint, ruleset_version=review_source.ruleset_version,
        semantic_asset_versions=review_source.semantic_asset_versions, issues=(),
    )
    class Resolver:
        def resolve_manifest(self, root, entries):
            values = dict(AUTHORITATIVE_VALUES)
            values["arc_goal"] = "新目标"
            source = _source(values)
            return AuthoritativeBaselineSnapshot(
                _profile(), (), None, (),
                (AuthorityRead("profile", "profile-main", "5", "b" * 64,
                               "profile-v1", _profile(), (source,)),),
                (source,),
            )

    records = ContractRecordStore(lifecycle.project_root)
    records.save_baseline(replacement.contract_id, replacement.contract_version, baseline)
    records.save_approval(approval)
    records.save_reviewer_result(review)
    pointer = lifecycle.switch_replacement(
        replacement.contract_id, replacement.contract_version, digest, baseline.fingerprint,
        expected_pointer=old_pointer, resolver=Resolver(), actor="editor-tingyu",
        ruleset_version="prewrite-v1",
    )
    assert pointer.content_hash == digest

    not_applicable = replace(
        approval.post_freeze_revision, status=ApprovalStatus.NOT_APPLICABLE,
        reason="错误地标为不适用",
    )
    blocked_project = tmp_path / "blocked"
    blocked, _, blocked_replacement, blocked_old, _, _, _ = _setup(
        blocked_project, replacement_baseline_fingerprint=baseline.fingerprint,
    )
    blocked_digest = NarrativeDecisionCodec.content_hash(blocked_replacement)
    blocked_approval = replace(
        approval, contract_content_hash=blocked_digest, post_freeze_revision=not_applicable,
    )
    blocked_review = review.__class__.build(
        result_id=review.result_id, contract_id=blocked_replacement.contract_id,
        contract_version=blocked_replacement.contract_version,
        contract_content_hash=blocked_digest, baseline_fingerprint=baseline.fingerprint,
        ruleset_version=review.ruleset_version,
        semantic_asset_versions=review.semantic_asset_versions, issues=(),
    )
    blocked_records = ContractRecordStore(blocked_project)
    blocked_records.save_baseline(blocked_replacement.contract_id, blocked_replacement.contract_version, baseline)
    blocked_records.save_approval(blocked_approval)
    blocked_records.save_reviewer_result(blocked_review)
    with pytest.raises(ContractStorageError, match="missing_required_revision_approval"):
        blocked.switch_replacement(
            blocked_replacement.contract_id, blocked_replacement.contract_version,
            blocked_digest, baseline.fingerprint, expected_pointer=blocked_old,
            resolver=Resolver(), actor="editor-tingyu", ruleset_version="prewrite-v1",
        )


@pytest.mark.parametrize("fault", ("after_prepare", "after_authority", "after_candidate"))
def test_replacement_candidate_partial_creation_recovers_idempotently(monkeypatch, tmp_path, fault):
    project = tmp_path / fault
    lifecycle, _, replacement, _, _, revision, approved = _setup(
        project, create_replacement=False,
    )
    fired = False

    def crash(stage):
        nonlocal fired
        if stage == fault and not fired:
            fired = True
            raise RuntimeError(fault)

    monkeypatch.setattr("creative_os.domains.contract_lifecycle._revision_hook", crash)
    kwargs = dict(
        authority_causal_impact_paths=("arc_goal",),
        authority_approved_change_requests=(approved,),
        evidence=(MemoryEvidence("test", "replacement"),),
    )
    with pytest.raises(RuntimeError, match=fault):
        lifecycle.create_replacement_candidate(replacement, revision, **kwargs)
    monkeypatch.setattr("creative_os.domains.contract_lifecycle._revision_hook", lambda stage: None)
    reopened = ContractLifecycleCoordinator(project)
    recovered = reopened.recover_replacement_candidate(replacement, revision, **kwargs)
    assert recovered.status == MemoryStatus.CANDIDATE
    assert reopened._read_revision_authority(
        replacement.contract_id, replacement.contract_version,
        NarrativeDecisionCodec.content_hash(replacement),
    )["required_approvals"] == ["full_contract", "outline_change", "post_freeze_revision"]


def test_prepare_journal_schema_and_recovery_evidence_are_exact(tmp_path):
    project = tmp_path / "project"
    lifecycle, _, replacement, _, _, revision, approved = _setup(project)
    with pytest.raises(ContractStorageError, match="revision_prepare"):
        lifecycle.recover_replacement_candidate(
            replacement, revision, authority_causal_impact_paths=("arc_goal",),
            authority_approved_change_requests=(approved,),
            evidence=(MemoryEvidence("different", "audit"),),
        )
    path = lifecycle.memory_root / "contracts" / "revisions" / f".{replacement.contract_id}-v{replacement.contract_version:04d}.prepare.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["schema_version"] = True
    canonical = json.dumps(envelope["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    envelope["entry_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    path.write_bytes((json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
    with pytest.raises(ContractStorageError, match="invalid_revision_prepare_journal"):
        lifecycle.recover_replacement_candidate(
            replacement, revision, authority_causal_impact_paths=("arc_goal",),
            authority_approved_change_requests=(approved,),
            evidence=(MemoryEvidence("test", "replacement"),),
        )
