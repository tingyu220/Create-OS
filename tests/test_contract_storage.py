import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from creative_os.domains.contract_lifecycle import (
    ContractLifecycleCoordinator,
    ContractPointer,
    ContractStorageError,
    create_initial_candidate,
    load_current,
    physical_key,
    read_pointer,
)
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryStatus
from creative_os.memory.store import JsonMemoryStore
from tests.test_narrative_memory import _decision


def _evidence() -> tuple[MemoryEvidence, ...]:
    return (MemoryEvidence(source_type="director", source_id="proposal-007"),)


def _lifecycle(tmp_path) -> tuple[ContractLifecycleCoordinator, object]:
    project = tmp_path / "文明升阶"
    return ContractLifecycleCoordinator(project), project


def _pointer(physical_key_value: str, version: int, content_hash: str) -> ContractPointer:
    return ContractPointer.build(
        physical_key=physical_key_value, contract_version=version, content_hash=content_hash,
        baseline_fingerprint="b" * 64, approval_record_id="approval-test",
        approval_record_hash="c" * 64, reviewer_result_id="review-test",
        reviewer_result_hash="d" * 64, ruleset_version="rules-v1",
        semantic_asset_versions=(("semantics", "v1"),), disposition_set_hash="e" * 64,
    )


def _race_initial_candidates(project, decisions):
    lifecycles = tuple(ContractLifecycleCoordinator(project) for _ in decisions)
    barrier = Barrier(len(decisions))

    def create(index):
        barrier.wait()
        try:
            return lifecycles[index].create_initial_candidate(
                decisions[index], evidence=_evidence()
            )
        except Exception as error:  # Assertions below verify the public error boundary.
            return error

    with ThreadPoolExecutor(max_workers=len(decisions)) as executor:
        return tuple(executor.map(create, range(len(decisions))))


def test_physical_key_and_pointer_require_the_same_strict_business_version():
    assert physical_key("narrative-chapter-007", 1) == "narrative-chapter-007-v0001"

    with pytest.raises(ValueError, match="contract_id"):
        physical_key("chapter-007", 1)
    with pytest.raises(ValueError, match="contract_version"):
        physical_key("narrative-chapter-007", True)
    with pytest.raises(ValueError, match="contract_version"):
        physical_key("narrative-chapter-007", 10_000)
    with pytest.raises(ValueError, match="physical_key.*contract_version"):
        _pointer("narrative-chapter-007-v0002", 1, "a" * 64)


def test_create_initial_candidate_persists_only_canonical_v0001_without_pointer(tmp_path):
    lifecycle, project = _lifecycle(tmp_path)
    decision = _decision()

    item = lifecycle.create_initial_candidate(decision, evidence=_evidence())

    assert item.id == "narrative-chapter-007-v0001"
    assert item.content == NarrativeDecisionCodec.encode_v2(decision)
    assert item.version == 1
    assert item.status == MemoryStatus.CANDIDATE
    assert lifecycle.read_pointer(decision.contract_id) is None
    assert lifecycle.load_current(decision.contract_id) is None
    assert not (
        project
        / ".creative_os"
        / "memory"
        / "contracts"
        / "pointers"
        / "contract-current-007.json"
    ).exists()

    with pytest.raises(ContractStorageError, match="initial_contract_version_must_be_1"):
        lifecycle.create_initial_candidate(replace(decision, contract_version=2), evidence=_evidence())


def test_module_level_storage_api_uses_the_same_pointer_only_contract(tmp_path):
    project = tmp_path / "文明升阶"
    decision = _decision()

    item = create_initial_candidate(project, decision, evidence=_evidence())

    assert item.id == "narrative-chapter-007-v0001"
    assert read_pointer(project, 7) is None
    assert load_current(project, decision.contract_id) is None


