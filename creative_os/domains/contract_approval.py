from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import StrEnum
from re import fullmatch

from creative_os.domains.contract_baseline import BaselineManifest
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import NarrativeDecision
from creative_os.domains.narrative_evidence import EvidenceRef, EvidenceRole


class ApprovalStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NOT_APPLICABLE = "not_applicable"


FULL_CONTRACT = "full_contract"
_BASELINE_FINGERPRINT_PATH = "BaselineManifest.fingerprint"
SPECIAL_APPROVAL_ITEMS = (
    "major_choice_and_cost",
    "information_reveal_and_misdirect",
    "foreshadow_payoff_or_close",
    "new_facts",
    "outline_change",
    "post_freeze_revision",
)
APPROVAL_ITEMS = (FULL_CONTRACT, *SPECIAL_APPROVAL_ITEMS)

_SYSTEM_ACTORS = frozenset({"system", "assistant", "ai", "model", "automation", "bot"})
_CONCRETE_FIELD_PATH = (
    r"[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?"
    r"(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?)*"
)
def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _require_sha256(value: object, name: str) -> str:
    text = _require_text(value, name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{name} must be a lowercase sha256")
    return text


def _require_human_actor(value: object) -> str:
    actor = _require_text(value, "approval approved_by")
    if actor.strip().casefold() in _SYSTEM_ACTORS:
        raise ValueError("approval approved_by must identify a human actor")
    return actor


def _require_timestamp(value: object) -> str:
    timestamp = _require_text(value, "approval approved_at")
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise ValueError("approval approved_at must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("approval approved_at must include a timezone")
    return timestamp


@dataclass(frozen=True, slots=True)
class ApprovalItem:
    """One human decision kept outside the frozen chapter contract."""

    status: ApprovalStatus
    reason: str
    approved_by: str
    approved_at: str
    decision_evidence: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, ApprovalStatus):
            raise TypeError("approval status must be an ApprovalStatus")
        _require_text(self.reason, "approval reason")
        _require_human_actor(self.approved_by)
        _require_timestamp(self.approved_at)
        if not isinstance(self.decision_evidence, tuple):
            raise TypeError("approval decision_evidence must be a tuple")
        for evidence in self.decision_evidence:
            if not isinstance(evidence, EvidenceRef) or evidence.is_legacy_replay_ref:
                raise ValueError("approval decision_evidence must contain field EvidenceRef values")
            evidence.validate()
            if evidence.role != EvidenceRole.DECISION:
                raise ValueError("approval evidence role must be decision")


@dataclass(frozen=True, slots=True)
class ContractApprovalRecord:
    """The complete external human approval projection for one contract version."""

    contract_id: str
    contract_version: int
    contract_content_hash: str
    baseline_manifest: BaselineManifest
    full_contract: ApprovalItem
    major_choice_and_cost: ApprovalItem
    information_reveal_and_misdirect: ApprovalItem
    foreshadow_payoff_or_close: ApprovalItem
    new_facts: ApprovalItem
    outline_change: ApprovalItem
    post_freeze_revision: ApprovalItem

    def __post_init__(self) -> None:
        _require_text(self.contract_id, "approval contract_id")
        if type(self.contract_version) is not int or self.contract_version < 1:
            raise ValueError("approval contract_version must be a positive integer")
        _require_sha256(self.contract_content_hash, "approval contract_content_hash")
        if not isinstance(self.baseline_manifest, BaselineManifest):
            raise TypeError("approval baseline_manifest must be a BaselineManifest")
        for name, item in self.approvals:
            if not isinstance(item, ApprovalItem):
                raise TypeError(f"approval {name} must be an ApprovalItem")
            for evidence in item.decision_evidence:
                if evidence.contract_id != self.contract_id or evidence.contract_version != self.contract_version:
                    raise ValueError(f"approval {name} decision evidence identity mismatch")
                _validate_decision_evidence_coverage(name, evidence.field_path)

        if self.full_contract.status == ApprovalStatus.NOT_APPLICABLE:
            raise ValueError("full_contract approval cannot be not_applicable")
        special_statuses = tuple(item.status for _, item in self.approvals[1:])
        if self.full_contract.status == ApprovalStatus.APPROVED and ApprovalStatus.REJECTED in special_statuses:
            raise ValueError("conflicting approval: full_contract approved while a special item is rejected")
        if self.full_contract.status == ApprovalStatus.REJECTED and ApprovalStatus.APPROVED in special_statuses:
            raise ValueError("conflicting approval: full_contract rejected while a special item is approved")

    @property
    def approvals(self) -> tuple[tuple[str, ApprovalItem], ...]:
        return tuple((name, getattr(self, name)) for name in APPROVAL_ITEMS)

    def item(self, name: str) -> ApprovalItem:
        if name not in APPROVAL_ITEMS:
            raise ValueError(f"unknown approval item: {name}")
        return getattr(self, name)


_COVERED_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (FULL_CONTRACT, ("NarrativeDecision.*", _BASELINE_FINGERPRINT_PATH)),
    (
        "major_choice_and_cost",
        (
            "chapter_contract.protagonist_choice.*",
            "chapter_contract.pressure_curve.*",
            "chapter_contract.ending_shift",
        ),
    ),
    (
        "information_reveal_and_misdirect",
        (
            "chapter_contract.information.*",
            "chapter_contract.reader_change.*",
            "chapter_contract.forbidden.*",
        ),
    ),
    (
        "foreshadow_payoff_or_close",
        ("chapter_contract.foreshadow_actions.*", "hook_refs[*]"),
    ),
    ("new_facts", ("new_fact_candidates[*]", "fact_boundary_refs[*]")),
    ("outline_change", ("arc_phase", "arc_goal", "change_requests[*]")),
    ("post_freeze_revision", ("revision_request.changed_field_paths[*]",)),
)

