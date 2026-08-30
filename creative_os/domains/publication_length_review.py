from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import re

from creative_os.domains.publication_migration_model import (
    LengthIntervalKind,
    MigrationOmission,
    PublicationChapterEntry,
    PublicationLengthPolicy,
    RewriteKind,
    SourceFragment,
    length_policy_hash,
)
from creative_os.domains.publication_source_snapshot import VerifiedSourceArchiveView


_CHINESE = re.compile(r"[\u4e00-\u9fff]")
_COMPLETE_ENDING = re.compile(r"[。！？…](?:[”’」』）》】])?$")
_RULESET = "publication-length-review-v1"


class PublicationSeverity(StrEnum):
    WARNING = "warning"
    BLOCKING = "blocking"


class SourceCoverageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PublicationIssue:
    code: str
    path: str
    severity: PublicationSeverity
    evidence: tuple[str, ...]
    issue_hash: str = ""

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value.strip() for value in (self.code, self.path)):
            raise ValueError("publication_issue_identity_invalid")
        if not isinstance(self.severity, PublicationSeverity):
            raise TypeError("publication_issue_severity_required")
        if not isinstance(self.evidence, tuple) or not all(isinstance(value, str) and value for value in self.evidence):
            raise ValueError("publication_issue_evidence_required")
        expected = _digest({"code": self.code, "evidence": list(self.evidence),
                            "path": self.path, "severity": self.severity.value})
        if self.issue_hash and self.issue_hash != expected:
            raise ValueError("publication_issue_hash_mismatch")
        if not self.issue_hash:
            object.__setattr__(self, "issue_hash", expected)


@dataclass(frozen=True, slots=True)
class PublicationChapterReview:
    target_chapter: int
    body_hash: str
    chinese_character_count: int
    ruleset_version: str
    issues: tuple[PublicationIssue, ...]
    review_hash: str = ""

    def __post_init__(self) -> None:
        if type(self.target_chapter) is not int or self.target_chapter <= 0:
            raise ValueError("review_target_chapter_invalid")
        if not isinstance(self.issues, tuple) or not all(isinstance(item, PublicationIssue) for item in self.issues):
            raise TypeError("review_issues_invalid")
        expected = _digest({"body_hash": self.body_hash, "chinese_character_count": self.chinese_character_count,
                            "issues": [item.issue_hash for item in self.issues], "ruleset_version": self.ruleset_version,
                            "target_chapter": self.target_chapter})
        if self.review_hash and self.review_hash != expected:
            raise ValueError("publication_review_hash_mismatch")
        if not self.review_hash:
            object.__setattr__(self, "review_hash", expected)

    @property
    def issue_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.issues)

    @property
    def blocking_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.issues if item.severity is PublicationSeverity.BLOCKING)


def review_publication_chapter(
    entry: PublicationChapterEntry, text: str, policy: PublicationLengthPolicy, *,
    migration_id: str = "", disposition_store=None,
) -> PublicationChapterReview:
    if not isinstance(entry, PublicationChapterEntry) or not isinstance(text, str) or not isinstance(policy, PublicationLengthPolicy):
        raise TypeError("entry_text_policy_required")
    body_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    count = len(_CHINESE.findall(text))
    issues: list[PublicationIssue] = []
    if entry.body_hash != body_hash:
        issues.append(_issue("chapter_body_hash_mismatch", "body_hash", PublicationSeverity.BLOCKING,
                             entry.body_hash, body_hash))
    if count > policy.hard_max:
        issues.append(_issue("chapter_length_hard_limit", "length.chinese_characters", PublicationSeverity.BLOCKING,
                             str(count), str(policy.hard_max)))
    elif count > policy.soft_max:
        if not _has_exact_disposition(entry.length_dispositions, LengthIntervalKind.SOFT_LIMIT,
                                      entry, text, policy, migration_id, disposition_store):
            issues.append(_issue("chapter_length_disposition_missing", "length.disposition",
                                 PublicationSeverity.BLOCKING, str(count), str(policy.soft_max)))
    elif count > policy.target_max:
        issues.append(_issue("chapter_length_soft_warning", "length.chinese_characters",
                             PublicationSeverity.WARNING, str(count), str(policy.target_max)))
    elif count < policy.short_min:
        if not _has_exact_disposition(entry.short_chapter_approvals, LengthIntervalKind.SHORT_CHAPTER,
                                      entry, text, policy, migration_id, disposition_store):
            issues.append(_issue("short_chapter_approval_missing", "length.short_chapter_approval",
                                 PublicationSeverity.BLOCKING, str(count), str(policy.short_min)))
    elif count < policy.target_min:
        issues.append(_issue("chapter_length_below_target", "length.chinese_characters",
                             PublicationSeverity.WARNING, str(count), str(policy.target_min)))
    stripped = text.rstrip()
    if not stripped or _COMPLETE_ENDING.search(stripped) is None:
        issues.append(_issue("truncated_sentence_ending", "body.ending", PublicationSeverity.BLOCKING,
                             stripped[-16:] if stripped else "<empty>"))
    if entry.body_hash == body_hash and not _hook_evidence_valid(entry, text, policy):
        issues.append(_issue("ending_hook_evidence_invalid", "ending_hook_evidence",
                             PublicationSeverity.BLOCKING, entry.ending_hook))
    if entry.body_hash == body_hash:
        for index, mapping in enumerate(entry.source_mappings):
            if not _span_valid(mapping.target_span, entry, text):
                issues.append(_issue("source_mapping_evidence_invalid", f"source_mappings[{index}].target_span",
                                     PublicationSeverity.BLOCKING, mapping.source_fragment.text_hash))
        for index, outcome in enumerate(entry.dramatic_outcomes):
            if not _span_valid(outcome.outcome_evidence, entry, text):
                issues.append(_issue("dramatic_outcome_evidence_invalid", f"dramatic_outcomes[{index}].outcome_evidence",
                                     PublicationSeverity.BLOCKING, outcome.outcome_id))
    return PublicationChapterReview(entry.target_chapter, body_hash, count, _RULESET, tuple(issues))


