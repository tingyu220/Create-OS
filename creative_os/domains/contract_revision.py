from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from datetime import datetime
from enum import StrEnum
import hashlib
import re

from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import (
    NarrativeChangeRequest,
    NarrativeChangeStatus,
    NarrativeDecision,
)


_PATH = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?"
    r"(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?)*"
)
_MAJOR_PREFIXES = (
    "arc_phase", "arc_goal", "inherited_pressure", "future_pressures",
    "chapter_contract.functions", "chapter_contract.dramatic_question",
    "chapter_contract.protagonist_choice", "chapter_contract.reader_change",
    "chapter_contract.information", "chapter_contract.pressure_curve",
    "chapter_contract.foreshadow_actions", "chapter_contract.ending_shift",
    "chapter_contract.forbidden",
)
_MISSING = object()


class RevisionValidationError(ValueError):
    pass


class RunContinuationStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class WriterRunContinuationAuthorization:
    authorization_id: str
    run_id: str
    old_contract_id: str
    old_contract_version: int
    old_contract_hash: str
    actor: str
    reason: str
    created_at: str
    expires_at: str
    status: RunContinuationStatus = RunContinuationStatus.ACTIVE
    supersedes_authorization_id: str | None = None

    def __post_init__(self) -> None:
        for value, name in ((self.authorization_id, "authorization_id"), (self.run_id, "run_id"),
                            (self.old_contract_id, "old_contract_id"), (self.actor, "actor"),
                            (self.reason, "reason")):
            _text(value, name)
        if self.actor.strip().casefold() in {"system", "assistant", "ai", "model", "automation"}:
            raise RevisionValidationError("continuation authorization requires a human actor")
        if type(self.old_contract_version) is not int or self.old_contract_version < 1:
            raise RevisionValidationError("old contract version is invalid")
        _sha256(self.old_contract_hash, "old contract hash")
        if not isinstance(self.status, RunContinuationStatus):
            raise RevisionValidationError("continuation authorization status is invalid")
        try:
            created = datetime.fromisoformat(self.created_at)
            expires = datetime.fromisoformat(self.expires_at)
        except (TypeError, ValueError) as error:
            raise RevisionValidationError("continuation authorization timestamps are invalid") from error
        if created.tzinfo is None or expires.tzinfo is None or expires <= created:
            raise RevisionValidationError("continuation authorization expiry is invalid")
        if self.status == RunContinuationStatus.REVOKED and not self.supersedes_authorization_id:
            raise RevisionValidationError("revocation must supersede an active authorization")
        if self.status == RunContinuationStatus.ACTIVE and self.supersedes_authorization_id is not None:
            raise RevisionValidationError("active authorization cannot supersede another record")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RevisionValidationError(f"{name} is required")
    return value


def _sha256(value: object, name: str) -> str:
    text = _text(value, name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise RevisionValidationError(f"{name} must be a lowercase sha256")
    return text


@dataclass(frozen=True, slots=True)
class CanonicalLeafChange:
    field_path: str
    old_value: object
    new_value: object
    old_present: bool = True
    new_present: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.field_path, str) or _PATH.fullmatch(self.field_path) is None:
            raise RevisionValidationError("revision leaf path is invalid")
        if type(self.old_present) is not bool or type(self.new_present) is not bool:
            raise RevisionValidationError("revision leaf presence must be boolean")
        if not self.old_present and not self.new_present:
            raise RevisionValidationError("revision leaf must exist on one side")
        _validate_leaf(self.old_value, "old_value")
        _validate_leaf(self.new_value, "new_value")


@dataclass(frozen=True, slots=True)
class ApprovedChangeRequestReference:
    request_id: str
    request_content_hash: str
    covered_changed_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.request_id, "change request id")
        _sha256(self.request_content_hash, "change request content hash")
        _paths(self.covered_changed_paths, "covered changed paths")
        if not self.covered_changed_paths:
            raise RevisionValidationError("change request reference must cover a changed path")