_PHASE_A_REAPPROVAL_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (_COVERED_PATHS[1][0], _COVERED_PATHS[1][1]),
    (_COVERED_PATHS[2][0], _COVERED_PATHS[2][1]),
    (
        _COVERED_PATHS[3][0],
        (
            *_COVERED_PATHS[3][1],
            "chapter_contract.foreshadow_actions.not_applicable_reason",
        ),
    ),
    (_COVERED_PATHS[4][0], _COVERED_PATHS[4][1]),
    (_COVERED_PATHS[5][0], _COVERED_PATHS[5][1]),
)


@dataclass(frozen=True, slots=True)
class PhaseAApplicabilityContext:
    """Explicit Phase A event applicability, including an intentional empty context."""

    foreshadow_event_paths: tuple[str, ...] = ()
    new_fact_paths: tuple[str, ...] = ()
    outline_change_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_event_paths(
            self.foreshadow_event_paths,
            ("hook_refs[*]",),
            "foreshadow_event_paths",
        )
        _require_event_paths(
            self.new_fact_paths,
            ("new_fact_candidates[*]", "fact_boundary_refs[*]"),
            "new_fact_paths",
        )
        _require_event_paths(
            self.outline_change_paths,
            ("change_requests[*]",),
            "outline_change_paths",
        )


@dataclass(frozen=True, slots=True)
class PhaseAReapprovalChanges:
    """Phase A change channels kept separate for deterministic reapproval propagation."""

    event_changes: PhaseAApplicabilityContext
    direct_changed_paths: tuple[str, ...] = ()
    causal_dependency_affected_paths: tuple[str, ...] = ()
    baseline_changed_roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for paths in (self.direct_changed_paths, self.causal_dependency_affected_paths):
            _require_paths(paths)
            if any(path.startswith("revision_request") for path in paths):
                raise ValueError("Phase A reapproval changes cannot include post-freeze revision paths")
        roles = _require_paths(self.baseline_changed_roles)
        allowed_roles = frozenset({"profile", "fact_snapshot", "previous_chapter", "outline_change"})
        if any(role not in allowed_roles for role in roles):
            raise ValueError("baseline_changed_roles contains an unsupported role")
        if not isinstance(self.event_changes, PhaseAApplicabilityContext):
            raise TypeError("event_changes must be PhaseAApplicabilityContext")


@dataclass(frozen=True, slots=True)
class _CandidatePathIndex:
    nodes: frozenset[str]
    leaves: frozenset[str]

    @property
    def all_paths(self) -> frozenset[str]:
        return self.nodes | self.leaves