def test_repeated_same_hash_is_idempotent_but_different_content_cannot_overwrite(tmp_path):
    lifecycle, project = _lifecycle(tmp_path)
    decision = _decision()
    original = lifecycle.create_initial_candidate(decision, evidence=_evidence())
    item_path = project / ".creative_os" / "memory" / "items" / f"{original.id}.json"
    before = item_path.read_bytes()

    repeated = lifecycle.create_initial_candidate(decision, evidence=_evidence())

    assert repeated == original
    assert item_path.read_bytes() == before

    with pytest.raises(ContractStorageError, match="immutable_contract_conflict"):
        lifecycle.create_initial_candidate(
            replace(decision, arc_goal="同一版本不得覆盖的新目标"),
            evidence=_evidence(),
        )

    assert item_path.read_bytes() == before


def test_concurrent_same_contract_content_returns_the_single_persisted_candidate(tmp_path):
    decision = _decision()

    for round_number in range(12):
        project = tmp_path / f"same-{round_number}" / "文明升阶"
        results = _race_initial_candidates(project, (decision,) * 8)
        stored = JsonMemoryStore(project / ".creative_os" / "memory").get_strict(
            "narrative-chapter-007-v0001"
        )

        assert results == (stored,) * 8
        assert list((project / ".creative_os" / "memory" / "items").glob("*.tmp")) == []


def test_concurrent_different_contract_content_has_one_winner_and_one_conflict(tmp_path):
    first = _decision()
    second = replace(first, arc_goal="同一版本的竞争剧情目标")

    for round_number in range(12):
        project = tmp_path / f"different-{round_number}" / "文明升阶"
        results = _race_initial_candidates(project, (first, second))
        successes = tuple(result for result in results if isinstance(result, MemoryItem))
        errors = tuple(result for result in results if isinstance(result, Exception))

        assert len(successes) == 1
        assert len(errors) == 1
        assert isinstance(errors[0], ContractStorageError)
        assert str(errors[0]) == "immutable_contract_conflict"
        assert (
            JsonMemoryStore(project / ".creative_os" / "memory").get_strict(
                "narrative-chapter-007-v0001"
            )
            == successes[0]
        )
        assert list((project / ".creative_os" / "memory" / "items").glob("*.tmp")) == []


def test_current_read_uses_only_the_complete_activation_bound_pointer(tmp_path):
    lifecycle, project = _lifecycle(tmp_path)
    decision = _decision()
    candidate = lifecycle.create_initial_candidate(decision, evidence=_evidence())
    store = JsonMemoryStore(project / ".creative_os" / "memory")
    store.replace(candidate.activate(actor="测试审批人"))

    assert lifecycle.load_current(decision.contract_id) is None

    pointer = _pointer(candidate.id, decision.contract_version, NarrativeDecisionCodec.content_hash(decision))
    lifecycle.write_pointer(pointer)
    pointer_path = (
        project
        / ".creative_os"
        / "memory"
        / "contracts"
        / "pointers"
        / "contract-current-007.json"
    )

    assert json.loads(pointer_path.read_text(encoding="utf-8")) == pointer.to_dict()
    assert not pointer_path.with_suffix(".json.tmp").exists()
    assert lifecycle.read_pointer(decision.contract_id) == pointer
    assert lifecycle.load_current(decision.contract_id) == decision


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    [
        ("missing_target", "missing_contract_pointer_target"),
        ("candidate_target", "contract_pointer_target_not_active"),
        ("wrong_hash", "contract_pointer_hash_mismatch"),
        ("wrong_envelope_version", "invalid_contract_envelope_version"),
        ("version_mismatch", "contract_pointer_version_mismatch"),
    ],
)
def test_pointer_reads_fail_closed_on_missing_or_inconsistent_targets(tmp_path, mutation, error_code):
    lifecycle, project = _lifecycle(tmp_path)
    decision = _decision()
    candidate = lifecycle.create_initial_candidate(decision, evidence=_evidence())
    store = JsonMemoryStore(project / ".creative_os" / "memory")
    pointer_key = candidate.id
    pointer_version = 1
    pointer_hash = NarrativeDecisionCodec.content_hash(decision)

    if mutation == "missing_target":
        version_two = replace(decision, contract_version=2)
        pointer_key = physical_key(decision.contract_id, 2)
        pointer_version = 2
        pointer_hash = NarrativeDecisionCodec.content_hash(version_two)
    elif mutation == "candidate_target":
        pass
    elif mutation == "wrong_hash":
        store.replace(candidate.activate(actor="测试审批人"))
        pointer_hash = "0" * 64
    elif mutation == "wrong_envelope_version":
        store.replace(replace(candidate.activate(actor="测试审批人"), version=2))
    elif mutation == "version_mismatch":
        version_two = replace(decision, contract_version=2)
        store.replace(
            replace(
                candidate.activate(actor="测试审批人"),
                content=NarrativeDecisionCodec.encode_v2(version_two),
            )
        )

    pointer_path = (
        project
        / ".creative_os"
        / "memory"
        / "contracts"
        / "pointers"
        / "contract-current-007.json"
    )
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_payload = _pointer(pointer_key, pointer_version, pointer_hash).to_dict()
    pointer_path.write_text(json.dumps(pointer_payload), encoding="utf-8")

    with pytest.raises(ContractStorageError, match=error_code):
        lifecycle.read_pointer(decision.contract_id)


