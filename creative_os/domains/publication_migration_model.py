from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import ntpath
from pathlib import PurePath, PureWindowsPath
import re

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash(value: str, name: str, allow_empty: bool = False) -> None:
    if not isinstance(value, str) or (not value and not allow_empty) or (value and not _HASH_RE.fullmatch(value)):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")


def _required_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


def _decision_time(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("decided_at is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as cause:
        raise ValueError("decided_at must be an ISO-8601 timestamp") from cause
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("decided_at must include a timezone")


class ManifestStatus(Enum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    REBUILT = "rebuilt"
    VERIFIED = "verified"
    ACTIVATED = "activated"


class CheckpointPhase(Enum):
    SNAPSHOT_VERIFIED = "snapshot_verified"
    PLAN_APPROVED = "plan_approved"
    CONTENT_REBUILT = "content_rebuilt"
    AUTHORITY_REBUILT = "authority_rebuilt"
    BATCH_VERIFIED = "batch_verified"
    ACTIVATED = "activated"
    FAILED = "failed"


class LengthIntervalKind(Enum):
    SOFT_LIMIT = "soft_limit"
    SHORT_CHAPTER = "short_chapter"


class RewriteKind(Enum):
    VERBATIM = "verbatim"
    LIGHT_REWRITE = "light_rewrite"


@dataclass(frozen=True, slots=True)
class FileHashRecord:
    relative_path: str
    content_hash: str

    def __post_init__(self) -> None:
        if (not isinstance(self.relative_path, str) or not self.relative_path.strip()
                or ntpath.isabs(self.relative_path) or PurePath(self.relative_path).is_absolute()
                or PureWindowsPath(self.relative_path).is_absolute()
                or ".." in PurePath(self.relative_path).parts):
            raise ValueError("invalid relative path")
        _hash(self.content_hash, "content hash")


@dataclass(frozen=True, slots=True)
class RewriteRecord:
    source_text_hash: str
    rewritten_text_hash: str
    reason: str

    def __post_init__(self) -> None:
        _hash(self.source_text_hash, "source text hash")
        _hash(self.rewritten_text_hash, "rewritten text hash")
        _required_text(self.reason, "rewrite reason")


@dataclass(frozen=True, slots=True)
class SourceFragment:
    source_chapter: int
    paragraph_start: int
    paragraph_end: int
    text_hash: str

    def __post_init__(self) -> None:
        if (type(self.source_chapter) is not int or self.source_chapter <= 0
                or type(self.paragraph_start) is not int or self.paragraph_start <= 0
                or type(self.paragraph_end) is not int or self.paragraph_end <= 0
                or self.paragraph_start > self.paragraph_end):
            raise ValueError("invalid source fragment range")
        _hash(self.text_hash, "text hash")


@dataclass(frozen=True, slots=True)
class TargetEvidenceSpan:
    """目标正文证据；offset 是 Python Unicode 码点的左闭右开区间。"""
    target_chapter: int
    start_offset: int
    end_offset: int
    excerpt: str
    excerpt_hash: str
    body_hash: str

    def __post_init__(self) -> None:
        if (type(self.target_chapter) is not int or self.target_chapter <= 0
                or type(self.start_offset) is not int or type(self.end_offset) is not int
                or self.start_offset < 0 or self.end_offset <= self.start_offset
                or not isinstance(self.excerpt, str) or not self.excerpt
                or self.end_offset - self.start_offset != len(self.excerpt)):
            raise ValueError("invalid target evidence span")
        _hash(self.excerpt_hash, "excerpt_hash")
        _hash(self.body_hash, "body_hash")
        if hashlib.sha256(self.excerpt.encode("utf-8")).hexdigest() != self.excerpt_hash:
            raise ValueError("excerpt_hash does not match excerpt")


@dataclass(frozen=True, slots=True)
class SourceToTargetMapping:
    source_fragment: SourceFragment
    target_chapter: int
    target_span: TargetEvidenceSpan
    rewrite_kind: RewriteKind
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source_fragment, SourceFragment):
            raise TypeError("source_fragment is required")
        if self.source_fragment.paragraph_start != self.source_fragment.paragraph_end:
            raise ValueError("mapping requires a single source paragraph")
        if type(self.target_chapter) is not int or self.target_chapter <= 0:
            raise ValueError("invalid target chapter")
        if not isinstance(self.target_span, TargetEvidenceSpan):
            raise TypeError("target_span is required")
        if self.target_span.target_chapter != self.target_chapter:
            raise ValueError("mapping target chapter mismatch")
        if not isinstance(self.rewrite_kind, RewriteKind) or not isinstance(self.reason, str):
            raise ValueError("invalid rewrite mapping")
        if self.rewrite_kind is RewriteKind.LIGHT_REWRITE and not self.reason.strip():
            raise ValueError("light rewrite reason is required")
        if self.rewrite_kind is RewriteKind.VERBATIM and self.reason:
            raise ValueError("verbatim mapping cannot have a rewrite reason")
        if (self.rewrite_kind is RewriteKind.VERBATIM
                and self.source_fragment.text_hash
                != hashlib.sha256(self.target_span.excerpt.encode("utf-8")).hexdigest()):
            raise ValueError("verbatim source and target text hash mismatch")


@dataclass(frozen=True, slots=True)
class DramaticOutcomeBinding:
    outcome_id: str
    dramatic_unit_hash: str
    candidate_hash: str
    target_chapter: int
    outcome_evidence: TargetEvidenceSpan
    hook_evidence: TargetEvidenceSpan

    def __post_init__(self) -> None:
        _required_text(self.outcome_id, "outcome_id")
        _hash(self.dramatic_unit_hash, "dramatic_unit_hash")
        _hash(self.candidate_hash, "candidate_hash")
        if type(self.target_chapter) is not int or self.target_chapter <= 0:
            raise ValueError("invalid target chapter")
        if not isinstance(self.outcome_evidence, TargetEvidenceSpan) or not isinstance(self.hook_evidence, TargetEvidenceSpan):
            raise TypeError("outcome and hook evidence are required")
        if (self.outcome_evidence.target_chapter != self.target_chapter
                or self.hook_evidence.target_chapter != self.target_chapter
                or self.outcome_evidence.body_hash != self.hook_evidence.body_hash):
            raise ValueError("dramatic outcome target chapter or body mismatch")


@dataclass(frozen=True, slots=True)
class PublicationLengthPolicy:
    target_min: int = 3000
    target_max: int = 4500
    soft_max: int = 5000
    hard_max: int = 5500
    short_min: int = 2500
    hook_tail_window_codepoints: int = 800

    def __post_init__(self) -> None:
        values = (self.target_min, self.target_max, self.soft_max, self.hard_max, self.short_min,
                  self.hook_tail_window_codepoints)
        if (not all(type(value) is int and value > 0 for value in values)
                or not self.short_min <= self.target_min <= self.target_max <= self.soft_max <= self.hard_max):
            raise ValueError("invalid length policy")


def length_policy_hash(policy: PublicationLengthPolicy) -> str:
    if not isinstance(policy, PublicationLengthPolicy):
        raise TypeError("policy is required")
    return _canonical_hash({"hard_max": policy.hard_max, "short_min": policy.short_min,
                            "hook_tail_window_codepoints": policy.hook_tail_window_codepoints,
                            "soft_max": policy.soft_max, "target_max": policy.target_max,
                            "target_min": policy.target_min})


def _validate_length_reference(value: object, expected_kind: LengthIntervalKind) -> None:
    _required_text(getattr(value, "disposition_id"), "disposition_id")
    _hash(getattr(value, "decision_hash"), "decision_hash")
    if type(getattr(value, "record_sequence")) is not int or getattr(value, "record_sequence") <= 0:
        raise ValueError("invalid length disposition record sequence")
    _required_text(getattr(value, "migration_id"), "migration_id")
    if type(getattr(value, "target_chapter")) is not int or getattr(value, "target_chapter") <= 0:
        raise ValueError("invalid target chapter")
    _hash(getattr(value, "body_hash"), "body_hash")
    _hash(getattr(value, "policy_hash"), "policy_hash")
    if getattr(value, "interval_kind") is not expected_kind:
        raise ValueError("invalid length interval kind")
    _required_text(getattr(value, "actor"), "actor")
    _required_text(getattr(value, "reason"), "reason")
    _decision_time(getattr(value, "decided_at"))


@dataclass(frozen=True, slots=True)
class LengthDisposition:
    disposition_id: str
    decision_hash: str
    record_sequence: int
    migration_id: str
    target_chapter: int
    body_hash: str
    policy_hash: str
    interval_kind: LengthIntervalKind
    actor: str
    reason: str
    decided_at: str

    def __post_init__(self) -> None:
        _validate_length_reference(self, LengthIntervalKind.SOFT_LIMIT)


@dataclass(frozen=True, slots=True)
class ShortChapterApproval:
    disposition_id: str
    decision_hash: str
    record_sequence: int
    migration_id: str
    target_chapter: int
    body_hash: str
    policy_hash: str
    interval_kind: LengthIntervalKind
    actor: str
    reason: str
    decided_at: str

    def __post_init__(self) -> None:
        _validate_length_reference(self, LengthIntervalKind.SHORT_CHAPTER)


@dataclass(frozen=True, slots=True)
class MigrationOmission:
    source_chapter: int
    paragraph_start: int
    paragraph_end: int
    original_text_hash: str
    reason: str
    snapshot_hash: str = ""
    migration_id: str = ""
    split_plan_candidate_hash: str = ""
    split_plan_decision_hash: str = ""
    actor: str = ""
    decided_at: str = ""

    def __post_init__(self) -> None:
        SourceFragment(self.source_chapter, self.paragraph_start, self.paragraph_end, self.original_text_hash)
        _required_text(self.reason, "omission reason")
        metadata = (self.snapshot_hash, self.migration_id, self.split_plan_candidate_hash,
                    self.split_plan_decision_hash, self.actor, self.decided_at)
        if any(metadata):
            if not all(metadata):
                raise ValueError("omission approval metadata must be complete")
            _hash(self.snapshot_hash, "snapshot_hash")
            _required_text(self.migration_id, "migration_id")
            _hash(self.split_plan_candidate_hash, "split_plan_candidate_hash")
            _hash(self.split_plan_decision_hash, "split_plan_decision_hash")
            _required_text(self.actor, "actor")
            _decision_time(self.decided_at)


@dataclass(frozen=True, slots=True)
class PublicationChapterEntry:
    target_chapter: int
    source_fragments: tuple[SourceFragment, ...]
    omissions: tuple[MigrationOmission, ...] = ()
    title: str = "标题"
    body_hash: str = "0" * 64
    rewrites: tuple[RewriteRecord, ...] = ()
    chapter_function: str = "未指定"
    turning_point: str = "未指定"
    ending_hook: str = "未指定"
    canon_assertions: tuple[str, ...] = ()
    contract_id: str = "contract"
    state_receipt_id: str = "receipt"
    source_mappings: tuple[SourceToTargetMapping, ...] = ()
    ending_hook_evidence: tuple[TargetEvidenceSpan, ...] = ()
    length_dispositions: tuple[LengthDisposition, ...] = ()
    short_chapter_approvals: tuple[ShortChapterApproval, ...] = ()
    dramatic_outcomes: tuple[DramaticOutcomeBinding, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if type(self.target_chapter) is not int or self.target_chapter <= 0:
            raise ValueError("invalid chapter entry")
        collections = ((self.source_fragments, SourceFragment, "source_fragments"),
                       (self.omissions, MigrationOmission, "omissions"),
                       (self.rewrites, RewriteRecord, "rewrites"),
                       (self.source_mappings, SourceToTargetMapping, "source_mappings"),
                       (self.ending_hook_evidence, TargetEvidenceSpan, "ending_hook_evidence"),
                       (self.length_dispositions, LengthDisposition, "length_dispositions"),
                       (self.short_chapter_approvals, ShortChapterApproval, "short_chapter_approvals"),
                       (self.dramatic_outcomes, DramaticOutcomeBinding, "dramatic_outcomes"))
        for values, expected, name in collections:
            if not isinstance(values, tuple) or not all(isinstance(item, expected) for item in values):
                raise ValueError(f"invalid {name}")
        for name in ("title", "chapter_function", "turning_point", "ending_hook", "contract_id", "state_receipt_id"):
            _required_text(getattr(self, name), name)
        _hash(self.body_hash, "body hash")
        if not isinstance(self.canon_assertions, tuple) or not all(isinstance(value, str) and value.strip() for value in self.canon_assertions):
            raise ValueError("invalid canon_assertions")
        if type(self.schema_version) is not int or self.schema_version not in {1, 2}:
            raise ValueError("unsupported entry schema version")
        if self.schema_version == 1:
            if any((self.source_mappings, self.ending_hook_evidence, self.length_dispositions,
                    self.short_chapter_approvals, self.dramatic_outcomes)):
                raise ValueError("schema v1 entry cannot contain v2 fields")
            return
        self._validate_v2()

    def _validate_v2(self) -> None:
        if not self.source_fragments or not self.source_mappings:
            raise ValueError("source mapping coverage is required")
        if tuple(mapping.source_fragment for mapping in self.source_mappings) != self.source_fragments:
            raise ValueError("source mapping coverage or source order mismatch")
        previous_end = -1
        for mapping in self.source_mappings:
            if mapping.target_chapter != self.target_chapter or mapping.target_span.body_hash != self.body_hash:
                raise ValueError("source mapping target binding mismatch")
            if mapping.target_span.start_offset < previous_end:
                raise ValueError("source mapping order or overlap is invalid")
            previous_end = mapping.target_span.end_offset
        if not self.ending_hook_evidence or not self.dramatic_outcomes:
            raise ValueError("ending hook and dramatic outcome evidence are required")
        for span in self.ending_hook_evidence:
            if span.target_chapter != self.target_chapter or span.body_hash != self.body_hash:
                raise ValueError("ending hook evidence target binding mismatch")
        if len(set(self.ending_hook_evidence)) != len(self.ending_hook_evidence):
            raise ValueError("duplicate ending hook evidence")
        if len({item.outcome_id for item in self.dramatic_outcomes}) != len(self.dramatic_outcomes):
            raise ValueError("duplicate outcome_id")
        if len({(item.dramatic_unit_hash, item.candidate_hash) for item in self.dramatic_outcomes}) != len(self.dramatic_outcomes):
            raise ValueError("duplicate dramatic outcome binding")
        for outcome in self.dramatic_outcomes:
            if outcome.target_chapter != self.target_chapter or outcome.outcome_evidence.body_hash != self.body_hash:
                raise ValueError("dramatic outcome target binding mismatch")
            if outcome.hook_evidence not in self.ending_hook_evidence:
                raise ValueError("dramatic outcome hook evidence mismatch")
        if set(self.ending_hook_evidence) != {item.hook_evidence for item in self.dramatic_outcomes}:
            raise ValueError("ending hook evidence set mismatch")
        if len(self.length_dispositions) + len(self.short_chapter_approvals) > 1:
            raise ValueError("conflicting length disposition")
        for approval in (*self.length_dispositions, *self.short_chapter_approvals):
            if approval.target_chapter != self.target_chapter or approval.body_hash != self.body_hash:
                raise ValueError("length disposition target binding mismatch")


@dataclass(frozen=True, slots=True)
class MigrationCheckpoint:
    migration_id: str
    phase: CheckpointPhase
    batch_id: str
    input_fingerprint: str
    output_fingerprint: str = ""
    error: str = ""
    project_id: str = ""
    source_edition_id: str = ""
    target_edition_id: str = ""
    source_start: int = 0
    source_end: int = 0
    previous_checkpoint_hash: str = ""
    checkpoint_hash: str = ""

    def __post_init__(self) -> None:
        _required_text(self.migration_id, "migration_id")
        _required_text(self.batch_id, "batch_id")
        if not isinstance(self.phase, CheckpointPhase):
            raise ValueError("invalid checkpoint identity")
        _hash(self.input_fingerprint, "input fingerprint")
        _hash(self.output_fingerprint, "output fingerprint", allow_empty=True)
        if self.phase is CheckpointPhase.FAILED and (not isinstance(self.error, str) or not self.error.strip()):
            raise ValueError("failed checkpoint requires error")
        if self.phase is not CheckpointPhase.FAILED and self.error != "":
            raise ValueError("non-failed checkpoint cannot have error")
        identity = (self.project_id, self.source_edition_id, self.target_edition_id)
        if any(identity) or self.source_start or self.source_end or self.previous_checkpoint_hash or self.checkpoint_hash:
            if not all(isinstance(value, str) and value.strip() for value in identity):
                raise ValueError("checkpoint authority identity must be complete")
            if self.source_edition_id == self.target_edition_id:
                raise ValueError("checkpoint editions must differ")
            if (type(self.source_start) is not int or type(self.source_end) is not int
                    or not ((self.source_start, self.source_end) == (0, 0)
                            or 0 < self.source_start <= self.source_end)):
                raise ValueError("invalid checkpoint source range")
            _hash(self.previous_checkpoint_hash, "previous_checkpoint_hash", allow_empty=True)
            _hash(self.checkpoint_hash, "checkpoint_hash", allow_empty=True)
            if self.checkpoint_hash and self.checkpoint_hash != migration_checkpoint_hash(self):
                raise ValueError("checkpoint_hash mismatch")


def migration_checkpoint_hash(value: MigrationCheckpoint) -> str:
    if not isinstance(value, MigrationCheckpoint):
        raise TypeError("checkpoint is required")
    return _canonical_hash({
        "batch_id": value.batch_id, "error": value.error,
        "input_fingerprint": value.input_fingerprint, "migration_id": value.migration_id,
        "output_fingerprint": value.output_fingerprint, "phase": value.phase.value,
        "previous_checkpoint_hash": value.previous_checkpoint_hash,
        "project_id": value.project_id, "source_edition_id": value.source_edition_id,
        "source_end": value.source_end, "source_start": value.source_start,
        "target_edition_id": value.target_edition_id,
    })


@dataclass(frozen=True, slots=True)
class PublicationChapterMigrationManifest:
    migration_id: str
    project_id: str
    source_edition_id: str
    target_edition_id: str
    source_start: int
    source_end: int
    frozen_through_chapter: int
    entries: tuple[PublicationChapterEntry, ...]
    omissions: tuple[MigrationOmission, ...]
    length_policy: PublicationLengthPolicy
    checkpoints: tuple[MigrationCheckpoint, ...]
    status: ManifestStatus
    source_file_hashes: tuple[FileHashRecord, ...] = ()
    frozen_file_hashes: tuple[FileHashRecord, ...] = ()
    approved_by: str = ""
    approved_at: str = ""
    manifest_hash: str = ""
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name in ("migration_id", "project_id", "source_edition_id", "target_edition_id"):
            _required_text(getattr(self, name), name)
        if (self.source_edition_id == self.target_edition_id or type(self.source_start) is not int
                or type(self.source_end) is not int or type(self.frozen_through_chapter) is not int
                or self.frozen_through_chapter < 0
                or not self.frozen_through_chapter < self.source_start <= self.source_end):
            raise ValueError("invalid manifest identity or range")
        if (not isinstance(self.entries, tuple) or not all(isinstance(item, PublicationChapterEntry) for item in self.entries)
                or not isinstance(self.omissions, tuple) or not all(isinstance(item, MigrationOmission) for item in self.omissions)
                or tuple(item.target_chapter for item in self.entries)
                != tuple(range(self.frozen_through_chapter + 1, self.frozen_through_chapter + 1 + len(self.entries)))):
            raise ValueError("invalid manifest entries")
        if not isinstance(self.length_policy, PublicationLengthPolicy):
            raise ValueError("invalid length policy")
        if not isinstance(self.checkpoints, tuple) or not all(isinstance(item, MigrationCheckpoint) and item.migration_id == self.migration_id for item in self.checkpoints):
            raise ValueError("invalid checkpoints")
        if not isinstance(self.status, ManifestStatus):
            raise ValueError("invalid manifest status")
        for collection in (self.source_file_hashes, self.frozen_file_hashes):
            if (not isinstance(collection, tuple) or not all(isinstance(item, FileHashRecord) for item in collection)
                    or len({item.relative_path for item in collection}) != len(collection)):
                raise ValueError("invalid file hashes")
        if not isinstance(self.approved_by, str) or not isinstance(self.approved_at, str):
            raise ValueError("approval metadata must be strings")
        if self.status in {ManifestStatus.APPROVED, ManifestStatus.REBUILT, ManifestStatus.VERIFIED, ManifestStatus.ACTIVATED} and (not self.approved_by.strip() or not self.approved_at.strip()):
            raise ValueError("approval metadata required")
        if self.status is ManifestStatus.CANDIDATE and (self.approved_by or self.approved_at):
            raise ValueError("candidate cannot have approval metadata")
        _hash(self.manifest_hash, "manifest hash", allow_empty=True)
        if type(self.schema_version) is not int or self.schema_version not in {1, 2}:
            raise ValueError("unsupported manifest schema version")
        if self.schema_version == 1 and any(entry.schema_version != 1 for entry in self.entries):
            raise ValueError("schema v1 manifest cannot contain v2 entries")
        if self.schema_version == 1 and any(
            checkpoint.project_id or checkpoint.source_edition_id or checkpoint.target_edition_id
            or checkpoint.source_start or checkpoint.source_end
            or checkpoint.previous_checkpoint_hash or checkpoint.checkpoint_hash
            for checkpoint in self.checkpoints
        ):
            raise ValueError("schema v1 manifest cannot contain v2 checkpoints")
        if self.schema_version == 2:
            if any(entry.schema_version != 2 for entry in self.entries):
                raise ValueError("schema v2 manifest requires v2 entries")
            approved_omissions = (*self.omissions, *(item for entry in self.entries for item in entry.omissions))
            if any(not omission.split_plan_decision_hash or omission.migration_id != self.migration_id
                   for omission in approved_omissions):
                raise ValueError("schema v2 omissions require exact approval binding")
            expected_policy_hash = length_policy_hash(self.length_policy)
            for entry in self.entries:
                if any(approval.migration_id != self.migration_id or approval.policy_hash != expected_policy_hash
                       for approval in (*entry.length_dispositions, *entry.short_chapter_approvals)):
                    raise ValueError("length disposition manifest or policy binding mismatch")
            previous_checkpoint_hash = ""
            for checkpoint in self.checkpoints:
                if (not checkpoint.checkpoint_hash or checkpoint.project_id != self.project_id
                        or checkpoint.source_edition_id != self.source_edition_id
                        or checkpoint.target_edition_id != self.target_edition_id
                        or checkpoint.previous_checkpoint_hash != previous_checkpoint_hash
                        or ((checkpoint.source_start, checkpoint.source_end) != (0, 0)
                            and not (self.source_start <= checkpoint.source_start
                                     <= checkpoint.source_end <= self.source_end))):
                    raise ValueError("schema v2 checkpoint binding or chain mismatch")
                previous_checkpoint_hash = checkpoint.checkpoint_hash
        consumed = [(item.source_chapter, item.paragraph_start, item.paragraph_end)
                    for entry in self.entries for item in (*entry.source_fragments, *entry.omissions)]
        consumed += [(item.source_chapter, item.paragraph_start, item.paragraph_end) for item in self.omissions]
        if any(not self.source_start <= item[0] <= self.source_end for item in consumed) or len(consumed) != len(set(consumed)):
            raise ValueError("invalid or duplicate source consumption")
