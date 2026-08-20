from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import NarrativeDecision
from creative_os.domains.narrative_memory import build_narrative_candidate_item
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
_POINTER_FIELDS = frozenset({"physical_key", "contract_version", "content_hash"})


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

    def __post_init__(self) -> None:
        contract_id, key_version = _parse_physical_key(self.physical_key)
        del contract_id
        _require_contract_version(self.contract_version)
        if key_version != self.contract_version:
            raise ValueError("physical_key contract_version mismatch")
        _require_sha256(self.content_hash)

    def to_dict(self) -> dict[str, str | int]:
        return {
            "physical_key": self.physical_key,
            "contract_version": self.contract_version,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ContractPointer:
        if set(payload) != _POINTER_FIELDS:
            raise ValueError("pointer must contain exactly physical_key/contract_version/content_hash")
        return cls(
            physical_key=payload["physical_key"],
            contract_version=payload["contract_version"],
            content_hash=payload["content_hash"],
        )


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
        canonical_content = NarrativeDecisionCodec.encode_v2(decision)
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
            decision = NarrativeDecisionCodec.decode_v2(item.content)
        except Exception as error:
            raise ContractStorageError("invalid_contract_content") from error
        if item.content != NarrativeDecisionCodec.encode_v2(decision):
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
