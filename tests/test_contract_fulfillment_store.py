from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
import creative_os.domains.contract_fulfillment_store as fulfillment_store

from creative_os.domains.contract_fulfillment import ContractFulfillmentEvidenceRecord
from creative_os.domains.contract_fulfillment_store import (
    ContractFulfillmentStore,
    ContractFulfillmentStoreError,
)
from creative_os.domains.narrative_evidence import EvidenceLocator, EvidenceRef, EvidenceRole


def _record(record_id="fulfillment-1", *, role=EvidenceRole.VERIFICATION,
            contract_id="narrative-chapter-007", supersedes=None):
    evidence = EvidenceRef(
        evidence_id=f"evidence-{record_id}", contract_id=contract_id, contract_version=2,
        field_path="chapter_contract.protagonist_choice.cost", role=role,
        source_id="artifact-7", source_version="sha-1", source_content_hash="a" * 64,
        locator=EvidenceLocator("line_range", "10-12"), excerpt="代价已经发生",
        assertion="正文实现选择代价", asserted_value="暴露自己",
    )
    return ContractFulfillmentEvidenceRecord(
        record_id=record_id, contract_id=contract_id, contract_version=2,
        contract_content_hash="b" * 64,
        field_path="chapter_contract.protagonist_choice.cost", evidence=evidence,
        recorded_at="2026-08-22T12:00:00+00:00", supersedes_record_id=supersedes,
    )


def test_record_rejects_non_fulfillment_roles_and_mismatched_binding():
    with pytest.raises(ValueError, match="verification or realization"):
        _record(role=EvidenceRole.INTENT)
    with pytest.raises(ValueError, match="field_path"):
        replace(_record(), field_path="chapter_contract.ending_shift")
    with pytest.raises(ValueError, match="source_content_hash"):
        replace(_record(), evidence=replace(_record().evidence, source_content_hash="not-a-hash"))


def test_append_is_idempotent_but_duplicate_id_with_other_content_conflicts(tmp_path):
    store = ContractFulfillmentStore(tmp_path)
    record = _record()
    assert store.append(record) == record
    assert store.append(record) == record
    with pytest.raises(ContractFulfillmentStoreError, match="record_id_conflict"):
        store.append(replace(record, recorded_at="2026-08-22T12:01:00+00:00"))
    assert store.records_for(record.contract_id, 2, "b" * 64) == (record,)


def test_supersede_is_append_only_and_active_records_hide_replaced_record(tmp_path):
    store = ContractFulfillmentStore(tmp_path)
    first = _record()
    correction = _record("fulfillment-2", role=EvidenceRole.REALIZATION,
                         supersedes=first.record_id)
    store.append(first)
    store.append(correction)
    assert store.records_for(first.contract_id, 2, "b" * 64) == (first, correction)
    assert store.active_records(first.contract_id, 2, "b" * 64) == (correction,)


def test_cross_contract_or_missing_supersede_is_rejected(tmp_path):
    store = ContractFulfillmentStore(tmp_path)
    store.append(_record())
    with pytest.raises(ContractFulfillmentStoreError, match="supersedes_missing"):
        store.append(_record("fulfillment-2", supersedes="unknown"))
    with pytest.raises(ContractFulfillmentStoreError, match="supersedes_binding_mismatch"):
        store.append(_record("fulfillment-3", contract_id="narrative-chapter-008",
                             supersedes="fulfillment-1"))


def test_concurrent_same_record_is_one_physical_append(tmp_path):
    record = _record()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: ContractFulfillmentStore(tmp_path).append(record), range(16)))
    assert results == [record] * 16
    assert ContractFulfillmentStore(tmp_path).records_for(record.contract_id, 2, "b" * 64) == (record,)


def test_restart_exact_read_and_tamper_rejection(tmp_path):
    store = ContractFulfillmentStore(tmp_path)
    record = _record()
    store.append(record)
    reopened = ContractFulfillmentStore(tmp_path)
    assert reopened.recover() == (record,)
    path = tmp_path / ".creative_os/memory/contract_fulfillment/records.jsonl"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("代价已经发生", "代价尚未发生"), encoding="utf-8")
    with pytest.raises(ContractFulfillmentStoreError, match="tampered"):
        ContractFulfillmentStore(tmp_path).recover()