def test_pointer_document_rejects_extra_fields_before_loading_target(tmp_path):
    lifecycle, project = _lifecycle(tmp_path)
    pointer_path = (
        project
        / ".creative_os"
        / "memory"
        / "contracts"
        / "pointers"
        / "contract-current-007.json"
    )
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(
        json.dumps(
            {
                "physical_key": "narrative-chapter-007-v0001",
                "contract_version": 1,
                "content_hash": "a" * 64,
                "status": "active",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractStorageError, match="invalid_contract_pointer"):
        lifecycle.read_pointer("narrative-chapter-007")


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_envelope_field",
        "boolean_version",
        "string_version",
        "missing_title",
        "non_string_content",
        "non_string_status",
        "unknown_evidence_field",
        "non_string_evidence_field",
    ],
)
def test_pointer_target_requires_an_exact_typed_raw_envelope(tmp_path, mutation):
    lifecycle, project = _lifecycle(tmp_path)
    decision = _decision()
    candidate = lifecycle.create_initial_candidate(decision, evidence=_evidence())
    store = JsonMemoryStore(project / ".creative_os" / "memory")
    store.replace(candidate.activate(actor="测试审批人"))
    pointer = _pointer(candidate.id, 1, NarrativeDecisionCodec.content_hash(decision))
    lifecycle.write_pointer(pointer)
    item_path = store.items_dir / f"{candidate.id}.json"
    payload = json.loads(item_path.read_text(encoding="utf-8"))

    if mutation == "unknown_envelope_field":
        payload["audit"] = []
    elif mutation == "boolean_version":
        payload["version"] = True
    elif mutation == "string_version":
        payload["version"] = "1"
    elif mutation == "missing_title":
        payload.pop("title")
    elif mutation == "non_string_content":
        payload["content"] = {"schema_version": 2}
    elif mutation == "non_string_status":
        payload["status"] = True
    elif mutation == "unknown_evidence_field":
        payload["evidence"][0]["audit"] = "unexpected"
    elif mutation == "non_string_evidence_field":
        payload["evidence"][0]["source_id"] = 7

    item_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ContractStorageError, match="invalid_contract_envelope"):
        lifecycle.read_pointer(decision.contract_id)


def test_pointer_target_rejects_unknown_contract_content_fields(tmp_path):
    lifecycle, project = _lifecycle(tmp_path)
    decision = _decision()
    candidate = lifecycle.create_initial_candidate(decision, evidence=_evidence())
    store = JsonMemoryStore(project / ".creative_os" / "memory")
    store.replace(candidate.activate(actor="测试审批人"))
    lifecycle.write_pointer(
        _pointer(candidate.id, 1, NarrativeDecisionCodec.content_hash(decision))
    )
    item_path = store.items_dir / f"{candidate.id}.json"
    payload = json.loads(item_path.read_text(encoding="utf-8"))
    content = json.loads(payload["content"])
    content["audit"] = []
    payload["content"] = json.dumps(content, ensure_ascii=False)
    item_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ContractStorageError, match="invalid_contract_content"):
        lifecycle.load_current(decision.contract_id)