def verify_source_coverage(
    source: VerifiedSourceArchiveView, entries: tuple[PublicationChapterEntry, ...],
    omissions: tuple[MigrationOmission, ...], *, target_texts: dict[int, str], split_plan_store=None,
    split_plan_candidate=None, archive_receipt=None, split_plan_review=None,
) -> None:
    if not isinstance(source, VerifiedSourceArchiveView):
        raise TypeError("verified_source_archive_view_required")
    if not isinstance(entries, tuple) or not all(isinstance(item, PublicationChapterEntry) for item in entries):
        raise TypeError("publication_entries_required")
    if not isinstance(omissions, tuple) or not all(isinstance(item, MigrationOmission) for item in omissions):
        raise TypeError("migration_omissions_required")
    if not entries:
        raise SourceCoverageError("publication_entries_empty")
    if not isinstance(target_texts, dict):
        raise TypeError("target_texts_required")
    source.verify_current()
    _require_split_plan_approval(split_plan_store, split_plan_candidate, archive_receipt, split_plan_review)
    expected = tuple((item.chapter_number, item.paragraph_ordinal, item.paragraph_hash)
                     for item in source.iter_paragraphs())
    consumed: list[tuple[int, int, str]] = []
    seen: set[tuple[int, int]] = set()
    previous: tuple[int, int] | None = None
    ordered_entries = tuple(sorted(entries, key=lambda item: item.target_chapter))
    if entries != ordered_entries or tuple(item.target_chapter for item in entries) != tuple(
        range(entries[0].target_chapter, entries[0].target_chapter + len(entries))
    ):
        raise SourceCoverageError("target_chapter_order_invalid")
    for entry in entries:
        target_text = target_texts.get(entry.target_chapter)
        if not isinstance(target_text, str):
            raise SourceCoverageError("target_text_missing")
        if hashlib.sha256(target_text.encode("utf-8")).hexdigest() != entry.body_hash:
            raise SourceCoverageError("target_body_hash_mismatch")
        for mapping in entry.source_mappings:
            fragment = mapping.source_fragment
            key = (fragment.source_chapter, fragment.paragraph_start)
            if fragment.paragraph_start != fragment.paragraph_end:
                raise SourceCoverageError("source_locator_invalid")
            if key in seen:
                raise SourceCoverageError("duplicate_source_fragment")
            if previous is not None and key <= previous:
                raise SourceCoverageError("source_fragment_out_of_order")
            paragraph = _load_exact(source, fragment)
            if mapping.target_span.body_hash != entry.body_hash or mapping.target_chapter != entry.target_chapter:
                raise SourceCoverageError("target_mapping_binding_invalid")
            if not _span_valid(mapping.target_span, entry, target_text):
                raise SourceCoverageError("target_mapping_evidence_invalid")
            if mapping.rewrite_kind is RewriteKind.LIGHT_REWRITE and not mapping.reason.strip():
                raise SourceCoverageError("rewrite_reason_missing")
            consumed.append((*key, paragraph.paragraph_hash))
            seen.add(key)
            previous = key
        for outcome in entry.dramatic_outcomes:
            if (not _span_valid(outcome.outcome_evidence, entry, target_text)
                    or not _span_valid(outcome.hook_evidence, entry, target_text)):
                raise SourceCoverageError("dramatic_outcome_evidence_invalid")
    _verify_candidate_entry_binding(entries, split_plan_candidate)
    approved_omissions = (*omissions, *(item for entry in entries for item in entry.omissions))
    _verify_omission_authority(approved_omissions, source, split_plan_store, split_plan_candidate,
                               archive_receipt, split_plan_review)
    for omission in approved_omissions:
        if omission.paragraph_start != omission.paragraph_end:
            raise SourceCoverageError("omission_locator_invalid")
        for ordinal in range(omission.paragraph_start, omission.paragraph_end + 1):
            key = (omission.source_chapter, ordinal)
            if key in seen:
                raise SourceCoverageError("duplicate_source_fragment")
            paragraph = source.load_paragraph(*key)
            if omission.paragraph_start == omission.paragraph_end and omission.original_text_hash != paragraph.paragraph_hash:
                raise SourceCoverageError("source_hash_mismatch")
            consumed.append((*key, paragraph.paragraph_hash))
            seen.add(key)
    if len(consumed) != len(seen):
        raise SourceCoverageError("duplicate_source_fragment")
    actual_by_key = {(chapter, ordinal): digest for chapter, ordinal, digest in consumed}
    expected_by_key = {(chapter, ordinal): digest for chapter, ordinal, digest in expected}
    wrong = next((key for key, digest in actual_by_key.items() if expected_by_key.get(key) != digest), None)
    if wrong is not None:
        raise SourceCoverageError("source_hash_or_locator_mismatch")
    if set(actual_by_key) != set(expected_by_key):
        raise SourceCoverageError("unmapped_source_fragment")
    _verify_outcomes(entries)