@dataclass(frozen=True, slots=True)
class RequiredReviewerBinding:
    contract_id: str
    contract_version: int
    contract_content_hash: str
    baseline_fingerprint: str

    def __post_init__(self) -> None:
        _text(self.contract_id, "reviewer binding contract_id")
        if type(self.contract_version) is not int or self.contract_version < 1:
            raise RevisionValidationError("reviewer binding contract_version is invalid")
        _sha256(self.contract_content_hash, "reviewer binding contract hash")
        _sha256(self.baseline_fingerprint, "reviewer binding baseline fingerprint")


@dataclass(frozen=True, slots=True)
class ContractRevisionRequest:
    contract_id: str
    chapter_id: str
    base_contract_version: int
    base_contract_content_hash: str
    replacement_contract_version: int
    replacement_contract_content_hash: str
    base_baseline_fingerprint: str
    replacement_baseline_fingerprint: str
    leaf_changes: tuple[CanonicalLeafChange, ...]
    causal_impact_paths: tuple[str, ...]
    scene_impact: str
    approved_change_requests: tuple[ApprovedChangeRequestReference, ...]

    def __post_init__(self) -> None:
        _text(self.contract_id, "revision contract_id")
        _text(self.chapter_id, "revision chapter_id")
        if type(self.base_contract_version) is not int or self.base_contract_version < 1:
            raise RevisionValidationError("base contract version is invalid")
        if self.replacement_contract_version != self.base_contract_version + 1:
            raise RevisionValidationError("replacement contract version must equal base version + 1")
        _sha256(self.base_contract_content_hash, "base contract hash")
        _sha256(self.replacement_contract_content_hash, "replacement contract hash")
        _sha256(self.base_baseline_fingerprint, "base baseline fingerprint")
        _sha256(self.replacement_baseline_fingerprint, "replacement baseline fingerprint")
        if not isinstance(self.leaf_changes, tuple) or not self.leaf_changes:
            raise RevisionValidationError("revision must contain a canonical leaf diff")
        if any(not isinstance(change, CanonicalLeafChange) for change in self.leaf_changes):
            raise RevisionValidationError("leaf_changes contains an invalid change")
        paths = tuple(change.field_path for change in self.leaf_changes)
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise RevisionValidationError("leaf_changes must be sorted and unique")
        _paths(self.causal_impact_paths, "causal impact paths")
        _text(self.scene_impact, "scene impact")
        if not isinstance(self.approved_change_requests, tuple) or any(
            not isinstance(reference, ApprovedChangeRequestReference)
            for reference in self.approved_change_requests
        ):
            raise RevisionValidationError("approved change requests must be exact references")
        request_ids = tuple(reference.request_id for reference in self.approved_change_requests)
        if len(set(request_ids)) != len(request_ids):
            raise RevisionValidationError("approved change request ids must be unique")

    @property
    def changed_field_paths(self) -> tuple[str, ...]:
        return tuple(change.field_path for change in self.leaf_changes)

    @property
    def requires_new_reviewer(self) -> bool:
        return self.base_baseline_fingerprint != self.replacement_baseline_fingerprint

    @property
    def required_reviewer_binding(self) -> RequiredReviewerBinding | None:
        if not self.requires_new_reviewer:
            return None
        return RequiredReviewerBinding(
            self.contract_id, self.replacement_contract_version,
            self.replacement_contract_content_hash, self.replacement_baseline_fingerprint,
        )

    def change(self, field_path: str) -> CanonicalLeafChange:
        for change in self.leaf_changes:
            if change.field_path == field_path:
                return change
        raise KeyError(field_path)

    @classmethod
    def build(
        cls,
        current: NarrativeDecision,
        replacement: NarrativeDecision,
        *,
        base_baseline_fingerprint: str,
        replacement_baseline_fingerprint: str,
        causal_impact_paths: tuple[str, ...],
        scene_impact: str,
        approved_change_requests: tuple[NarrativeChangeRequest, ...],
    ) -> "ContractRevisionRequest":
        if not isinstance(current, NarrativeDecision) or not isinstance(replacement, NarrativeDecision):
            raise TypeError("current and replacement must be NarrativeDecision values")
        if current.contract_id != replacement.contract_id or current.chapter != replacement.chapter:
            raise RevisionValidationError("replacement identity must match current contract")
        if replacement.contract_version != current.contract_version + 1:
            raise RevisionValidationError("replacement contract version must equal base version + 1")
        current.validate()
        replacement.validate()
        old_leaves = _leaves(current)
        new_leaves = _leaves(replacement)
        changes = tuple(
            CanonicalLeafChange(
                path,
                None if old_leaves.get(path, _MISSING) is _MISSING else old_leaves[path],
                None if new_leaves.get(path, _MISSING) is _MISSING else new_leaves[path],
                path in old_leaves,
                path in new_leaves,
            )
            for path in sorted(old_leaves.keys() | new_leaves.keys())
            if old_leaves.get(path, _MISSING) != new_leaves.get(path, _MISSING)
        )
        if not changes:
            raise RevisionValidationError("replacement must change at least one leaf")
        _paths(causal_impact_paths, "causal impact paths")
        canonical_paths = old_leaves.keys() | new_leaves.keys()
        if any(path not in canonical_paths for path in causal_impact_paths):
            raise RevisionValidationError("causal impact contains a non-canonical path")
        if not isinstance(approved_change_requests, tuple):
            raise TypeError("approved_change_requests must be a tuple")
        major_paths = tuple(change.field_path for change in changes if _major_path(change.field_path))
        references = list(_approved_references(changes, current.chapter, approved_change_requests))
        covered_major = {path for reference in references for path in reference.covered_changed_paths}
        if set(major_paths) - covered_major:
            raise RevisionValidationError("major revision requires an approved NarrativeChangeRequest exact binding")
        business_changed_paths = tuple(change.field_path for change in changes)
        if not set(business_changed_paths).issubset(causal_impact_paths):
            raise RevisionValidationError("causal impact paths must cover every changed leaf")
        return cls(
            current.contract_id,
            current.chapter_contract.chapter_id,
            current.contract_version,
            NarrativeDecisionCodec.content_hash(current),
            replacement.contract_version,
            NarrativeDecisionCodec.content_hash(replacement),
            base_baseline_fingerprint,
            replacement_baseline_fingerprint,
            changes,
            causal_impact_paths,
            scene_impact,
            tuple(sorted(references, key=lambda item: item.request_id)),
        )

    def verify(
        self,
        current: NarrativeDecision,
        replacement: NarrativeDecision,
        *,
        authority_causal_impact_paths: tuple[str, ...],
        authority_approved_change_requests: tuple[NarrativeChangeRequest, ...],
    ) -> None:
        """Recompute identity, hashes and canonical diff so public construction cannot shrink it."""
        if not isinstance(current, NarrativeDecision) or not isinstance(replacement, NarrativeDecision):
            raise TypeError("current and replacement must be NarrativeDecision values")
        current.validate()
        replacement.validate()
        old_leaves = _leaves(current)
        new_leaves = _leaves(replacement)
        expected_changes = tuple(
            CanonicalLeafChange(
                path,
                None if old_leaves.get(path, _MISSING) is _MISSING else old_leaves[path],
                None if new_leaves.get(path, _MISSING) is _MISSING else new_leaves[path],
                path in old_leaves, path in new_leaves,
            )
            for path in sorted(old_leaves.keys() | new_leaves.keys())
            if old_leaves.get(path, _MISSING) != new_leaves.get(path, _MISSING)
        )
        _paths(authority_causal_impact_paths, "authority causal impact paths")
        if any(path not in old_leaves and path not in new_leaves for path in authority_causal_impact_paths):
            raise RevisionValidationError("authority causal impact contains a non-canonical path")
        expected_references = _approved_references(
            expected_changes, current.chapter, authority_approved_change_requests,
        )
        major_paths = {change.field_path for change in expected_changes if _major_path(change.field_path)}
        covered_major = {
            path for reference in expected_references for path in reference.covered_changed_paths
        }
        if major_paths - covered_major:
            raise RevisionValidationError(
                "major revision requires an approved NarrativeChangeRequest exact binding"
            )
        if (
            self.contract_id != current.contract_id
            or self.chapter_id != current.chapter_contract.chapter_id
            or self.base_contract_version != current.contract_version
            or self.replacement_contract_version != replacement.contract_version
            or self.base_contract_content_hash != NarrativeDecisionCodec.content_hash(current)
            or self.replacement_contract_content_hash != NarrativeDecisionCodec.content_hash(replacement)
            or self.leaf_changes != expected_changes
            or self.causal_impact_paths != authority_causal_impact_paths
            or self.approved_change_requests != expected_references
        ):
            raise RevisionValidationError("revision request canonical binding mismatch")
        if not set(self.changed_field_paths).issubset(self.causal_impact_paths):
            raise RevisionValidationError("causal impact paths must cover every changed leaf")


