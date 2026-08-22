import ast
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import creative_os.domains.writer_admission as admission
from creative_os.domains.contract_baseline_resolver import AuthoritativeBaselineSnapshot, AuthorityRead
from creative_os.domains.contract_lifecycle import ContractLifecycleCoordinator
from creative_os.domains.contract_record_store import ExactContractRecords
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_memory import build_narrative_candidate_item
from creative_os.memory.model import MemoryEvidence
from tests.test_contract_preflight import AUTHORITATIVE_VALUES, _candidate, _profile, _source
from tests.test_contract_record_store import _approval, _baseline, _review


def test_signer_and_raw_signing_are_not_public_api():
    assert not hasattr(admission, "TokenSigner")
    assert not hasattr(admission.WriterAdmissionService, "sign")
    assert "signer" not in admission.WriterAdmissionService.__init__.__annotations__


def test_grant_and_token_use_distinct_type_tags_and_shapes():
    grant_fields = set(admission.AdmissionGrant.__dataclass_fields__)
    token_fields = set(admission.WriterAdmissionToken.__dataclass_fields__)
    assert "context_fingerprint" not in grant_fields
    assert "run_id" not in grant_fields
    assert {"context_fingerprint", "run_id", "authority_state_hash", "expires_at"} <= token_fields
    assert admission.WriterAdmissionService._GRANT_DOMAIN != admission.WriterAdmissionService._TOKEN_DOMAIN

    from creative_os.novel_continuation_runner import PreparedWriterRun
    assert "grant" not in PreparedWriterRun.__dataclass_fields__
    assert "projection" in PreparedWriterRun.__dataclass_fields__


def test_no_other_domain_imports_private_mac_or_constructs_signed_tokens():
    violations = []
    for path in Path("creative_os").rglob("*.py"):
        if path.name == "writer_admission.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)) and "writer_admission" in ast.unparse(node):
                if "_PrivateMac" in ast.unparse(node): violations.append(str(path))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"AdmissionGrant", "WriterAdmissionToken"}:
                violations.append(str(path))
    assert violations == []


def test_two_stage_service_rechecks_authority_and_binds_real_context(monkeypatch, tmp_path):
    project = tmp_path / "project"; lifecycle = ContractLifecycleCoordinator(project); original = _candidate()
    bindings = tuple(replace(b, evidence=tuple(replace(r, contract_version=1) for r in b.evidence))
                     for b in original.chapter_contract.intent_evidence_bindings)
    decision = replace(original, contract_version=1,
                       chapter_contract=replace(original.chapter_contract, intent_evidence_bindings=bindings))
    item = build_narrative_candidate_item(project, decision, evidence=(MemoryEvidence("test", "fixture"),),
                                          item_id="narrative-chapter-007-v0001")
    lifecycle.store.add_immutable(item); digest = NarrativeDecisionCodec.content_hash(decision); baseline = _baseline()
    approval = replace(_approval(baseline, contract_id=decision.contract_id), contract_version=1,
                       contract_content_hash=digest)
    review = _review(baseline, contract_id=decision.contract_id, issues=())
    review = review.__class__.build(result_id=review.result_id, contract_id=decision.contract_id,
        contract_version=1, contract_content_hash=digest, baseline_fingerprint=baseline.fingerprint,
        ruleset_version=review.ruleset_version, semantic_asset_versions=review.semantic_asset_versions, issues=())
    exact = ExactContractRecords("baseline", baseline, "approval", approval, "review", review)
    class Records:
        def __init__(self, root): pass
        def find_exact(self, **kwargs): return exact
    class Resolver:
        def resolve_manifest(self, root, entries):
            source = _source(AUTHORITATIVE_VALUES)
            return AuthoritativeBaselineSnapshot(_profile(), (), None, (),
                (AuthorityRead("profile", "profile-main", "5", "b"*64, "profile-v1", _profile(), (source,)),), (source,))
    monkeypatch.setattr("creative_os.domains.contract_lifecycle.ContractRecordStore", Records)
    lifecycle.activate_initial(decision.contract_id, 1, digest, baseline.fingerprint,
        resolver=Resolver(), actor="editor-tingyu", ruleset_version="prewrite-v1")
    monkeypatch.setattr(admission, "ContractRecordStore", Records)
    service = admission.WriterAdmissionService(project, Resolver())
    grant = service.pre_admit(admission.PreAdmissionRequest(decision.contract_id))
    with __import__("pytest").raises(admission.WriterAdmissionError):
        service.validate_grant_for_context(replace(grant, signature="0"*64))
    expired = replace(grant, expires_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
    with __import__("pytest").raises(admission.WriterAdmissionError):
        service.validate_grant_for_context(expired)
    token = service.finalize_admission(grant, "d"*64, "run-1")
    assert service.validate_token(token, "run-1", "d"*64) == token
    assert admission.WriterAdmissionService(project, Resolver()).validate_token(token, "run-1", "d"*64) == token

    # Re-open lifecycle/service state and execute the full two-stage admission path.
    (project / "production/final_chapters").mkdir(parents=True)
    (project / "production/final_chapters/chapter_006.md").write_text("# 第6章\n上一章结尾。", encoding="utf-8")
    (project / ".creative_os/import").mkdir(parents=True, exist_ok=True)
    (project / ".creative_os/import/baseline.json").write_text(
        '{"world_rules":[],"characters":[],"plot_milestones":[],"hooks":[],"style_constraints":[]}',
        encoding="utf-8",
    )
    (project / ".creative_os/import/conflicts.json").write_text("[]", encoding="utf-8")
    (project / ".creative_os/import/approval.json").write_text('{"resolutions":{}}', encoding="utf-8")
    from creative_os.novel_continuation_runner import prepare_continuation_run, continue_one_chapter
    reopened = admission.WriterAdmissionService(project, Resolver())
    prepared = prepare_continuation_run(project, "restart-run", reopened, decision.contract_id)
    result = continue_one_chapter(prepared, client=None, dry_run=True)
    assert result.status == "dry_run"
    pointer_path = project / ".creative_os/memory/contracts/pointers/contract-current-007.json"
    pointer_payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer_payload["activation_binding_hash"] = "0" * 64
    pointer_path.write_text(json.dumps(pointer_payload), encoding="utf-8")
    with __import__("pytest").raises(Exception):
        admission.WriterAdmissionService(project, Resolver()).pre_admit(
            admission.PreAdmissionRequest(decision.contract_id)
        )

    handoffs = []
    invalid = (
        (None, "run-1", "d" * 64),
        (grant, "run-1", "d" * 64),
        (replace(token, expires_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()), "run-1", "d" * 64),
        (replace(token, contract_content_hash="0" * 64), "run-1", "d" * 64),
        (token, "run-1", "e" * 64),
        (token, "wrong-run", "d" * 64),
    )
    for invalid_token, expected_run, fingerprint in invalid:
        with __import__("pytest").raises(admission.WriterAdmissionError):
            service.validate_token(invalid_token, expected_run, fingerprint,
                                   handoff=lambda: handoffs.append("side-effect"))
    assert handoffs == []