class ContractApprovalPolicy:
    """Immutable field-path policy; it never creates or changes human decisions."""

    @classmethod
    def covered_paths(cls, item_name: str) -> tuple[str, ...]:
        _require_text(item_name, "approval item name")
        for name, paths in _COVERED_PATHS:
            if name == item_name:
                return paths
        raise ValueError(f"unknown approval item: {item_name}")

    @classmethod
    def required_items(
        cls,
        candidate: NarrativeDecision,
        context: PhaseAApplicabilityContext,
    ) -> tuple[str, ...]:
        if not isinstance(candidate, NarrativeDecision):
            raise TypeError("candidate must be a NarrativeDecision")
        candidate.validate()
        if not isinstance(context, PhaseAApplicabilityContext):
            raise TypeError("context must be PhaseAApplicabilityContext")

        required = [
            FULL_CONTRACT,
            "major_choice_and_cost",
            "information_reveal_and_misdirect",
        ]
        if candidate.chapter_contract.foreshadow_actions.values or context.foreshadow_event_paths:
            required.append("foreshadow_payoff_or_close")
        if context.new_fact_paths:
            required.append("new_facts")
        if context.outline_change_paths:
            required.append("outline_change")
        return tuple(required)

    @classmethod
    def required_reapprovals(
        cls,
        candidate: NarrativeDecision,
        changes: PhaseAReapprovalChanges,
        context: PhaseAApplicabilityContext,
    ) -> tuple[str, ...]:
        if not isinstance(changes, PhaseAReapprovalChanges):
            raise TypeError("changes must be PhaseAReapprovalChanges")
        current_required = cls.required_items(candidate, context)
        candidate_paths = _candidate_path_index(candidate).all_paths
        changed_paths = changes.direct_changed_paths + changes.causal_dependency_affected_paths
        if any(path not in candidate_paths for path in changed_paths):
            raise ValueError("reapproval changes contain a non-canonical candidate path")
        if not any(
            (
                changes.direct_changed_paths,
                changes.causal_dependency_affected_paths,
                changes.baseline_changed_roles,
                changes.event_changes.foreshadow_event_paths,
                changes.event_changes.new_fact_paths,
                changes.event_changes.outline_change_paths,
            )
        ):
            return ()

        required = {FULL_CONTRACT}
        for item_name, patterns in _PHASE_A_REAPPROVAL_PATHS:
            if any(_path_matches(pattern, path) for pattern in patterns for path in changed_paths):
                required.add(item_name)

        if changes.event_changes.foreshadow_event_paths:
            required.add("foreshadow_payoff_or_close")
        if changes.event_changes.new_fact_paths:
            required.add("new_facts")
        if changes.event_changes.outline_change_paths:
            required.add("outline_change")

        if changes.baseline_changed_roles:
            required.update(current_required)
            if "outline_change" in changes.baseline_changed_roles:
                required.add("outline_change")
        if changes.causal_dependency_affected_paths and "outline_change" in current_required:
            required.add("outline_change")
        return tuple(item_name for item_name in APPROVAL_ITEMS[:-1] if item_name in required)

    @classmethod
    def required_revision_approvals(
        cls,
        current: NarrativeDecision,
        candidate: NarrativeDecision,
        revision_request: object,
        *,
        authority_causal_impact_paths: tuple[str, ...],
        authority_approved_change_requests: tuple[object, ...],
    ) -> tuple[str, ...]:
        """Derive the complete human re-review set for a frozen replacement."""
        from creative_os.domains.contract_revision import ContractRevisionRequest

        if not isinstance(current, NarrativeDecision) or not isinstance(candidate, NarrativeDecision):
            raise TypeError("current and candidate must be NarrativeDecision values")
        current.validate()
        candidate.validate()
        if not isinstance(revision_request, ContractRevisionRequest):
            raise TypeError("revision_request must be a ContractRevisionRequest")
        if (
            revision_request.contract_id != candidate.contract_id
            or revision_request.replacement_contract_version != candidate.contract_version
            or revision_request.replacement_contract_content_hash
            != NarrativeDecisionCodec.content_hash(candidate)
        ):
            raise ValueError("revision request candidate binding mismatch")
        revision_request.verify(
            current,
            candidate,
            authority_causal_impact_paths=authority_causal_impact_paths,
            authority_approved_change_requests=authority_approved_change_requests,
        )
        required = {FULL_CONTRACT, "post_freeze_revision"}
        for item_name, patterns in _PHASE_A_REAPPROVAL_PATHS:
            if any(
                _path_matches(pattern, path)
                for pattern in patterns
                for path in revision_request.changed_field_paths + revision_request.causal_impact_paths
            ):
                required.add(item_name)
        return tuple(item for item in APPROVAL_ITEMS if item in required)

    @classmethod
    def validate(
        cls,
        record: ContractApprovalRecord,
        candidate: NarrativeDecision,
        context: PhaseAApplicabilityContext,
    ) -> None:
        if not isinstance(record, ContractApprovalRecord):
            raise TypeError("record must be a ContractApprovalRecord")
        if not isinstance(candidate, NarrativeDecision):
            raise TypeError("candidate must be a NarrativeDecision")
        if (
            record.contract_id != candidate.contract_id
            or record.contract_version != candidate.contract_version
            or record.contract_content_hash != NarrativeDecisionCodec.content_hash(candidate)
        ):
            raise ValueError("approval record candidate binding mismatch")
        candidate_leaves = _candidate_path_index(candidate).leaves
        for item_name, item in record.approvals:
            for evidence in item.decision_evidence:
                if item_name == FULL_CONTRACT and evidence.field_path == _BASELINE_FINGERPRINT_PATH:
                    if evidence.source_content_hash != record.baseline_manifest.fingerprint:
                        raise ValueError(
                            "approval full_contract decision evidence does not bind current "
                            "baseline fingerprint"
                        )
                elif evidence.field_path not in candidate_leaves:
                    raise ValueError(
                        f"approval {item_name} decision evidence is not a canonical candidate leaf"
                    )
        for item_name in cls.required_items(candidate, context):
            if item_name != FULL_CONTRACT and record.item(item_name).status == ApprovalStatus.NOT_APPLICABLE:
                raise ValueError(f"invalid_approval_not_applicable: {item_name}")