def test_deletion_truncation_and_reordering_are_rejected(tmp_path):
    store = ContractFulfillmentStore(tmp_path)
    store.append(_record())
    store.append(_record("fulfillment-2", supersedes="fulfillment-1"))
    path = tmp_path / ".creative_os/memory/contract_fulfillment/records.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[0] + "\n", encoding="utf-8")
    with pytest.raises(ContractFulfillmentStoreError, match="tampered"):
        ContractFulfillmentStore(tmp_path).recover()

    path.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")
    with pytest.raises(ContractFulfillmentStoreError, match="tampered"):
        ContractFulfillmentStore(tmp_path).recover()


@pytest.mark.parametrize("mutation", ["extra_evidence", "boolean_schema", "duplicate_key", "noncanonical",
                                      "blank_line", "crlf", "extra_newline"])
def test_decoder_rejects_non_strict_json_and_schema(tmp_path, mutation):
    store = ContractFulfillmentStore(tmp_path)
    store.append(_record())
    path = tmp_path / ".creative_os/memory/contract_fulfillment/records.jsonl"
    text = path.read_text(encoding="utf-8")
    if mutation == "extra_evidence":
        text = text.replace('"evidence_id":', '"extra":1,"evidence_id":')
    elif mutation == "boolean_schema":
        text = text.replace('"schema_version":1', '"schema_version":true')
    elif mutation == "duplicate_key":
        text = text.replace('{"entry_hash":', '{"entry_hash":"0","entry_hash":')
    elif mutation == "blank_line":
        text = "\n" + text
    elif mutation == "crlf":
        text = text.replace("\n", "\r\n")
    elif mutation == "extra_newline":
        text += "\n"
    else:
        text = text.replace(',', ', ', 1)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ContractFulfillmentStoreError, match="tampered"):
        ContractFulfillmentStore(tmp_path).recover()


def test_prepared_journal_recovers_partial_append_without_mutating_old_line(tmp_path):
    store = ContractFulfillmentStore(tmp_path)
    first = _record()
    store.append(first)
    original = (tmp_path / ".creative_os/memory/contract_fulfillment/records.jsonl").read_bytes()
    second = _record("fulfillment-2", supersedes=first.record_id)
    store._write_prepared_for_test(second)
    reopened = ContractFulfillmentStore(tmp_path)
    assert reopened.recover() == (first, second)
    assert (tmp_path / ".creative_os/memory/contract_fulfillment/records.jsonl").read_bytes().startswith(original)


def test_store_never_changes_contract_or_approval_authority_files(tmp_path):
    contract = tmp_path / ".creative_os/memory/items/contract.json"
    approval = tmp_path / ".creative_os/memory/contract_records/approvals/approval.json"
    contract.parent.mkdir(parents=True)
    approval.parent.mkdir(parents=True)
    contract.write_bytes(b"contract-authority")
    approval.write_bytes(b"approval-authority")
    ContractFulfillmentStore(tmp_path).append(_record())
    assert contract.read_bytes() == b"contract-authority"
    assert approval.read_bytes() == b"approval-authority"


@pytest.mark.parametrize(
    ("failure_event", "recovered_count"),
    [
        ("before_replace:journal.json", 0),
        ("before_records_replace", 1),
        ("before_replace:head.json", 1),
        ("before_journal_unlink", 1),
    ],
)
def test_each_commit_stage_recovers_without_duplicate(monkeypatch, tmp_path, failure_event, recovered_count):
    fired = False

    def fail_once(event, _path):
        nonlocal fired
        if event == failure_event and not fired:
            fired = True
            raise OSError("injected failure")

    monkeypatch.setattr(fulfillment_store, "_IO_HOOK", fail_once)
    with pytest.raises(OSError, match="injected failure"):
        ContractFulfillmentStore(tmp_path).append(_record())
    monkeypatch.setattr(fulfillment_store, "_IO_HOOK", lambda *_args: None)
    reopened = ContractFulfillmentStore(tmp_path)
    assert len(reopened.recover()) == recovered_count
    if recovered_count:
        reopened.append(_record())
        assert len(reopened.recover()) == 1