def _validate_leaf(value: object, name: str) -> None:
    if value is None or type(value) in {str, int, bool, float} or isinstance(value, Enum):
        return
    raise RevisionValidationError(f"{name} must be an immutable scalar")


def _paths(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise RevisionValidationError(f"{name} must be a tuple")
    if any(not isinstance(path, str) or _PATH.fullmatch(path) is None for path in value):
        raise RevisionValidationError(f"{name} contains an invalid path")
    if tuple(sorted(value)) != value or len(set(value)) != len(value):
        raise RevisionValidationError(f"{name} must be sorted and unique")
    return value


def _leaves(value: object) -> dict[str, object]:
    result: dict[str, object] = {}

    def visit(current: object, path: str) -> None:
        if path in {
            "contract_version",
            "chapter_contract.intent_evidence_bindings",
            "legacy_unclassified_evidence",
        }:
            return
        if is_dataclass(current) and not isinstance(current, type):
            for field in fields(current):
                visit(getattr(current, field.name), f"{path}.{field.name}" if path else field.name)
        elif isinstance(current, tuple):
            for index, item in enumerate(current):
                visit(item, f"{path}[{index}]")
        else:
            _validate_leaf(current, path)
            result[path] = current

    visit(value, "")
    return result


def _major_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[")
               for prefix in _MAJOR_PREFIXES)


def _change_text(value: object, present: bool) -> str:
    return str(value) if present else "<missing>"


def _approved_references(
    changes: tuple[CanonicalLeafChange, ...],
    chapter: int,
    requests: tuple[NarrativeChangeRequest, ...],
) -> tuple[ApprovedChangeRequestReference, ...]:
    if not isinstance(requests, tuple):
        raise TypeError("approved change requests must be a tuple")
    major_paths = {change.field_path for change in changes if _major_path(change.field_path)}
    references: list[ApprovedChangeRequestReference] = []
    for request in requests:
        if not isinstance(request, NarrativeChangeRequest):
            raise TypeError("approved change requests contains an invalid request")
        request.validate()
        if request.status != NarrativeChangeStatus.APPROVED or chapter not in request.affected_chapters:
            continue
        covered = tuple(sorted(
            change.field_path for change in changes
            if change.field_path in major_paths
            and _change_text(change.old_value, change.old_present) == request.old_plan
            and _change_text(change.new_value, change.new_present) == request.new_plan
        ))
        if covered:
            references.append(ApprovedChangeRequestReference(
                request.id,
                hashlib.sha256(request.to_json().encode("utf-8")).hexdigest(),
                covered,
            ))
    return tuple(sorted(references, key=lambda item: item.request_id))
