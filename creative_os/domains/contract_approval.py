from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from creative_os.domains.contract_baseline import BaselineManifest
from creative_os.domains.narrative_evidence import EvidenceRef, EvidenceRole


class ApprovalStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NOT_APPLICABLE = "not_applicable"


FULL_CONTRACT = "full_contract"
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
    (FULL_CONTRACT, ("NarrativeDecision.*", "BaselineManifest.fingerprint")),
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

_REAPPROVAL_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
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
    ("post_freeze_revision", ("revision_request.*",)),
)


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
    def required_items(cls, applicable_field_paths: tuple[str, ...]) -> tuple[str, ...]:
        paths = _require_paths(applicable_field_paths)
        required = [FULL_CONTRACT]
        for item_name, patterns in _COVERED_PATHS[1:]:
            if any(
                not path.endswith(".not_applicable_reason") and _path_matches(pattern, path)
                for pattern in patterns
                for path in paths
            ):
                required.append(item_name)
        return tuple(required)

    @classmethod
    def required_reapprovals(cls, changed_field_paths: tuple[str, ...]) -> tuple[str, ...]:
        paths = _require_paths(changed_field_paths)
        if not paths:
            return ()
        required = [FULL_CONTRACT]
        for item_name, patterns in _REAPPROVAL_PATHS:
            if any(_path_matches(pattern, path) for pattern in patterns for path in paths):
                required.append(item_name)
        return tuple(required)

    @classmethod
    def validate(
        cls,
        record: ContractApprovalRecord,
        applicable_field_paths: tuple[str, ...],
    ) -> None:
        if not isinstance(record, ContractApprovalRecord):
            raise TypeError("record must be a ContractApprovalRecord")
        for item_name in cls.required_items(applicable_field_paths):
            if item_name != FULL_CONTRACT and record.item(item_name).status == ApprovalStatus.NOT_APPLICABLE:
                raise ValueError(f"invalid_approval_not_applicable: {item_name}")


def _require_paths(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError("field paths must be a tuple")
    for path in value:
        _require_text(path, "field path")
    if len(set(value)) != len(value):
        raise ValueError("field paths must not contain duplicates")
    return value


def _path_matches(pattern: str, path: str) -> bool:
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[")
    if pattern.endswith("[*]"):
        prefix = pattern[:-3]
        if not path.startswith(prefix + "["):
            return False
        suffix = path[len(prefix) + 1 :]
        return bool(suffix) and suffix.endswith("]") and "]" not in suffix[:-1]
    return path == pattern
