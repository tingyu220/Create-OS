from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EngagementValidationError(ValueError):
    pass


class EngagementScope(StrEnum):
    BOOK = "book"
    VOLUME = "volume"
    ARC = "arc"
    CHAPTER = "chapter"


class ExpectationState(StrEnum):
    OPEN = "open"
    ESCALATING = "escalating"
    PAID = "paid"
    ABANDONED = "abandoned"


class EngagementReviewStatus(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"


class EngagementAction(StrEnum):
    ESTABLISH = "establish"
    ESCALATE = "escalate"
    PAY = "pay"
    WITHHOLD = "withhold"


class EngagementIntensity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PEAK = "peak"


class EngagementStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    REJECTED = "rejected"


class EngagementDecisionDisposition(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NOT_APPLICABLE = "not_applicable"


class OpeningCheckpointDisposition(StrEnum):
    APPROVED = "approved"
    REVISION_REQUIRED = "revision_required"


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise EngagementValidationError(f"{name} is required")
    return value


def _hash(value: object, name: str) -> str:
    value = _text(value, name)
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise EngagementValidationError(f"{name} must be lowercase sha256")
    return value


def _positive(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise EngagementValidationError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class VolumeEngagement:
    objectives: tuple[str, ...]
    not_applicable_reason: str | None

    def __post_init__(self) -> None:
        objectives = self.objectives
        if not isinstance(objectives, tuple) or any(type(item) is not str or not item.strip() for item in objectives):
            raise EngagementValidationError("volume objectives must be non-empty strings")
        reason = self.not_applicable_reason
        if reason is not None and (type(reason) is not str or not reason.strip()):
            raise EngagementValidationError("volume N/A reason must be non-empty")
        if bool(objectives) == bool(reason):
            raise EngagementValidationError("volume requires objectives or N/A reason")


@dataclass(frozen=True, slots=True)
class EngagementPlan:
    project_id: str
    version: int
    status: EngagementStatus
    content_hash: str

    def __post_init__(self) -> None:
        _text(self.project_id, "project_id")
        _positive(self.version, "version")
        if not isinstance(self.status, EngagementStatus):
            raise EngagementValidationError("invalid plan status")
        _hash(self.content_hash, "content_hash")


@dataclass(frozen=True, slots=True)
class ExpectationRecord:
    expectation_id: str
    state: ExpectationState
    created_chapter: int
    expected_payoff_window: tuple[int, int]

    def __post_init__(self) -> None:
        _text(self.expectation_id, "expectation_id")
        if not isinstance(self.state, ExpectationState):
            raise EngagementValidationError("invalid expectation state")
        _positive(self.created_chapter, "created_chapter")
        if (not isinstance(self.expected_payoff_window, tuple)
                or len(self.expected_payoff_window) != 2
                or any(type(item) is not int or item <= 0 for item in self.expected_payoff_window)
                or self.expected_payoff_window[0] > self.expected_payoff_window[1]):
            raise EngagementValidationError("invalid payoff window")


@dataclass(frozen=True, slots=True)
class EngagementObligation:
    obligation_id: str
    expectation_id: str
    action: str
    expected_payoff_window: tuple[int, int]
    evidence: tuple[object, ...]

    def __post_init__(self) -> None:
        _text(self.obligation_id, "obligation_id")
        _text(self.expectation_id, "expectation_id")
        if self.action not in {item.value for item in EngagementAction}:
            raise EngagementValidationError("invalid engagement action")
        ExpectationRecord("x", ExpectationState.OPEN, 1, self.expected_payoff_window)
        if not isinstance(self.evidence, tuple):
            raise EngagementValidationError("evidence must be tuple")


@dataclass(frozen=True, slots=True)
class EngagementCurveEntry:
    chapter_number: int
    intensity: EngagementIntensity
    arc_id: str
    expectation_obligation_ids: tuple[str, ...]
    causal_rationale: str

    def __post_init__(self) -> None:
        _positive(self.chapter_number, "chapter_number")
        if not isinstance(self.intensity, EngagementIntensity):
            raise EngagementValidationError("invalid intensity")
        _text(self.arc_id, "arc_id")
        if not isinstance(self.expectation_obligation_ids, tuple) or any(type(item) is not str for item in self.expectation_obligation_ids):
            raise EngagementValidationError("invalid obligation ids")
        _text(self.causal_rationale, "causal_rationale")


@dataclass(frozen=True, slots=True)
class EngagementCurve:
    plan_id: str
    plan_hash: str
    entries: tuple[EngagementCurveEntry, ...]

    def __post_init__(self) -> None:
        _text(self.plan_id, "plan_id")
        _hash(self.plan_hash, "plan_hash")
        if not isinstance(self.entries, tuple):
            raise EngagementValidationError("entries must be tuple")


@dataclass(frozen=True, slots=True)
class ChapterEngagementProjection:
    plan_id: str
    plan_version: int
    plan_hash: str
    ledger_head_hash: str
    curve_hash: str
    chapter_number: int
    obligation_ids: tuple[str, ...]
    canonical_json: str
    projection_hash: str

    def __post_init__(self) -> None:
        _text(self.plan_id, "plan_id")
        _positive(self.plan_version, "plan_version")
        for name, value in (("plan_hash", self.plan_hash), ("ledger_head_hash", self.ledger_head_hash), ("curve_hash", self.curve_hash), ("projection_hash", self.projection_hash)):
            _hash(value, name)
        _positive(self.chapter_number, "chapter_number")
        if not isinstance(self.obligation_ids, tuple) or any(type(item) is not str or not item for item in self.obligation_ids):
            raise EngagementValidationError("invalid obligation ids")
        _text(self.canonical_json, "canonical_json")


@dataclass(frozen=True, slots=True)
class PlanDecisionRecord:
    plan_id: str
    plan_hash: str
    curve_id: str
    curve_hash: str
    actor: str
    reason: str

    def __post_init__(self) -> None:
        _text(self.plan_id, "plan_id")
        _hash(self.plan_hash, "plan_hash")
        _text(self.curve_id, "curve_id")
        _hash(self.curve_hash, "curve_hash")
        _text(self.actor, "actor")
        _text(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class ExpectationTransitionCandidate:
    expectation_id: str
    from_state: str
    to_state: str
    artifact_hash: str
    evidence: tuple[object, ...]

    def __post_init__(self) -> None:
        _text(self.expectation_id, "expectation_id")
        if self.from_state not in {"absent", *(item.value for item in ExpectationState)} or self.to_state not in {item.value for item in ExpectationState}:
            raise EngagementValidationError("invalid transition state")
        _hash(self.artifact_hash, "artifact_hash")
        if not isinstance(self.evidence, tuple):
            raise EngagementValidationError("evidence must be tuple")


@dataclass(frozen=True, slots=True)
class PlanActivationRecord:
    plan_id: str
    plan_hash: str
    curve_id: str
    curve_hash: str
    activation_binding_hash: str

    def __post_init__(self) -> None:
        _text(self.plan_id, "plan_id")
        _hash(self.plan_hash, "plan_hash")
        _text(self.curve_id, "curve_id")
        _hash(self.curve_hash, "curve_hash")
        _hash(self.activation_binding_hash, "activation_binding_hash")


@dataclass(frozen=True, slots=True)
class ExpectationTransitionDecision:
    candidate_id: str
    disposition: EngagementDecisionDisposition
    actor: str
    reason: str
    previous_authority_hash: str

    def __post_init__(self) -> None:
        _text(self.candidate_id, "candidate_id")
        if not isinstance(self.disposition, EngagementDecisionDisposition):
            raise EngagementValidationError("invalid decision disposition")
        _text(self.actor, "actor")
        _text(self.reason, "reason")
        _hash(self.previous_authority_hash, "previous_authority_hash")


@dataclass(frozen=True, slots=True)
class EngagementReviewResult:
    status: EngagementReviewStatus
    plan_hash: str
    ledger_head_hash: str
    curve_hash: str
    artifact_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, EngagementReviewStatus):
            raise EngagementValidationError("invalid review status")
        for name, value in (("plan_hash", self.plan_hash), ("ledger_head_hash", self.ledger_head_hash), ("curve_hash", self.curve_hash), ("artifact_hash", self.artifact_hash)):
            _hash(value, name)


@dataclass(frozen=True, slots=True)
class OpeningCheckpointReviewRecord:
    project_id: str
    chapter_number: int
    plan_hash: str
    projection_hash: str
    ledger_head_hash: str
    curve_hash: str
    contract_hash: str
    context_fingerprint: str
    artifact_hash: str
    ruleset_hash: str

    def __post_init__(self) -> None:
        _text(self.project_id, "project_id")
        _positive(self.chapter_number, "chapter_number")
        for name, value in (("plan_hash", self.plan_hash), ("projection_hash", self.projection_hash), ("ledger_head_hash", self.ledger_head_hash), ("curve_hash", self.curve_hash), ("contract_hash", self.contract_hash), ("context_fingerprint", self.context_fingerprint), ("artifact_hash", self.artifact_hash), ("ruleset_hash", self.ruleset_hash)):
            _hash(value, name)


@dataclass(frozen=True, slots=True)
class OpeningCheckpointReviewDecision:
    record_id: str
    disposition: OpeningCheckpointDisposition
    actor: str
    reason: str
    previous_authority_hash: str

    def __post_init__(self) -> None:
        _text(self.record_id, "record_id")
        if not isinstance(self.disposition, OpeningCheckpointDisposition):
            raise EngagementValidationError("invalid opening disposition")
        _text(self.actor, "actor")
        _text(self.reason, "reason")
        _hash(self.previous_authority_hash, "previous_authority_hash")
