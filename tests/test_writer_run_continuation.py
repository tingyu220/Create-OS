from dataclasses import replace
from datetime import datetime, timedelta, timezone

from creative_os.domains.contract_record_store import ContractRecordStore
from creative_os.domains.contract_revision import (
    RunContinuationStatus, WriterRunContinuationAuthorization,
)
from creative_os.domains.writer_admission import (
    AdmittedContractProjection, AdmissionAuthorityState, ContextExclusion,
    PreAdmissionRequest, RestrictedWriterAdmissionToken, WriterAdmissionError,
    WriterAdmissionService,
)
import creative_os.domains.writer_admission as admission_module
from creative_os.domains.contract_lifecycle import ContractLifecycleCoordinator, ContractPointer
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_memory import build_narrative_candidate_item
from creative_os.memory.model import MemoryEvidence
from tests.test_contract_preflight import _candidate
from tests.test_contract_revision import _replacement
from tests.test_contract_record_store import _install_prepared_journal, _io_path, _record_path
import pytest
from types import SimpleNamespace
from creative_os.domains.novel_continuation import ContinuationTask, continuation_task_hash
from creative_os.llm_writer import promote_llm_writer_pilot_to_final, run_llm_writer_pilot
from creative_os.novel_continuation_runner import (
    PreparedWriterRun, continue_one_chapter, promote_passing_draft,
)


def _authorization(**changes):
    now = datetime.now(timezone.utc)
    value = WriterRunContinuationAuthorization(
        authorization_id="continue-old-run-1", run_id="run-1",
        old_contract_id="narrative-chapter-007", old_contract_version=1,
        old_contract_hash="a" * 64, actor="editor-tingyu",
        reason="允许当前写作调用完成并立即停止",
        created_at=now.isoformat(), expires_at=(now + timedelta(minutes=10)).isoformat(),
    )
    return replace(value, **changes)


def test_continuation_authorization_is_append_only_exact_and_restartable(tmp_path):
    store = ContractRecordStore(tmp_path)
    authorization = _authorization()
    record_id = store.save_continuation_authorization(authorization)
    assert store.save_continuation_authorization(authorization) == record_id
    reopened = ContractRecordStore(tmp_path)
    assert reopened.load_continuation_authorization(record_id) == authorization
    assert reopened.find_exact_continuation_authorization(
        authorization_id=authorization.authorization_id, run_id="run-1",
        contract_id=authorization.old_contract_id, contract_version=1,
        contract_hash="a" * 64,
    ) == (record_id, authorization)


def test_revocation_is_a_superseding_human_record_and_removes_active_authority(tmp_path):
    store = ContractRecordStore(tmp_path)
    authorization = _authorization()
    store.save_continuation_authorization(authorization)
    revocation = _authorization(
        authorization_id="revoke-old-run-1", status=RunContinuationStatus.REVOKED,
        supersedes_authorization_id=authorization.authorization_id,
        reason="撤销旧运行继续权限",
    )
    store.save_continuation_authorization(revocation)
    assert store.find_exact_continuation_authorization(
        authorization_id=authorization.authorization_id, run_id="run-1",
        contract_id=authorization.old_contract_id, contract_version=1,
        contract_hash="a" * 64,
    ) is None


def test_authorization_global_identity_tamper_and_prepared_recovery(tmp_path):
    source_root = tmp_path / "source"
    source = ContractRecordStore(source_root)
    authorization = _authorization()
    record_id = source.save_continuation_authorization(authorization)
    with pytest.raises(Exception, match="authorization_id conflict"):
        source.save_continuation_authorization(replace(
            authorization, run_id="run-2", reason="另一运行复用同一身份",
        ))

    target_root = tmp_path / "target"
    ContractRecordStore(target_root)
    _install_prepared_journal(
        source_root, target_root, "continuation_authorization", record_id,
    )
    target = ContractRecordStore(target_root)
    target.recover()
    assert target.load(record_id) == authorization
    path = _record_path(target_root, "continuation_authorizations", record_id)
    io_path = _io_path(path)
    io_path.write_bytes(io_path.read_bytes().replace(b"editor-tingyu", b"editor-tamper"))
    with pytest.raises(Exception):
        ContractRecordStore(target_root).load_continuation_authorization(record_id)


def test_restricted_token_has_separate_domain_and_authorization_binding():
    assert WriterAdmissionService._RESTRICTED_DOMAIN not in {
        WriterAdmissionService._GRANT_DOMAIN, WriterAdmissionService._TOKEN_DOMAIN,
    }
    assert "authorization_id" in RestrictedWriterAdmissionToken.__dataclass_fields__
    assert "restricted_old_run" in RestrictedWriterAdmissionToken.__dataclass_fields__
    assert "projection_hash" in RestrictedWriterAdmissionToken.__dataclass_fields__


def _pointer(decision):
    return ContractPointer.build(
        physical_key=f"{decision.contract_id}-v{decision.contract_version:04d}",
        contract_version=decision.contract_version,
        content_hash=NarrativeDecisionCodec.content_hash(decision), baseline_fingerprint="b" * 64,
        approval_record_id="approval", approval_record_hash="c" * 64,
        reviewer_result_id="review", reviewer_result_hash="d" * 64,
        ruleset_version="rules-v1", semantic_asset_versions=(("semantic", "v1"),),
        disposition_set_hash="e" * 64,
    )


