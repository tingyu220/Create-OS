from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re
from typing import Callable, Iterable

from creative_os.domains.narrative_evidence import EvidenceRef, EvidenceRole
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import NarrativeDecision
from creative_os.domains.narrative_causality import CAUSAL_FIELD_PATHS_V1


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


def _sha256(value: object, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be a lowercase sha256")


@dataclass(frozen=True, slots=True)
class ContractFulfillmentEvidenceRecord:
    record_id: str
    contract_id: str
    contract_version: int
    contract_content_hash: str
    field_path: str
    evidence: EvidenceRef
    recorded_at: str
    supersedes_record_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or _ID.fullmatch(self.record_id) is None:
            raise ValueError("record_id is invalid")
        _text(self.contract_id, "contract_id")
        if type(self.contract_version) is not int or self.contract_version < 1:
            raise ValueError("contract_version must be a positive integer")
        _sha256(self.contract_content_hash, "contract_content_hash")
        _text(self.field_path, "field_path")
        if not isinstance(self.evidence, EvidenceRef) or self.evidence.is_legacy_replay_ref:
            raise ValueError("evidence must be a contract EvidenceRef")
        self.evidence.validate()
        _sha256(self.evidence.source_content_hash, "source_content_hash")
        if self.evidence.role not in {EvidenceRole.VERIFICATION, EvidenceRole.REALIZATION}:
            raise ValueError("fulfillment evidence role must be verification or realization")
        if (
            self.evidence.contract_id != self.contract_id
            or self.evidence.contract_version != self.contract_version
            or self.evidence.field_path != self.field_path
        ):
            raise ValueError("evidence contract/version/field_path binding mismatch")
        try:
            timestamp = datetime.fromisoformat(self.recorded_at)
        except (TypeError, ValueError) as error:
            raise ValueError("recorded_at must be an ISO timestamp") from error
        if timestamp.tzinfo is None:
            raise ValueError("recorded_at must include timezone")
        if self.supersedes_record_id is not None:
            if _ID.fullmatch(self.supersedes_record_id) is None:
                raise ValueError("supersedes_record_id is invalid")
            if self.supersedes_record_id == self.record_id:
                raise ValueError("record cannot supersede itself")


class FulfillmentStatus(StrEnum):
    FULFILLED = "fulfilled"
    INCOMPLETE = "incomplete"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class FulfillmentArtifactMetadata:
    chapter_id: str
    target_chinese_chars: int
    source_id: str
    source_version: str
    source_content_hash: str

    def __post_init__(self) -> None:
        _text(self.chapter_id, "chapter_id")
        if type(self.target_chinese_chars) is not int or self.target_chinese_chars < 1:
            raise ValueError("target_chinese_chars must be positive")
        _text(self.source_id, "source_id")
        _text(self.source_version, "source_version")
        _sha256(self.source_content_hash, "source_content_hash")


@dataclass(frozen=True, slots=True)
class FieldFulfillmentResult:
    field_path: str
    required_roles: tuple[EvidenceRole, ...]
    satisfied_roles: tuple[EvidenceRole, ...]
    missing_roles: tuple[EvidenceRole, ...]
    record_ids: tuple[str, ...]
    metadata_realized: bool = False


@dataclass(frozen=True, slots=True)
class ContractFulfillmentResult:
    contract_id: str
    contract_version: int
    contract_content_hash: str
    status: FulfillmentStatus
    fields: tuple[FieldFulfillmentResult, ...]
    stale_record_ids: tuple[str, ...] = ()

    def field(self, field_path: str) -> FieldFulfillmentResult:
        for result in self.fields:
            if result.field_path == field_path:
                return result
        raise KeyError(field_path)


class ContractFulfillmentEvaluator:
    """Purely derives fulfillment without modifying the frozen contract or authority records."""

    _METADATA_PATHS = (
        "chapter_contract.chapter_id",
        "chapter_contract.target_chinese_chars",
    )

    def evaluate(
        self,
        contract: NarrativeDecision,
        active_records: Iterable[ContractFulfillmentEvidenceRecord],
        evidence_validator: Callable[[EvidenceRef, object], bool],
        artifact_metadata: FulfillmentArtifactMetadata,
    ) -> ContractFulfillmentResult:
        if not isinstance(contract, NarrativeDecision):
            raise TypeError("contract must be NarrativeDecision")
        contract.validate()
        if not callable(evidence_validator):
            raise TypeError("evidence_validator must be callable")
        if not isinstance(artifact_metadata, FulfillmentArtifactMetadata):
            raise TypeError("artifact_metadata must be FulfillmentArtifactMetadata")
        digest = NarrativeDecisionCodec.content_hash(contract)
        bindings = {binding.field_path: binding for binding in contract.chapter_contract.intent_evidence_bindings}
        required_fields = _fulfillment_fields(contract)
        records_by_path: dict[str, list[ContractFulfillmentEvidenceRecord]] = {}
        stale: list[str] = []
        for record in active_records:
            if not isinstance(record, ContractFulfillmentEvidenceRecord):
                raise TypeError("active_records must contain fulfillment records")
            if (
                record.contract_id != contract.contract_id
                or record.contract_version != contract.contract_version
                or record.contract_content_hash != digest
                or record.field_path not in required_fields and record.field_path not in self._METADATA_PATHS
            ):
                stale.append(record.record_id)
                continue
            expected_value = (required_fields[record.field_path][0]
                              if record.field_path in required_fields else
                              (contract.chapter_contract.chapter_id
                               if record.field_path.endswith("chapter_id")
                               else contract.chapter_contract.target_chinese_chars))
            try:
                valid = (_same_value(record.evidence.asserted_value, expected_value)
                         and evidence_validator(record.evidence, expected_value))
            except Exception:
                valid = False
            if valid is not True:
                stale.append(record.record_id)
                continue
            records_by_path.setdefault(record.field_path, []).append(record)

        fields: list[FieldFulfillmentResult] = []
        for path, (expected_value, non_applicable) in required_fields.items():
            binding = bindings.get(path)
            frozen_roles = set() if binding is None else {
                ref.role for ref in binding.evidence
                if _same_value(ref.asserted_value, expected_value)
            }
            required = ((EvidenceRole.INTENT, EvidenceRole.NON_APPLICABILITY, EvidenceRole.VERIFICATION)
                        if non_applicable else
                        (EvidenceRole.INTENT, EvidenceRole.VERIFICATION, EvidenceRole.REALIZATION))
            external = records_by_path.get(path, [])
            satisfied = set(frozen_roles) | {record.evidence.role for record in external}
            fields.append(_field_result(path, required, satisfied, external, False))

        metadata_values = {
            "chapter_contract.chapter_id": artifact_metadata.chapter_id,
            "chapter_contract.target_chinese_chars": artifact_metadata.target_chinese_chars,
        }
        metadata_matches = (
            artifact_metadata.chapter_id == contract.chapter_contract.chapter_id
            and artifact_metadata.target_chinese_chars == contract.chapter_contract.target_chinese_chars
        )
        for path in self._METADATA_PATHS:
            external = records_by_path.get(path, [])
            satisfied = {EvidenceRole.INTENT, *(record.evidence.role for record in external)}
            same_artifact_verification = any(
                record.evidence.role == EvidenceRole.VERIFICATION
                and record.evidence.source_id == artifact_metadata.source_id
                and record.evidence.source_version == artifact_metadata.source_version
                and record.evidence.source_content_hash == artifact_metadata.source_content_hash
                and _same_value(record.evidence.asserted_value, metadata_values[path])
                for record in external
            )
            realized = metadata_matches and same_artifact_verification
            if realized:
                satisfied.add(EvidenceRole.REALIZATION)
            fields.append(_field_result(
                path,
                (EvidenceRole.INTENT, EvidenceRole.VERIFICATION, EvidenceRole.REALIZATION),
                satisfied,
                external,
                realized,
            ))

        complete = all(not field.missing_roles for field in fields)
        status = (FulfillmentStatus.STALE if stale else
                  FulfillmentStatus.FULFILLED if complete else FulfillmentStatus.INCOMPLETE)
        return ContractFulfillmentResult(
            contract.contract_id, contract.contract_version, digest, status,
            tuple(sorted(fields, key=lambda item: item.field_path)), tuple(sorted(set(stale))),
        )


def _field_result(path, required, satisfied, records, metadata_realized):
    satisfied_roles = tuple(role for role in required if role in satisfied)
    missing = tuple(role for role in required if role not in satisfied)
    return FieldFulfillmentResult(
        path, required, satisfied_roles, missing,
        tuple(sorted(record.record_id for record in records)), metadata_realized,
    )


def _fulfillment_fields(contract: NarrativeDecision) -> dict[str, tuple[object, bool]]:
    fields: dict[str, tuple[object, bool]] = {}
    for stable in CAUSAL_FIELD_PATHS_V1:
        if stable.endswith("[*]"):
            parent = stable[:-3]
            values = _read_path(contract, parent)
            fields.update({f"{parent}[{index}]": (value, False) for index, value in enumerate(values)})
        else:
            value = _read_path(contract, stable)
            fields[stable] = (value.value if hasattr(value, "value") else value, False)
    for plan_path in (
        "chapter_contract.information.misdirect",
        "chapter_contract.foreshadow_actions",
        "chapter_contract.forbidden",
    ):
        plan = _read_path(contract, plan_path)
        if not plan.values:
            fields[f"{plan_path}.not_applicable_reason"] = (plan.not_applicable_reason, True)
    return dict(sorted(fields.items()))


def _read_path(value: object, path: str) -> object:
    current = value
    for segment in path.split("."):
        current = getattr(current, segment)
    return current


def _same_value(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right
