from dataclasses import replace

from creative_os.domains.contract_fulfillment import (
    ContractFulfillmentEvaluator,
    FulfillmentArtifactMetadata,
    FulfillmentStatus,
)
from creative_os.domains.contract_fulfillment_store import ContractFulfillmentStore
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_evidence import EvidenceLocator, EvidenceRef, EvidenceRole
from creative_os.domains.narrative_decision import FieldEvidenceBinding, NullablePlan
from tests.test_contract_fulfillment_store import _record
from tests.test_contract_preflight import _candidate
from creative_os.domains.narrative_review import append_fulfillment_records


def _expected(contract, path):
    current = contract
    for segment in path.split("."):
        if "[" in segment:
            name, index = segment[:-1].split("[")
            current = getattr(current, name)[int(index)]
        else:
            current = getattr(current, segment)
    return current.value if hasattr(current, "value") else current


def _all_records(contract):
    digest = NarrativeDecisionCodec.content_hash(contract)
    records = []
    for index, binding in enumerate(contract.chapter_contract.intent_evidence_bindings):
        frozen_roles = {ref.role for ref in binding.evidence}
        roles = [EvidenceRole.VERIFICATION]
        if EvidenceRole.NON_APPLICABILITY not in frozen_roles:
            roles.append(EvidenceRole.REALIZATION)
        for role in roles:
            base = _record(f"fulfillment-{index}-{role.value}", role=role,
                           contract_id=contract.contract_id)
            expected = _expected(contract, binding.field_path)
            records.append(replace(
                base, contract_version=contract.contract_version, contract_content_hash=digest,
                field_path=binding.field_path,
                evidence=replace(base.evidence, contract_version=contract.contract_version,
                                 field_path=binding.field_path, asserted_value=expected),
            ))
    for offset, path in enumerate(("chapter_contract.chapter_id", "chapter_contract.target_chinese_chars")):
        base = _record(f"metadata-verification-{offset}", contract_id=contract.contract_id)
        records.append(replace(
            base, contract_version=contract.contract_version, contract_content_hash=digest,
            field_path=path,
            evidence=replace(base.evidence, contract_version=contract.contract_version,
                             field_path=path, asserted_value=_expected(contract, path),
                             source_id="final-chapter-7", source_version="v1",
                             source_content_hash="c" * 64),
        ))
    return tuple(records)


def _metadata(contract):
    return FulfillmentArtifactMetadata(
        chapter_id=contract.chapter_contract.chapter_id,
        target_chinese_chars=contract.chapter_contract.target_chinese_chars,
        source_id="final-chapter-7", source_version="v1", source_content_hash="c" * 64,
    )


def test_intent_evidence_alone_never_counts_as_fulfillment():
    contract = _candidate()
    result = ContractFulfillmentEvaluator().evaluate(contract, (), lambda _ref, _expected: True, _metadata(contract))
    assert result.status == FulfillmentStatus.INCOMPLETE
    assert all(field.missing_roles for field in result.fields)


def test_missing_frozen_leaf_binding_cannot_disappear_from_evaluation():
    original = _candidate()
    missing = original.chapter_contract.intent_evidence_bindings[0]
    contract = replace(original, chapter_contract=replace(
        original.chapter_contract,
        intent_evidence_bindings=original.chapter_contract.intent_evidence_bindings[1:],
    ))
    result = ContractFulfillmentEvaluator().evaluate(
        contract, _all_records(contract), lambda _ref, _expected: True, _metadata(contract),
    )
    assert EvidenceRole.INTENT in result.field(missing.field_path).missing_roles
    assert result.status == FulfillmentStatus.INCOMPLETE


def test_every_normal_leaf_requires_verification_and_realization():
    contract = _candidate()
    records = list(_all_records(contract))
    removed = next(record for record in records if record.evidence.role == EvidenceRole.REALIZATION)
    records.remove(removed)
    result = ContractFulfillmentEvaluator().evaluate(contract, tuple(records), lambda _ref, _expected: True, _metadata(contract))
    field = result.field(removed.field_path)
    assert field.missing_roles == (EvidenceRole.REALIZATION,)
    assert result.status == FulfillmentStatus.INCOMPLETE