def test_old_token_dies_after_switch_and_only_exact_authorized_run_gets_restricted_token(tmp_path):
    project = tmp_path / "project"
    lifecycle = ContractLifecycleCoordinator(project)
    original = _candidate()
    v1 = replace(original, contract_version=1, chapter_contract=replace(
        original.chapter_contract,
        intent_evidence_bindings=tuple(replace(
            binding, evidence=tuple(replace(ref, contract_version=1) for ref in binding.evidence),
        ) for binding in original.chapter_contract.intent_evidence_bindings),
    ))
    item = build_narrative_candidate_item(
        project, v1, evidence=(MemoryEvidence("test", "v1"),),
        item_id=f"{v1.contract_id}-v0001",
    ).activate(actor="editor")
    lifecycle.store.add_immutable(item)
    old_pointer = _pointer(v1)
    lifecycle.write_pointer(old_pointer)
    projection = AdmittedContractProjection(
        v1.contract_id, 1, old_pointer.content_hash, NarrativeDecisionCodec.encode_v2(v1),
    )
    exclusions = (ContextExclusion(v1.contract_id, 1),)
    state = AdmissionAuthorityState(
        old_pointer, v1, "f" * 64, projection,
        admission_module._hash(projection.__dict__ if hasattr(projection, "__dict__") else {
            "contract_id": projection.contract_id, "contract_version": 1,
            "contract_content_hash": projection.contract_content_hash,
            "canonical_json": projection.canonical_json,
        }),
        exclusions, admission_module._hash([{"contract_id": v1.contract_id, "contract_version": 1}]),
    )
    service = WriterAdmissionService(project, object())
    service._evaluate_authority_locked = lambda contract_id: state
    grant = service.pre_admit(PreAdmissionRequest(v1.contract_id))
    old_token = service.finalize_admission(grant, "1" * 64, "run-1")

    v2 = _replacement(v1, arc_goal="新目标")
    lifecycle.store.add_immutable(build_narrative_candidate_item(
        project, v2, evidence=(MemoryEvidence("test", "v2"),),
        item_id=f"{v2.contract_id}-v0002",
    ).activate(actor="editor"))
    lifecycle.write_pointer(_pointer(v2))
    service._evaluate_authority_locked = lambda contract_id: (_ for _ in ()).throw(WriterAdmissionError("stale"))
    with pytest.raises(WriterAdmissionError):
        service.validate_token(old_token, "run-1", "1" * 64)

    authorization = _authorization(old_contract_hash=old_pointer.content_hash)
    ContractRecordStore(project).save_continuation_authorization(authorization)
    restricted = service.issue_restricted_continuation_token(old_token, authorization.authorization_id)
    assert service.validate_token(restricted, "run-1", "1" * 64) == restricted
    task = ContinuationTask(
        chapter_number=7, previous_chapter=6, narrative_goal="完成已启动的旧运行",
        required_facts=[], forbidden_contradictions=[], open_hooks=[], last_chapter_ending="结尾",
        character_states=[], target_chinese_chars=1000, min_chinese_chars=800,
        contract_projection=projection,
    )
    context = SimpleNamespace(
        fingerprint="1" * 64,
        size_chars=0,
        sources=(),
        task=SimpleNamespace(id="chapter-007", goal=task.narrative_goal),
        knowledge=(SimpleNamespace(id="writer-task:chapter:007", body=continuation_task_hash(task)),),
    )
    prepared = PreparedWriterRun(project, "run-1", task, context, projection, restricted, service)
    assert continue_one_chapter(prepared, client=None, dry_run=True).status == "dry_run"
    forged_projection = replace(projection, canonical_json="{}")
    forged_task = replace(task, contract_projection=forged_projection)
    forged_context = replace(
        context,
        knowledge=(SimpleNamespace(
            id="writer-task:chapter:007", body=continuation_task_hash(forged_task),
        ),),
    ) if hasattr(context, "__dataclass_fields__") else SimpleNamespace(
        fingerprint=context.fingerprint, size_chars=0, sources=(), task=context.task,
        knowledge=(SimpleNamespace(
            id="writer-task:chapter:007", body=continuation_task_hash(forged_task),
        ),),
    )
    forged = replace(prepared, task=forged_task, context=forged_context,
                     projection=forged_projection)
    exits = (
        lambda: continue_one_chapter(forged, client=None, dry_run=True),
        lambda: promote_passing_draft(forged),
        lambda: run_llm_writer_pilot(forged, client=None),
        lambda: promote_llm_writer_pilot_to_final(forged),
    )
    for production_exit in exits:
        with pytest.raises(ValueError, match="prepared run binding mismatch"):
            production_exit()
    with pytest.raises(WriterAdmissionError):
        service.validate_token(restricted, "other-run", "1" * 64)
    revocation = replace(
        authorization, authorization_id="revoke-old-run-1", status=RunContinuationStatus.REVOKED,
        supersedes_authorization_id=authorization.authorization_id, reason="撤销",
    )
    ContractRecordStore(project).save_continuation_authorization(revocation)
    with pytest.raises(WriterAdmissionError, match="not_active"):
        service.validate_token(restricted, "run-1", "1" * 64)