def _has_exact_disposition(references, kind, entry, text, policy, migration_id, store) -> bool:
    if len(references) != 1 or store is None or not migration_id:
        return False
    reference = references[0]
    if (reference.interval_kind is not kind or reference.migration_id != migration_id
            or reference.target_chapter != entry.target_chapter or reference.body_hash != entry.body_hash
            or reference.policy_hash != length_policy_hash(policy)):
        return False
    try:
        return store.require_exact(reference, text, policy) == reference
    except Exception:
        return False


def _hook_evidence_valid(entry, text, policy):
    if not entry.ending_hook_evidence:
        return False
    paragraphs = tuple(match for match in re.finditer(r"(?:\r?\n[ \t]*){2,}", text))
    last_paragraph_start = paragraphs[-1].end() if paragraphs else 0
    tail_start = max(last_paragraph_start, len(text.rstrip()) - policy.hook_tail_window_codepoints)
    for span in entry.ending_hook_evidence:
        if (not _span_valid(span, entry, text) or span.start_offset < tail_start
                or _COMPLETE_ENDING.search(span.excerpt.rstrip()) is None):
            return False
    return True


def _span_valid(span, entry, text):
    return (span.target_chapter == entry.target_chapter and span.body_hash == entry.body_hash
            and 0 <= span.start_offset < span.end_offset <= len(text)
            and text[span.start_offset:span.end_offset] == span.excerpt
            and hashlib.sha256(span.excerpt.encode("utf-8")).hexdigest() == span.excerpt_hash)


def _load_exact(source, fragment):
    try:
        paragraph = source.load_paragraph(fragment.source_chapter, fragment.paragraph_start)
    except Exception as cause:
        raise SourceCoverageError("source_locator_invalid") from cause
    if paragraph.paragraph_hash != fragment.text_hash:
        raise SourceCoverageError("source_hash_mismatch")
    return paragraph


def _verify_omission_authority(omissions, source, store, candidate, receipt, review):
    if any(value is None for value in (store, candidate, receipt, review)):
        raise SourceCoverageError("omission_approval_missing")
    try:
        decision = store.require_current_approval(candidate, receipt, review)
    except Exception as cause:
        raise SourceCoverageError("omission_approval_invalid") from cause
    approved = {}
    for planned in candidate.omissions:
        for fragment in planned.source_fragments:
            key = (fragment.source_chapter, fragment.paragraph_start, fragment.paragraph_end)
            approved[key] = (planned, fragment)
    final_keys = [(item.source_chapter, item.paragraph_start, item.paragraph_end) for item in omissions]
    if len(final_keys) != len(set(final_keys)) or set(final_keys) != set(approved):
        raise SourceCoverageError("omission_set_mismatch")
    for omission in omissions:
        key = (omission.source_chapter, omission.paragraph_start, omission.paragraph_end)
        planned = approved.get(key)
        if planned is None:
            raise SourceCoverageError("omission_not_in_approved_candidate")
        planned_omission, fragment = planned
        if (omission.original_text_hash != fragment.text_hash or omission.snapshot_hash != source.snapshot_hash
                or omission.migration_id != candidate.migration_id
                or omission.split_plan_candidate_hash != candidate.candidate_hash
                or omission.split_plan_decision_hash != decision.decision_hash
                or omission.actor != decision.actor or omission.decided_at != decision.decided_at
                or omission.reason != planned_omission.reason):
            raise SourceCoverageError("omission_approval_binding_invalid")