def test_empty_nullable_field_uses_frozen_non_applicability_and_external_verification():
    original = _candidate()
    path = "chapter_contract.forbidden.not_applicable_reason"
    source_ref = original.chapter_contract.intent_evidence_bindings[0].evidence[0]
    non_applicable = replace(
        source_ref, evidence_id="na-forbidden", field_path=path,
        role=EvidenceRole.NON_APPLICABILITY, assertion="禁止项不适用", asserted_value="本章无禁止项",
    )
    intent = replace(
        source_ref, evidence_id="intent-forbidden-empty", field_path=path,
        role=EvidenceRole.INTENT, assertion="冻结禁止项为空", asserted_value="本章无禁止项",
    )
    contract = replace(original, chapter_contract=replace(
        original.chapter_contract,
        forbidden=NullablePlan((), "本章无禁止项"),
        intent_evidence_bindings=(*(binding for binding in original.chapter_contract.intent_evidence_bindings
                                    if not binding.field_path.startswith("chapter_contract.forbidden.values[")),
                                  FieldEvidenceBinding(path, (intent, non_applicable))),
    ))
    records = _all_records(contract)
    result = ContractFulfillmentEvaluator().evaluate(contract, records, lambda _ref, _expected: True, _metadata(contract))
    assert result.field(path).missing_roles == ()
    assert EvidenceRole.REALIZATION not in result.field(path).required_roles


def test_artifact_metadata_realizes_chapter_id_and_target_length():
    contract = _candidate()
    result = ContractFulfillmentEvaluator().evaluate(
        contract, _all_records(contract), lambda _ref, _expected: True, _metadata(contract),
    )
    assert result.status == FulfillmentStatus.FULFILLED
    assert result.field("chapter_contract.chapter_id").metadata_realized
    assert result.field("chapter_contract.target_chinese_chars").metadata_realized


def test_wrong_asserted_value_is_stale_even_when_path_and_role_match():
    contract = _candidate()
    records = list(_all_records(contract))
    target = records[0]
    records[0] = replace(target, evidence=replace(target.evidence, asserted_value="错误值"))
    result = ContractFulfillmentEvaluator().evaluate(
        contract, records, lambda _ref, _expected: True, _metadata(contract),
    )
    assert result.status == FulfillmentStatus.STALE
    assert target.record_id in result.stale_record_ids


def test_metadata_requires_verification_from_the_same_exact_artifact():
    contract = _candidate()
    metadata = replace(_metadata(contract), source_content_hash="d" * 64)
    result = ContractFulfillmentEvaluator().evaluate(
        contract, _all_records(contract), lambda _ref, _expected: True, metadata,
    )
    assert EvidenceRole.REALIZATION in result.field("chapter_contract.chapter_id").missing_roles
    assert result.status == FulfillmentStatus.INCOMPLETE


def test_any_stale_record_prevents_fulfilled_status():
    contract = _candidate()
    records = list(_all_records(contract))
    records.append(replace(records[0], record_id="stale-extra", contract_content_hash="0" * 64))
    result = ContractFulfillmentEvaluator().evaluate(
        contract, records, lambda _ref, _expected: True, _metadata(contract),
    )
    assert result.status == FulfillmentStatus.STALE


def test_old_contract_hash_and_failed_integrity_are_stale_not_fulfilled():
    contract = _candidate()
    records = list(_all_records(contract))
    records[0] = replace(records[0], contract_content_hash="0" * 64)
    result = ContractFulfillmentEvaluator().evaluate(contract, tuple(records), lambda ref, _expected: ref.source_id != "artifact-7",
                                                     _metadata(contract))
    assert result.status == FulfillmentStatus.STALE
    assert records[0].record_id in result.stale_record_ids


def test_superseded_record_is_not_used_and_evaluation_never_changes_contract_or_hash(tmp_path):
    contract = _candidate()
    before_json = NarrativeDecisionCodec.encode_v2(contract)
    before_hash = NarrativeDecisionCodec.content_hash(contract)
    records = list(_all_records(contract))
    target = records[0]
    store = ContractFulfillmentStore(tmp_path)
    store.append(target)
    correction = replace(
        target, record_id="correction-1", supersedes_record_id=target.record_id,
        evidence=replace(target.evidence, evidence_id="correction-evidence", excerpt="更正后的证据"),
    )
    store.append(correction)
    active = store.active_records(contract.contract_id, contract.contract_version, before_hash)
    assert active == (correction,)
    ContractFulfillmentEvaluator().evaluate(contract, active, lambda _ref, _expected: True, _metadata(contract))
    assert NarrativeDecisionCodec.encode_v2(contract) == before_json
    assert NarrativeDecisionCodec.content_hash(contract) == before_hash


def test_reviewer_only_appends_fulfillment_records(tmp_path):
    contract = _candidate()
    before = NarrativeDecisionCodec.encode_v2(contract)
    record = _all_records(contract)[0]
    store = ContractFulfillmentStore(tmp_path)
    assert append_fulfillment_records(store, (record,)) == (record,)
    assert store.recover() == (record,)
    assert NarrativeDecisionCodec.encode_v2(contract) == before


def test_reviewer_rejects_duck_typed_fulfillment_sink():
    class FakeStore:
        def append(self, record):
            raise AssertionError("must not be called")

    contract = _candidate()
    try:
        append_fulfillment_records(FakeStore(), (_all_records(contract)[0],))
    except TypeError:
        pass
    else:
        raise AssertionError("duck-typed store must be rejected")
