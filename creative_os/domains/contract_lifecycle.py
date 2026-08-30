from __future__ import annotations

import json
import hashlib
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import NarrativeDecision
from creative_os.domains.narrative_memory import build_narrative_candidate_item
from creative_os.domains.contract_baseline_resolver import BaselineSourceResolver, ResolverError
from creative_os.domains.contract_record_store import ContractRecordStore
from creative_os.domains.contract_record_store import authoritative_record_hash
from creative_os.domains.contract_approval import ApprovalStatus, ContractApprovalPolicy
from creative_os.domains.contract_preflight import ContractPreflightValidator
from creative_os.domains.contract_review import validate_reviewer_gate
from creative_os.domains.narrative_causality import CausalDependencyAnalyzer
from creative_os.domains.contract_revision import ContractRevisionRequest
from creative_os.domains.narrative_decision import NarrativeChangeRequest
from creative_os.domains.project_authority import project_authority_lock
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope, MemoryStatus
from creative_os.memory.store import (
    ImmutableMemoryConflictError,
    JsonMemoryStore,
    MemoryStoreError,
)


_CONTRACT_ID_PATTERN = re.compile(r"^narrative-chapter-(00[1-9]|0[1-9][0-9]|[1-9][0-9]{2})$")
_PHYSICAL_KEY_PATTERN = re.compile(
    r"^(narrative-chapter-(?:00[1-9]|0[1-9][0-9]|[1-9][0-9]{2}))-v([0-9]{4})$"
)
_POINTER_FIELDS = frozenset({
    "physical_key", "contract_version", "content_hash", "baseline_fingerprint",
    "approval_record_id", "approval_record_hash", "reviewer_result_id",
    "reviewer_result_hash", "ruleset_version", "semantic_asset_versions",
    "disposition_set_hash", "activation_binding_hash",
})


class ContractStorageError(ValueError):
    """A persisted contract or pointer failed its closed-world invariants."""


def physical_key(contract_id: str, contract_version: int) -> str:
    _require_contract_id(contract_id)
    _require_contract_version(contract_version)
    return f"{contract_id}-v{contract_version:04d}"


@dataclass(frozen=True, slots=True)
class ContractPointer:
    physical_key: str
    contract_version: int
    content_hash: str
    baseline_fingerprint: str
    approval_record_id: str
    approval_record_hash: str
    reviewer_result_id: str
    reviewer_result_hash: str
    ruleset_version: str
    semantic_asset_versions: tuple[tuple[str, str], ...]
    disposition_set_hash: str
    activation_binding_hash: str

    def __post_init__(self) -> None:
        contract_id, key_version = _parse_physical_key(self.physical_key)
        del contract_id
        _require_contract_version(self.contract_version)
        if key_version != self.contract_version:
            raise ValueError("physical_key contract_version mismatch")
        _require_sha256(self.content_hash)
        for value in (self.baseline_fingerprint, self.approval_record_hash,
                      self.reviewer_result_hash, self.disposition_set_hash,
                      self.activation_binding_hash):
            _require_sha256(value)
        for value in (self.approval_record_id, self.reviewer_result_id, self.ruleset_version):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("pointer binding identity is required")
        if not isinstance(self.semantic_asset_versions, tuple) or tuple(sorted(self.semantic_asset_versions)) != self.semantic_asset_versions:
            raise ValueError("pointer semantic assets must be canonical")
        if self.activation_binding_hash != _activation_binding_hash(self.binding_payload()):
            raise ValueError("pointer activation binding hash mismatch")

    def to_dict(self) -> dict[str, str | int]:
        return {
            "physical_key": self.physical_key,
            "contract_version": self.contract_version,
            "content_hash": self.content_hash,
            "baseline_fingerprint": self.baseline_fingerprint,
            "approval_record_id": self.approval_record_id,
            "approval_record_hash": self.approval_record_hash,
            "reviewer_result_id": self.reviewer_result_id,
            "reviewer_result_hash": self.reviewer_result_hash,
            "ruleset_version": self.ruleset_version,
            "semantic_asset_versions": [list(item) for item in self.semantic_asset_versions],
            "disposition_set_hash": self.disposition_set_hash,
            "activation_binding_hash": self.activation_binding_hash,
        }

    def binding_payload(self) -> dict[str, object]:
        return {key: value for key, value in self.to_dict().items() if key != "activation_binding_hash"}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ContractPointer:
        if set(payload) != _POINTER_FIELDS:
            raise ValueError("pointer must contain exactly physical_key/contract_version/content_hash")
        return cls(
            physical_key=payload["physical_key"],
            contract_version=payload["contract_version"],
            content_hash=payload["content_hash"], baseline_fingerprint=payload["baseline_fingerprint"],
            approval_record_id=payload["approval_record_id"], approval_record_hash=payload["approval_record_hash"],
            reviewer_result_id=payload["reviewer_result_id"], reviewer_result_hash=payload["reviewer_result_hash"],
            ruleset_version=payload["ruleset_version"],
            semantic_asset_versions=tuple(tuple(item) for item in payload["semantic_asset_versions"]),
            disposition_set_hash=payload["disposition_set_hash"], activation_binding_hash=payload["activation_binding_hash"],
        )

    @classmethod
    def build(cls, *, physical_key: str, contract_version: int, content_hash: str,
              baseline_fingerprint: str, approval_record_id: str, approval_record_hash: str,
              reviewer_result_id: str, reviewer_result_hash: str, ruleset_version: str,
              semantic_asset_versions: tuple[tuple[str, str], ...], disposition_set_hash: str) -> "ContractPointer":
        payload = locals().copy(); payload.pop("cls")
        return cls(**payload, activation_binding_hash=_activation_binding_hash(payload))