def _require_split_plan_approval(store, candidate, receipt, review):
    if any(value is None for value in (store, candidate, receipt, review)):
        raise SourceCoverageError("split_plan_authority_required")
    try:
        decision = store.require_current_approval(candidate, receipt, review)
    except Exception as cause:
        raise SourceCoverageError("split_plan_approval_invalid") from cause
    if not getattr(decision, "approved", False):
        raise SourceCoverageError("split_plan_not_approved")
    return decision


def dramatic_unit_hash(unit) -> str:
    """与 SplitPlan candidate canonical unit payload 一致的稳定单元标识。"""
    try:
        payload = {
            "function": unit.function, "scene_scope": list(unit.scene_scope),
            "conflict": unit.conflict, "choice_or_discovery": unit.choice_or_discovery,
            "outcome": unit.outcome, "information_reveal": unit.information_reveal,
            "technology_state": unit.technology_state, "state_shift": unit.state_shift,
            "ending_hook": unit.ending_hook,
            "source_fragments": [{"source_chapter": item.source_chapter,
                                  "paragraph_start": item.paragraph_start,
                                  "paragraph_end": item.paragraph_end, "text_hash": item.text_hash}
                                 for item in unit.source_fragments],
            "estimated_chinese_chars": unit.estimated_chinese_chars,
            "boundary_basis": unit.boundary_basis, "dialogue_closed": unit.dialogue_closed,
            "conflict_status": unit.conflict_status.value, "choice_status": unit.choice_status.value,
            "closure_evidence": [{"dimension": item.dimension.value,
                                  "source_chapter": item.source_chapter,
                                  "paragraph_ordinal": item.paragraph_ordinal,
                                  "paragraph_hash": item.paragraph_hash, "excerpt": item.excerpt,
                                  "start_offset": item.start_offset, "end_offset": item.end_offset}
                                 for item in unit.closure_evidence],
        }
    except (AttributeError, TypeError) as cause:
        raise SourceCoverageError("candidate_unit_shape_invalid") from cause
    return _digest(payload)


def _verify_candidate_entry_binding(entries, candidate):
    candidate_hash = getattr(candidate, "candidate_hash", "")
    units = getattr(candidate, "units", None)
    if not isinstance(units, tuple) or not candidate_hash:
        raise SourceCoverageError("candidate_unit_binding_invalid")
    authoritative = tuple((dramatic_unit_hash(unit), tuple(unit.source_fragments)) for unit in units)
    consumed_hashes: list[str] = []
    unit_cursor = 0
    for entry in entries:
        outcomes = entry.dramatic_outcomes
        if not outcomes or any(item.candidate_hash != candidate_hash for item in outcomes):
            raise SourceCoverageError("candidate_hash_mismatch")
        entry_hashes = tuple(item.dramatic_unit_hash for item in outcomes)
        expected_slice = authoritative[unit_cursor:unit_cursor + len(entry_hashes)]
        if entry_hashes != tuple(item[0] for item in expected_slice):
            raise SourceCoverageError("candidate_unit_order_or_identity_mismatch")
        expected_fragments = tuple(fragment for _, fragments in expected_slice for fragment in fragments)
        actual_fragments = tuple(mapping.source_fragment for mapping in entry.source_mappings)
        if actual_fragments != expected_fragments:
            raise SourceCoverageError("entry_candidate_source_group_mismatch")
        consumed_hashes.extend(entry_hashes)
        unit_cursor += len(entry_hashes)
    if unit_cursor != len(authoritative) or len(consumed_hashes) != len(set(consumed_hashes)):
        raise SourceCoverageError("candidate_unit_coverage_mismatch")


def _verify_outcomes(entries):
    prior_ids = None
    prior_units = None
    for entry in entries:
        current_ids = {item.outcome_id for item in entry.dramatic_outcomes}
        current_units = {item.dramatic_unit_hash for item in entry.dramatic_outcomes}
        if ((prior_ids is not None and current_ids & prior_ids)
                or (prior_units is not None and current_units & prior_units)):
            raise SourceCoverageError("repeated_dramatic_outcome")
        prior_ids = current_ids
        prior_units = current_units


def _issue(code, path, severity, *evidence):
    return PublicationIssue(code, path, severity, tuple(evidence))


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()
