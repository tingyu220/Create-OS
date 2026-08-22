import inspect
from dataclasses import replace

import pytest

from creative_os.domains.contract_lifecycle import ContractLifecycleCoordinator
from creative_os.domains.contract_baseline_resolver import AuthoritativeBaselineSnapshot, AuthorityRead
from creative_os.domains.contract_record_store import ExactContractRecords
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_memory import build_narrative_candidate_item
from creative_os.memory.model import MemoryEvidence
from tests.test_contract_preflight import AUTHORITATIVE_VALUES, _candidate, _profile, _source
from tests.test_contract_record_store import _approval, _baseline, _review


def test_activate_initial_requires_reviewer_ruleset():
    parameter = inspect.signature(ContractLifecycleCoordinator.activate_initial).parameters["ruleset_version"]
    assert parameter.default is inspect.Parameter.empty


def test_recover_initial_does_not_trust_existing_pointer(monkeypatch, tmp_path):
    lifecycle = ContractLifecycleCoordinator(tmp_path / "project")
    monkeypatch.setattr(lifecycle, "read_pointer", lambda contract_id: object())
    calls = []
    monkeypatch.setattr(lifecycle, "activate_initial", lambda *args, **kwargs: calls.append((args, kwargs)) or "verified")

    result = lifecycle.recover_initial(
        "narrative-chapter-001",
        contract_version=1,
        contract_hash="a" * 64,
        baseline_fingerprint="b" * 64,
        resolver=object(),
        actor="editor",
        ruleset_version="rules-v1",
    )

    assert result == "verified"
    assert len(calls) == 1


def test_activate_initial_reruns_real_preflight_and_causal(monkeypatch, tmp_path):
    project = tmp_path / "project"
    lifecycle = ContractLifecycleCoordinator(project)
    original = _candidate()
    bindings = tuple(
        replace(binding, evidence=tuple(replace(ref, contract_version=1) for ref in binding.evidence))
        for binding in original.chapter_contract.intent_evidence_bindings
    )
    decision = replace(
        original, contract_version=1,
        chapter_contract=replace(original.chapter_contract, intent_evidence_bindings=bindings),
    )
    item = build_narrative_candidate_item(
        project, decision, evidence=(MemoryEvidence("test", "fixture"),),
        item_id="narrative-chapter-007-v0001",
    )
    lifecycle.store.add_immutable(item)
    digest = NarrativeDecisionCodec.content_hash(decision)
    baseline = _baseline()
    approval = _approval(baseline, contract_id=decision.contract_id)
    approval = replace(approval, contract_version=1, contract_content_hash=digest)
    review = _review(baseline, contract_id=decision.contract_id, issues=())
    review = review.__class__.build(
        result_id=review.result_id, contract_id=decision.contract_id, contract_version=1,
        contract_content_hash=digest, baseline_fingerprint=baseline.fingerprint,
        ruleset_version=review.ruleset_version,
        semantic_asset_versions=review.semantic_asset_versions, issues=(),
    )
    exact = ExactContractRecords("baseline", baseline, "approval", approval, "review", review)

    class Records:
        def __init__(self, root): pass
        def find_exact(self, **kwargs): return exact

    class Resolver:
        def resolve_manifest(self, root, entries):
            source = _source(AUTHORITATIVE_VALUES)
            return AuthoritativeBaselineSnapshot(
                _profile(), (), None, (),
                (AuthorityRead("profile", "profile-main", "5", "b" * 64, "profile-v1", _profile(), (source,)),),
                (source,),
            )

    monkeypatch.setattr("creative_os.domains.contract_lifecycle.ContractRecordStore", Records)
    pointer = lifecycle.activate_initial(
        decision.contract_id, 1, digest, baseline.fingerprint,
        resolver=Resolver(), actor="editor-tingyu", ruleset_version="prewrite-v1",
    )
    assert pointer.content_hash == digest
    assert pointer.baseline_fingerprint == baseline.fingerprint
    assert pointer.approval_record_id == "approval"
    assert pointer.reviewer_result_id == "review"
    assert pointer.ruleset_version == "prewrite-v1"
    assert len(pointer.activation_binding_hash) == 64
    assert lifecycle.read_pointer(decision.contract_id) == pointer


def test_activate_initial_rejects_non_initial_version(tmp_path):
    lifecycle = ContractLifecycleCoordinator(tmp_path / "project")
    with pytest.raises(Exception, match="initial_contract_version_must_be_1"):
        lifecycle.activate_initial(
            "narrative-chapter-007", 2, "a" * 64, "b" * 64,
            resolver=object(), actor="editor", ruleset_version="prewrite-v1",
        )