def _require_paths(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError("field paths must be a tuple")
    for path in value:
        _require_text(path, "field path")
        _require_concrete_field_path(path)
    if len(set(value)) != len(value):
        raise ValueError("field paths must not contain duplicates")
    return value


def _require_event_paths(value: object, patterns: tuple[str, ...], name: str) -> tuple[str, ...]:
    paths = _require_paths(value)
    if any(not any(_path_matches(pattern, path) for pattern in patterns) for path in paths):
        raise ValueError(f"{name} contains an out-of-domain path")
    return paths


def _path_matches(pattern: str, path: str) -> bool:
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return path == prefix or path.startswith(prefix + ".")
    if pattern.endswith("[*]"):
        prefix = pattern[:-3]
        if path == prefix:
            return True
        suffix = path[len(prefix) :] if path.startswith(prefix) else ""
        return fullmatch(
            r"\[\d+\](?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?)*",
            suffix,
        ) is not None
    return path == pattern


def _validate_decision_evidence_coverage(item_name: str, field_path: str | None) -> None:
    if field_path is None:
        raise ValueError(f"approval {item_name} decision evidence requires a field_path")
    _require_concrete_field_path(field_path)
    if item_name == FULL_CONTRACT:
        return
    patterns = ContractApprovalPolicy.covered_paths(item_name)
    if not any(_path_matches(pattern, field_path) for pattern in patterns):
        raise ValueError(f"approval {item_name} decision evidence is outside its coverage")


def _require_concrete_field_path(path: str) -> str:
    if fullmatch(_CONCRETE_FIELD_PATH, path) is None:
        raise ValueError("field path must be a concrete path with numeric array indices")
    return path


def _candidate_path_index(candidate: NarrativeDecision) -> _CandidatePathIndex:
    candidate.validate()
    nodes: set[str] = set()
    leaves: set[str] = set()

    def visit(value: object, path: str) -> None:
        if is_dataclass(value) and not isinstance(value, type):
            if path:
                nodes.add(path)
            for model_field in fields(value):
                child_path = f"{path}.{model_field.name}" if path else model_field.name
                visit(getattr(value, model_field.name), child_path)
            return
        if isinstance(value, tuple):
            nodes.add(path)
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
            return
        if value is None:
            nodes.add(path)
            return
        leaves.add(path)

    visit(candidate, "")
    return _CandidatePathIndex(nodes=frozenset(nodes), leaves=frozenset(leaves))