class ContractLifecycleCoordinator:
    """Storage primitives for immutable candidates and the sole current pointer."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        self.memory_root = self.project_root / ".creative_os" / "memory"
        self.store = JsonMemoryStore(self.memory_root)
        self.pointers_dir = self.memory_root / "contracts" / "pointers"

    def create_initial_candidate(
        self,
        decision: NarrativeDecision,
        *,
        evidence: Iterable[MemoryEvidence],
    ) -> MemoryItem:
        if not isinstance(decision, NarrativeDecision):
            raise TypeError("create_initial_candidate requires NarrativeDecision")
        decision.validate()
        if decision.contract_version != 1:
            raise ContractStorageError("initial_contract_version_must_be_1")

        item_id = physical_key(decision.contract_id, decision.contract_version)
        canonical_content = NarrativeDecisionCodec.encode(decision)
        expected_hash = NarrativeDecisionCodec.content_hash(decision)
        try:
            existing = self.store.get_strict(item_id)
        except KeyError:
            existing = None
        except MemoryStoreError as error:
            raise ContractStorageError("invalid_contract_envelope") from error

        if existing is not None:
            return self._require_matching_initial_candidate(
                existing,
                decision=decision,
                canonical_content=canonical_content,
                expected_hash=expected_hash,
            )

        item = build_narrative_candidate_item(
            self.project_root,
            decision,
            evidence=evidence,
            item_id=item_id,
        )
        try:
            self.store.add_immutable(item)
        except ImmutableMemoryConflictError:
            try:
                stored = self.store.get_strict(item_id)
            except KeyError as error:
                raise ContractStorageError("immutable_contract_conflict") from error
            except MemoryStoreError as error:
                raise ContractStorageError("invalid_contract_envelope") from error
            return self._require_matching_initial_candidate(
                stored,
                decision=decision,
                canonical_content=canonical_content,
                expected_hash=expected_hash,
            )
        except MemoryStoreError as error:
            raise ContractStorageError("immutable_contract_conflict") from error
        try:
            stored = self.store.get_strict(item_id)
        except MemoryStoreError as error:
            raise ContractStorageError("invalid_contract_envelope") from error
        self._validate_contract_item(
            stored,
            expected_contract_id=decision.contract_id,
            expected_version=1,
            expected_status=MemoryStatus.CANDIDATE,
        )
        return stored

    def create_replacement_candidate(
        self,
        decision: NarrativeDecision,
        revision_request: ContractRevisionRequest,
        *,
        authority_causal_impact_paths: tuple[str, ...],
        authority_approved_change_requests: tuple[NarrativeChangeRequest, ...],
        evidence: Iterable[MemoryEvidence],
    ) -> MemoryItem:
        """Persist one immutable next-version candidate without changing current."""
        if not isinstance(decision, NarrativeDecision):
            raise TypeError("replacement requires NarrativeDecision")
        if not isinstance(revision_request, ContractRevisionRequest):
            raise TypeError("replacement requires ContractRevisionRequest")
        evidence = tuple(evidence)
        if any(not isinstance(item, MemoryEvidence) for item in evidence):
            raise TypeError("replacement evidence must contain MemoryEvidence values")
        with project_authority_lock(self.project_root):
            current = self.load_current(decision.contract_id)
            pointer = self.read_pointer(decision.contract_id)
            if current is None or pointer is None:
                raise ContractStorageError("missing_current_contract")
            revision_request.verify(
                current, decision,
                authority_causal_impact_paths=authority_causal_impact_paths,
                authority_approved_change_requests=authority_approved_change_requests,
            )
            if decision.contract_version != pointer.contract_version + 1:
                raise ContractStorageError("replacement_version_must_be_contiguous")
            required_approvals = ContractApprovalPolicy.required_revision_approvals(
                current, decision, revision_request,
                authority_causal_impact_paths=authority_causal_impact_paths,
                authority_approved_change_requests=authority_approved_change_requests,
            )
            prepare = {
                "schema_version": 1,
                "state": "prepared",
                "physical_key": physical_key(decision.contract_id, decision.contract_version),
                "contract_content_hash": NarrativeDecisionCodec.content_hash(decision),
                "revision_binding_hash": _activation_binding_hash({
                    "request": request_binding_payload(revision_request),
                    "causal": list(authority_causal_impact_paths),
                    "changes": [item.to_json() for item in authority_approved_change_requests],
                    "evidence": [asdict(item) for item in evidence],
                }),
            }
            self._write_revision_prepare(decision.contract_id, decision.contract_version, prepare)
            _revision_hook("after_prepare")
            self._write_revision_authority(
                decision, revision_request, authority_causal_impact_paths,
                authority_approved_change_requests, required_approvals,
            )
            self._write_revision_prepare(
                decision.contract_id, decision.contract_version,
                {**prepare, "state": "authority_written"},
            )
            _revision_hook("after_authority")
            item_id = physical_key(decision.contract_id, decision.contract_version)
            item = build_narrative_candidate_item(
                self.project_root, decision, evidence=evidence, item_id=item_id,
            )
            try:
                self.store.add_immutable(item)
            except ImmutableMemoryConflictError:
                existing = self.store.get_strict(item_id)
                if (
                    existing.content != item.content
                    or existing.status != MemoryStatus.CANDIDATE
                    or existing.evidence != item.evidence
                    or existing.kind != item.kind
                    or existing.scope != item.scope
                    or existing.scope_id != item.scope_id
                ):
                    raise ContractStorageError("immutable_contract_conflict")
                stored = existing
            else:
                stored = self.store.get_strict(item_id)
            self._write_revision_prepare(
                decision.contract_id, decision.contract_version,
                {**prepare, "state": "committed"},
            )
            _revision_hook("after_candidate")
            return stored

    def recover_replacement_candidate(self, decision: NarrativeDecision, revision_request: ContractRevisionRequest,
                                      **kwargs: object) -> MemoryItem:
        return self.create_replacement_candidate(decision, revision_request, **kwargs)  # type: ignore[arg-type]

    def list_contract_versions(self, contract_id: str) -> tuple[NarrativeDecision, ...]:
        _require_contract_id(contract_id)
        versions: list[NarrativeDecision] = []
        for item in self.store.list():
            if not item.id.startswith(contract_id + "-v"):
                continue
            _, version = _parse_physical_key(item.id)
            versions.append(self._validate_contract_item(
                item, expected_contract_id=contract_id, expected_version=version,
                expected_status=item.status,
            ))
        ordered = tuple(sorted(versions, key=lambda decision: decision.contract_version))
        if ordered and tuple(item.contract_version for item in ordered) != tuple(
            range(ordered[0].contract_version, ordered[-1].contract_version + 1)
        ):
            raise ContractStorageError("contract_version_history_gap")
        return ordered

    def switch_replacement(
        self,
        contract_id: str,
        replacement_version: int,
        replacement_hash: str,
        baseline_fingerprint: str,
        *,
        expected_pointer: ContractPointer,
        resolver: BaselineSourceResolver,
        actor: str,
        ruleset_version: str,
    ) -> ContractPointer:
        """CAS switch with old ACTIVE retained until the new pointer is durable."""
        with project_authority_lock(self.project_root):
            revision_authority = self._read_revision_authority(
                contract_id, replacement_version, replacement_hash,
            )
            if revision_authority["replacement_baseline_fingerprint"] != baseline_fingerprint:
                raise ContractStorageError("replacement_baseline_binding_mismatch")
            if (
                revision_authority["base_contract_version"] != expected_pointer.contract_version
                or revision_authority["base_contract_content_hash"] != expected_pointer.content_hash
                or revision_authority["base_baseline_fingerprint"] != expected_pointer.baseline_fingerprint
            ):
                raise ContractStorageError("replacement_base_binding_mismatch")
            current_pointer = self.read_pointer(contract_id)
            journal = self._read_switch_journal(contract_id, replacement_version)
            if journal is None:
                if current_pointer != expected_pointer:
                    raise ContractStorageError("contract_switch_conflict")
                if replacement_version != expected_pointer.contract_version + 1:
                    raise ContractStorageError("replacement_version_must_be_contiguous")
                new_pointer = self._prepare_replacement_pointer_locked(
                    contract_id, replacement_version, replacement_hash, baseline_fingerprint,
                    resolver=resolver, actor=actor, ruleset_version=ruleset_version,
                    required_approvals=tuple(revision_authority["required_approvals"]),
                )
                journal = {
                    "schema_version": 1, "state": "prepared", "actor": actor,
                    "old_pointer": expected_pointer.to_dict(), "new_pointer": new_pointer.to_dict(),
                }
                self._write_switch_journal(contract_id, replacement_version, journal)
                _switch_hook("after_prepare")
            else:
                if ContractPointer.from_dict(journal["old_pointer"]) != expected_pointer:
                    raise ContractStorageError("contract_switch_conflict")
                new_pointer = ContractPointer.from_dict(journal["new_pointer"])
                if (new_pointer.contract_version, new_pointer.content_hash) != (replacement_version, replacement_hash):
                    raise ContractStorageError("contract_switch_conflict")
                verified = self._prepare_replacement_pointer_locked(
                    contract_id, replacement_version, replacement_hash, baseline_fingerprint,
                    resolver=resolver, actor=actor, ruleset_version=ruleset_version,
                    required_approvals=tuple(revision_authority["required_approvals"]),
                )
                if verified != new_pointer:
                    raise ContractStorageError("replacement_authority_drift")
            return self._advance_switch_locked(
                contract_id, replacement_version, journal, expected_pointer, new_pointer, actor,
            )

    def recover_switch(self, contract_id: str, **kwargs: object) -> ContractPointer:
        return self.switch_replacement(contract_id, **kwargs)  # type: ignore[arg-type]

    def _require_matching_initial_candidate(
        self,
        stored: MemoryItem,
        *,
        decision: NarrativeDecision,
        canonical_content: str,
        expected_hash: str,
    ) -> MemoryItem:
        stored_decision = self._validate_contract_item(
            stored,
            expected_contract_id=decision.contract_id,
            expected_version=1,
            expected_status=MemoryStatus.CANDIDATE,
        )
        if (
            stored.content != canonical_content
            or NarrativeDecisionCodec.content_hash(stored_decision) != expected_hash
        ):
            raise ContractStorageError("immutable_contract_conflict")
        return stored

    def read_pointer(self, contract: str | int) -> ContractPointer | None:
        contract_id = _normalize_contract_id(contract)
        path = self._pointer_path(contract_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("pointer root must be an object")
            pointer = ContractPointer.from_dict(payload)
            pointer_contract_id, _ = _parse_physical_key(pointer.physical_key)
            if pointer_contract_id != contract_id:
                raise ValueError("pointer contract_id mismatch")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ContractStorageError("invalid_contract_pointer") from error

        self._load_pointer_target(contract_id, pointer)
        return pointer

    def load_current(self, contract: str | int) -> NarrativeDecision | None:
        contract_id = _normalize_contract_id(contract)
        pointer = self.read_pointer(contract_id)
        if pointer is None:
            return None
        return self._load_pointer_target(contract_id, pointer)

    def write_pointer(self, pointer: ContractPointer) -> None:
        if not isinstance(pointer, ContractPointer):
            raise TypeError("write_pointer requires ContractPointer")
        contract_id, _ = _parse_physical_key(pointer.physical_key)
        self._load_pointer_target(contract_id, pointer)

        path = self._pointer_path(contract_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(pointer.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def activate_initial(
        self,
        contract_id: str,
        contract_version: int,
        contract_hash: str,
        baseline_fingerprint: str,
        *,
        resolver: BaselineSourceResolver,
        actor: str,
        ruleset_version: str,
    ) -> ContractPointer:
        """Activate only after exact authority and baseline re-read succeed."""
        if contract_version != 1:
            raise ContractStorageError("initial_contract_version_must_be_1")
        records = ContractRecordStore(self.project_root)
        with project_authority_lock(self.project_root):
            exact = records.find_exact(
                contract_id=contract_id,
                contract_version=contract_version,
                contract_hash=contract_hash,
                baseline_fingerprint=baseline_fingerprint,
                ruleset_version=ruleset_version,
            )
            if exact is None:
                raise ContractStorageError("missing_exact_contract_records")
            if exact.reviewer_result is None:
                raise ContractStorageError("missing_prewrite_review")
            if exact.approval.full_contract.status != ApprovalStatus.APPROVED or any(
                item.status not in {ApprovalStatus.APPROVED, ApprovalStatus.NOT_APPLICABLE}
                for _, item in exact.approval.approvals
            ):
                raise ContractStorageError("contract_not_approved")
            if actor != exact.approval.full_contract.approved_by:
                raise ContractStorageError("activation_actor_mismatch")
            gate = validate_reviewer_gate(
                exact.reviewer_result,
                exact.dispositions,
                contract_id=contract_id,
                contract_version=contract_version,
                contract_content_hash=contract_hash,
                baseline_fingerprint=baseline_fingerprint,
                ruleset_version=ruleset_version,
                semantic_asset_versions=exact.reviewer_result.semantic_asset_versions,
            )
            if not gate.is_ready:
                raise ContractStorageError("reviewer_gate_blocked")
            try:
                authority = resolver.resolve_manifest(self.project_root, exact.baseline.entries)
            except ResolverError as error:
                raise ContractStorageError(error.issue.code) from error
            item = self.store.get_strict(physical_key(contract_id, contract_version))
            if item.status not in {MemoryStatus.CANDIDATE, MemoryStatus.ACTIVE}:
                raise ContractStorageError("invalid_contract_envelope_status")
            decision = self._validate_contract_item(item, expected_contract_id=contract_id,
                expected_version=contract_version, expected_status=item.status)
            if NarrativeDecisionCodec.content_hash(decision) != contract_hash:
                raise ContractStorageError("contract_hash_mismatch")
            causal = CausalDependencyAnalyzer().analyze(
                decision, authority.profile, authority.fact_snapshots,
                authority.previous_chapter, authority.change_requests,
            )
            preflight = ContractPreflightValidator().validate(decision, authority.evidence_resolver, causal)
            if not causal.is_resolved or not preflight.is_ready:
                raise ContractStorageError("contract_preflight_blocked")
            disposition_set_hash = _activation_binding_hash({
                "dispositions": [
                    [record_id, authoritative_record_hash(record)]
                    for record_id, record in sorted(exact.disposition_records)
                ]
            })
            pointer = ContractPointer.build(
                physical_key=physical_key(contract_id, contract_version),
                contract_version=contract_version, content_hash=contract_hash,
                baseline_fingerprint=baseline_fingerprint,
                approval_record_id=exact.approval_record_id,
                approval_record_hash=authoritative_record_hash(exact.approval),
                reviewer_result_id=exact.reviewer_record_id,
                reviewer_result_hash=exact.reviewer_result.result_hash,
                ruleset_version=ruleset_version,
                semantic_asset_versions=exact.reviewer_result.semantic_asset_versions,
                disposition_set_hash=disposition_set_hash,
            )
            existing_pointer = self.read_pointer(contract_id)
            if existing_pointer is not None and existing_pointer != pointer:
                raise ContractStorageError("initial_pointer_conflict")
            if item.status == MemoryStatus.CANDIDATE:
                self.store.replace(item.activate(actor=actor))
            self.write_pointer(pointer)
            return pointer

    def recover_initial(self, contract_id: str, **kwargs: object) -> ContractPointer:
        return self.activate_initial(contract_id, **kwargs)  # type: ignore[arg-type]

    def _prepare_replacement_pointer_locked(
        self, contract_id: str, version: int, contract_hash: str, baseline_fingerprint: str,
        *, resolver: BaselineSourceResolver, actor: str, ruleset_version: str,
        required_approvals: tuple[str, ...],
    ) -> ContractPointer:
        records = ContractRecordStore(self.project_root)
        exact = records.find_exact(
            contract_id=contract_id, contract_version=version, contract_hash=contract_hash,
            baseline_fingerprint=baseline_fingerprint, ruleset_version=ruleset_version,
        )
        if exact is None or exact.reviewer_result is None:
            raise ContractStorageError("missing_exact_contract_records")
        if exact.approval.full_contract.status != ApprovalStatus.APPROVED or any(
            item.status not in {ApprovalStatus.APPROVED, ApprovalStatus.NOT_APPLICABLE}
            for _, item in exact.approval.approvals
        ):
            raise ContractStorageError("contract_not_approved")
        if any(exact.approval.item(name).status != ApprovalStatus.APPROVED for name in required_approvals):
            raise ContractStorageError("missing_required_revision_approval")
        if actor != exact.approval.full_contract.approved_by:
            raise ContractStorageError("activation_actor_mismatch")
        gate = validate_reviewer_gate(
            exact.reviewer_result, exact.dispositions, contract_id=contract_id,
            contract_version=version, contract_content_hash=contract_hash,
            baseline_fingerprint=baseline_fingerprint, ruleset_version=ruleset_version,
            semantic_asset_versions=exact.reviewer_result.semantic_asset_versions,
        )
        if not gate.is_ready:
            raise ContractStorageError("reviewer_gate_blocked")
        try:
            authority = resolver.resolve_manifest(self.project_root, exact.baseline.entries)
        except ResolverError as error:
            raise ContractStorageError(error.issue.code) from error
        item = self.store.get_strict(physical_key(contract_id, version))
        if item.status not in {MemoryStatus.CANDIDATE, MemoryStatus.ACTIVE}:
            raise ContractStorageError("invalid_replacement_status")
        decision = self._validate_contract_item(
            item, expected_contract_id=contract_id, expected_version=version,
            expected_status=item.status,
        )
        if NarrativeDecisionCodec.content_hash(decision) != contract_hash:
            raise ContractStorageError("contract_hash_mismatch")
        causal = CausalDependencyAnalyzer().analyze(
            decision, authority.profile, authority.fact_snapshots,
            authority.previous_chapter, authority.change_requests,
        )
        preflight = ContractPreflightValidator().validate(
            decision, authority.evidence_resolver, causal,
        )
        if not causal.is_resolved or not preflight.is_ready:
            raise ContractStorageError("contract_preflight_blocked")
        disposition_set_hash = _activation_binding_hash({
            "dispositions": [
                [record_id, authoritative_record_hash(record)]
                for record_id, record in sorted(exact.disposition_records)
            ]
        })
        return ContractPointer.build(
            physical_key=physical_key(contract_id, version), contract_version=version,
            content_hash=contract_hash, baseline_fingerprint=baseline_fingerprint,
            approval_record_id=exact.approval_record_id,
            approval_record_hash=authoritative_record_hash(exact.approval),
            reviewer_result_id=exact.reviewer_record_id,
            reviewer_result_hash=exact.reviewer_result.result_hash,
            ruleset_version=ruleset_version,
            semantic_asset_versions=exact.reviewer_result.semantic_asset_versions,
            disposition_set_hash=disposition_set_hash,
        )

    def _advance_switch_locked(
        self, contract_id: str, replacement_version: int, journal: dict[str, object], old_pointer: ContractPointer,
        new_pointer: ContractPointer, actor: str,
    ) -> ContractPointer:
        new_item = self.store.get_strict(new_pointer.physical_key)
        old_item = self.store.get_strict(old_pointer.physical_key)
        if new_item.status == MemoryStatus.CANDIDATE:
            self.store.replace(new_item.activate(actor=actor))
            journal = {**journal, "state": "new_active"}
            self._write_switch_journal(contract_id, replacement_version, journal)
            _switch_hook("after_new_active")
        elif new_item.status != MemoryStatus.ACTIVE:
            raise ContractStorageError("invalid_replacement_status")
        current = self.read_pointer(contract_id)
        if current == old_pointer:
            self.write_pointer(new_pointer)
            journal = {**journal, "state": "pointer_switched"}
            self._write_switch_journal(contract_id, replacement_version, journal)
            _switch_hook("after_pointer")
        elif current != new_pointer:
            raise ContractStorageError("contract_switch_conflict")
        new_item = self.store.get_strict(new_pointer.physical_key)
        if new_item.status != MemoryStatus.ACTIVE or self.read_pointer(contract_id) != new_pointer:
            raise ContractStorageError("replacement_not_safely_current")
        old_item = self.store.get_strict(old_pointer.physical_key)
        if old_item.status == MemoryStatus.ACTIVE:
            self.store.replace(old_item.archive(actor=actor))
            journal = {**journal, "state": "old_archived"}
            self._write_switch_journal(contract_id, replacement_version, journal)
            _switch_hook("after_old_archive")
        elif old_item.status != MemoryStatus.ARCHIVED:
            raise ContractStorageError("invalid_old_contract_status")
        if journal["state"] != "committed":
            journal = {**journal, "state": "committed"}
            self._write_switch_journal(contract_id, replacement_version, journal)
            _switch_hook("after_commit")
        if self.read_pointer(contract_id) != new_pointer:
            raise ContractStorageError("invalid_contract_switch_journal")
        return new_pointer

    def _switch_journal_path(self, contract_id: str, replacement_version: int) -> Path:
        _require_contract_id(contract_id)
        _require_contract_version(replacement_version)
        return self.memory_root / "contracts" / "switches" / f"{contract_id}-v{replacement_version:04d}.json"

    def _read_switch_journal(self, contract_id: str, replacement_version: int) -> dict[str, object] | None:
        path = self._switch_journal_path(contract_id, replacement_version)
        if not path.exists():
            return None
        try:
            raw = path.read_bytes()
            envelope = _strict_canonical_json(raw)
            if set(envelope) != {"payload", "entry_hash"}:
                raise ValueError("invalid envelope")
            value = envelope["payload"]
            if envelope["entry_hash"] != _activation_binding_hash(value):
                raise ValueError("switch journal hash mismatch")
            if raw != _canonical_bytes(envelope):
                raise ValueError("switch journal is not canonical")
            if set(value) != {"schema_version", "state", "actor", "old_pointer", "new_pointer"}:
                raise ValueError("invalid fields")
            if value["schema_version"] != 1 or value["state"] not in {
                "prepared", "new_active", "pointer_switched", "old_archived", "committed",
            }:
                raise ValueError("invalid switch state")
            old_pointer = ContractPointer.from_dict(value["old_pointer"])
            new_pointer = ContractPointer.from_dict(value["new_pointer"])
            if new_pointer.contract_version != replacement_version:
                raise ValueError("switch journal filename binding mismatch")
            if old_pointer.contract_version + 1 != new_pointer.contract_version:
                raise ValueError("switch journal version binding mismatch")
            return value
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise ContractStorageError("invalid_contract_switch_journal") from error

    def _write_switch_journal(
        self, contract_id: str, replacement_version: int, value: dict[str, object],
    ) -> None:
        path = self._switch_journal_path(contract_id, replacement_version)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        envelope = {"payload": value, "entry_hash": _activation_binding_hash(value)}
        with temporary.open("wb") as stream:
            stream.write(_canonical_bytes(envelope))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def _revision_authority_path(self, contract_id: str, version: int) -> Path:
        return self.memory_root / "contracts" / "revisions" / f"{physical_key(contract_id, version)}.json"

    def _write_revision_authority(
        self, decision: NarrativeDecision, request: ContractRevisionRequest,
        causal_paths: tuple[str, ...], change_requests: tuple[NarrativeChangeRequest, ...],
        required_approvals: tuple[str, ...],
    ) -> None:
        payload = {
            "schema_version": 1,
            "contract_id": decision.contract_id,
            "replacement_contract_version": decision.contract_version,
            "replacement_contract_content_hash": NarrativeDecisionCodec.content_hash(decision),
            "base_contract_version": request.base_contract_version,
            "base_contract_content_hash": request.base_contract_content_hash,
            "base_baseline_fingerprint": request.base_baseline_fingerprint,
            "replacement_baseline_fingerprint": request.replacement_baseline_fingerprint,
            "revision_binding_hash": _activation_binding_hash({
                "leaf_changes": [
                    [change.field_path, change.old_present, str(change.old_value),
                     change.new_present, str(change.new_value)]
                    for change in request.leaf_changes
                ],
                "causal_impact_paths": list(causal_paths),
                "approved_change_requests": [item.to_json() for item in change_requests],
            }),
            "required_approvals": list(required_approvals),
        }
        envelope = {"payload": payload, "entry_hash": _activation_binding_hash(payload)}
        raw = _canonical_bytes(envelope)
        path = self._revision_authority_path(decision.contract_id, decision.contract_version)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != raw:
                raise ContractStorageError("immutable_revision_authority_conflict")
            return
        temporary = path.with_suffix(".tmp")
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try: os.fsync(descriptor)
            finally: os.close(descriptor)

    def _read_revision_authority(
        self, contract_id: str, version: int, contract_hash: str,
    ) -> dict[str, object]:
        path = self._revision_authority_path(contract_id, version)
        try:
            raw = path.read_bytes()
            envelope = _strict_canonical_json(raw)
            if raw != _canonical_bytes(envelope) or set(envelope) != {"payload", "entry_hash"}:
                raise ValueError("non-canonical authority")
            payload = envelope["payload"]
            if envelope["entry_hash"] != _activation_binding_hash(payload):
                raise ValueError("authority hash mismatch")
            if set(payload) != {
                "schema_version", "contract_id", "replacement_contract_version",
                "replacement_contract_content_hash", "base_contract_version",
                "base_contract_content_hash", "base_baseline_fingerprint",
                "replacement_baseline_fingerprint", "revision_binding_hash",
                "required_approvals",
            } or type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
                raise ValueError("invalid revision authority schema")
            for name in (
                "contract_id",
            ):
                if not isinstance(payload[name], str) or not payload[name]:
                    raise ValueError("invalid revision authority field")
            for name in (
                "replacement_contract_content_hash", "base_contract_content_hash",
                "base_baseline_fingerprint", "replacement_baseline_fingerprint", "revision_binding_hash",
            ):
                _require_sha256(payload[name])
            if (
                type(payload["replacement_contract_version"]) is not int
                or type(payload["base_contract_version"]) is not int
                or payload["base_contract_version"] < 1
                or payload["replacement_contract_version"] != payload["base_contract_version"] + 1
            ):
                raise ValueError("invalid revision authority version")
            approvals = payload["required_approvals"]
            from creative_os.domains.contract_approval import APPROVAL_ITEMS
            if (
                not isinstance(approvals, list)
                or any(not isinstance(name, str) or name not in APPROVAL_ITEMS for name in approvals)
                or approvals != [name for name in APPROVAL_ITEMS if name in approvals]
                or len(set(approvals)) != len(approvals)
                or "full_contract" not in approvals
                or "post_freeze_revision" not in approvals
            ):
                raise ValueError("invalid required revision approvals")
            if (
                payload["contract_id"] != contract_id
                or payload["replacement_contract_version"] != version
                or payload["replacement_contract_content_hash"] != contract_hash
            ):
                raise ValueError("authority binding mismatch")
            return payload
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ContractStorageError("invalid_revision_authority") from error

    def _write_revision_prepare(self, contract_id: str, version: int, payload: dict[str, object]) -> None:
        path = self.memory_root / "contracts" / "revisions" / f".{physical_key(contract_id, version)}.prepare.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                raw = path.read_bytes()
                existing_envelope = _strict_canonical_json(raw)
                if set(existing_envelope) != {"payload", "entry_hash"}:
                    raise ValueError("invalid prepare envelope")
                existing = existing_envelope["payload"]
                if (
                    not isinstance(existing, dict)
                    or set(existing) != {
                        "schema_version", "state", "physical_key",
                        "contract_content_hash", "revision_binding_hash",
                    }
                    or type(existing["schema_version"]) is not int
                    or existing["schema_version"] != 1
                    or existing["state"] not in {"prepared", "authority_written", "committed"}
                    or existing["physical_key"] != physical_key(contract_id, version)
                    or raw != _canonical_bytes(existing_envelope)
                    or existing_envelope["entry_hash"] != _activation_binding_hash(existing)
                ):
                    raise ValueError("invalid prepare journal")
                _require_sha256(existing["contract_content_hash"])
                _require_sha256(existing["revision_binding_hash"])
                binding_fields = ("physical_key", "contract_content_hash", "revision_binding_hash")
                if any(existing[name] != payload[name] for name in binding_fields):
                    raise ContractStorageError("revision_prepare_conflict")
                if existing["state"] == "committed":
                    return
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ContractStorageError("invalid_revision_prepare_journal") from error
        envelope = {"payload": payload, "entry_hash": _activation_binding_hash(payload)}
        temporary = path.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            stream.write(_canonical_bytes(envelope)); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try: os.fsync(descriptor)
            finally: os.close(descriptor)

    def _load_pointer_target(
        self,
        contract_id: str,
        pointer: ContractPointer,
    ) -> NarrativeDecision:
        try:
            item = self.store.get_strict(pointer.physical_key)
        except KeyError as error:
            raise ContractStorageError("missing_contract_pointer_target") from error
        except MemoryStoreError as error:
            raise ContractStorageError("invalid_contract_envelope") from error
        if item.status != MemoryStatus.ACTIVE:
            raise ContractStorageError("contract_pointer_target_not_active")
        decision = self._validate_contract_item(
            item,
            expected_contract_id=contract_id,
            expected_version=pointer.contract_version,
            expected_status=MemoryStatus.ACTIVE,
        )
        if NarrativeDecisionCodec.content_hash(decision) != pointer.content_hash:
            raise ContractStorageError("contract_pointer_hash_mismatch")
        return decision

    def _validate_contract_item(
        self,
        item: MemoryItem,
        *,
        expected_contract_id: str,
        expected_version: int,
        expected_status: MemoryStatus,
    ) -> NarrativeDecision:
        if item.version != 1:
            raise ContractStorageError("invalid_contract_envelope_version")
        if item.status != expected_status:
            raise ContractStorageError("invalid_contract_envelope_status")
        if (
            item.kind != MemoryKind.PROJECT_DECISION
            or item.scope != MemoryScope.PROJECT
            or item.scope_id != self.project_root.name
        ):
            raise ContractStorageError("invalid_contract_envelope")
        try:
            decision = NarrativeDecisionCodec.decode(item.content)
        except Exception as error:
            raise ContractStorageError("invalid_contract_content") from error
        if item.content != NarrativeDecisionCodec.encode(decision):
            raise ContractStorageError("invalid_contract_content")
        if decision.contract_id != expected_contract_id:
            raise ContractStorageError("contract_pointer_contract_id_mismatch")
        if decision.contract_version != expected_version:
            raise ContractStorageError("contract_pointer_version_mismatch")
        if item.id != physical_key(decision.contract_id, decision.contract_version):
            raise ContractStorageError("contract_physical_key_mismatch")
        return decision

    def _pointer_path(self, contract_id: str) -> Path:
        match = _CONTRACT_ID_PATTERN.fullmatch(contract_id)
        assert match is not None
        return self.pointers_dir / f"contract-current-{match.group(1)}.json"


def create_initial_candidate(
    project_root: str | Path,
    decision: NarrativeDecision,
    *,
    evidence: Iterable[MemoryEvidence],
) -> MemoryItem:
    return ContractLifecycleCoordinator(project_root).create_initial_candidate(decision, evidence=evidence)


def read_pointer(project_root: str | Path, contract: str | int) -> ContractPointer | None:
    return ContractLifecycleCoordinator(project_root).read_pointer(contract)


def load_current(project_root: str | Path, contract: str | int) -> NarrativeDecision | None:
    return ContractLifecycleCoordinator(project_root).load_current(contract)


def _normalize_contract_id(contract: str | int) -> str:
    if type(contract) is int:
        if not 1 <= contract <= 999:
            raise ValueError("chapter number must be between 1 and 999")
        return f"narrative-chapter-{contract:03d}"
    _require_contract_id(contract)
    return contract


def _require_contract_id(value: object) -> str:
    if not isinstance(value, str) or _CONTRACT_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("contract_id must be narrative-chapter-NNN")
    return value


def _require_contract_version(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 9999:
        raise ValueError("contract_version must be an integer between 1 and 9999")
    return value


def _require_sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("content_hash must be a lowercase sha256")
    return value


def _parse_physical_key(value: object) -> tuple[str, int]:
    if not isinstance(value, str):
        raise ValueError("physical_key must be text")
    match = _PHYSICAL_KEY_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("physical_key must be narrative-chapter-NNN-vMMMM")
    contract_version = int(match.group(2))
    _require_contract_version(contract_version)
    return match.group(1), contract_version


def _activation_binding_hash(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _strict_canonical_json(raw: bytes) -> dict[str, object]:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _switch_hook(stage: str) -> None:
    del stage


def _revision_hook(stage: str) -> None:
    del stage


def request_binding_payload(request: ContractRevisionRequest) -> dict[str, object]:
    return asdict(request)
