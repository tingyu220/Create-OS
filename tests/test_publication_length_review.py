from __future__ import annotations

from dataclasses import replace
import hashlib
from types import SimpleNamespace

import pytest

from creative_os.domains.publication_length_review import (
    SourceCoverageError,
    dramatic_unit_hash,
    review_publication_chapter,
    verify_source_coverage,
)
from creative_os.domains.publication_migration_model import (
    DramaticOutcomeBinding,
    LengthIntervalKind,
    MigrationOmission,
    PublicationChapterEntry,
    PublicationLengthPolicy,
    RewriteKind,
    SourceFragment,
    SourceToTargetMapping,
    TargetEvidenceSpan,
)
from creative_os.domains.publication_source_snapshot import (
    build_source_snapshot,
    copy_verified_source_archive,
    load_verified_archive,
)
from creative_os.runtime.publication_length_disposition_store import PublicationLengthDispositionStore


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _entry(text: str, *, chapter: int = 5, source: SourceFragment | None = None,
           disposition=(), short=(), outcome_id: str = "outcome-1",
           candidate_hash: str | None = None, unit_hash: str | None = None) -> PublicationChapterEntry:
    source = source or SourceFragment(5, 1, 1, _sha(text))
    body_hash = _sha(text)
    hook_text = text[-2:]
    hook = TargetEvidenceSpan(chapter, len(text) - 2, len(text), hook_text, _sha(hook_text), body_hash)
    outcome_text = text[-3:-2]
    outcome = TargetEvidenceSpan(chapter, len(text) - 3, len(text) - 2, outcome_text, _sha(outcome_text), body_hash)
    mapping_span = TargetEvidenceSpan(chapter, 0, len(text), text, body_hash, body_hash)
    return PublicationChapterEntry(
        target_chapter=chapter, source_fragments=(source,), title="标题", body_hash=body_hash,
        chapter_function="推进", turning_point="选择", ending_hook="悬念",
        contract_id="contract", state_receipt_id="state", schema_version=2,
        source_mappings=(SourceToTargetMapping(source, chapter, mapping_span, RewriteKind.LIGHT_REWRITE, "轻度重写"),),
        ending_hook_evidence=(hook,), length_dispositions=tuple(disposition),
        short_chapter_approvals=tuple(short),
        dramatic_outcomes=(DramaticOutcomeBinding(outcome_id, unit_hash or _sha("unit:" + outcome_id),
                                                   candidate_hash or _sha("candidate:" + outcome_id), chapter, outcome, hook),),
    )


@pytest.mark.parametrize(("count", "code"), [(5501, "chapter_length_hard_limit"), (2500, "chapter_length_below_target"), (4501, "chapter_length_soft_warning")])
def test_length_intervals_are_deterministic(count, code):
    text = "文" * count + "。"
    review = review_publication_chapter(_entry(text), text, PublicationLengthPolicy())
    assert code in review.issue_codes


@pytest.mark.parametrize(("count", "expected"), [
    (2499, "short_chapter_approval_missing"), (2500, "chapter_length_below_target"),
    (2999, "chapter_length_below_target"), (3000, None), (4500, None),
    (4501, "chapter_length_soft_warning"), (5000, "chapter_length_soft_warning"),
    (5001, "chapter_length_disposition_missing"), (5500, "chapter_length_disposition_missing"),
    (5501, "chapter_length_hard_limit"),
])
def test_all_length_policy_boundaries(count, expected):
    text = "文" * count + "。"
    review = review_publication_chapter(_entry(text), text, PublicationLengthPolicy())
    length_codes = {code for code in review.issue_codes if code.startswith("chapter_length") or code.startswith("short_chapter")}
    assert length_codes == ({expected} if expected else set())


def test_5001_to_5500_requires_exact_persisted_disposition(tmp_path):
    text = "文" * 5001 + "。"
    entry = _entry(text)
    store = PublicationLengthDispositionStore(tmp_path)
    decision = store.append_decision("migration-1", 5, text, PublicationLengthPolicy(),
                                     "editor", "完整高潮",
                                     decided_at="2026-08-28T10:00:00+08:00")
    approved = replace(entry, length_dispositions=(decision,))
    assert "chapter_length_disposition_missing" not in review_publication_chapter(
        approved, text, PublicationLengthPolicy(), migration_id="migration-1", disposition_store=store,
    ).blocking_codes
    forged = replace(decision, disposition_id="forged")
    forged_review = review_publication_chapter(
        replace(entry, length_dispositions=(forged,)), text, PublicationLengthPolicy(),
        migration_id="migration-1", disposition_store=store,
    )
    assert "chapter_length_disposition_missing" in forged_review.blocking_codes


def test_short_chapter_requires_exact_short_approval(tmp_path):
    text = "文" * 2000 + "。"
    entry = _entry(text)
    store = PublicationLengthDispositionStore(tmp_path)
    missing = review_publication_chapter(entry, text, PublicationLengthPolicy(), migration_id="migration-1", disposition_store=store)
    assert "short_chapter_approval_missing" in missing.blocking_codes
    decision = store.append_decision("migration-1", 5, text, PublicationLengthPolicy(),
                                     "editor", "独立强钩子",
                                     decided_at="2026-08-28T10:00:00+08:00")
    assert not review_publication_chapter(replace(entry, short_chapter_approvals=(decision,)), text,
        PublicationLengthPolicy(), migration_id="migration-1", disposition_store=store).blocking_codes


def test_review_binds_body_hook_span_and_complete_sentence():
    text = "文" * 3000 + "。"
    entry = _entry(text)
    assert not review_publication_chapter(entry, text, PublicationLengthPolicy()).blocking_codes
    assert "chapter_body_hash_mismatch" in review_publication_chapter(entry, text + "篡", PublicationLengthPolicy()).blocking_codes
    truncated = text[:-1] + "，"
    assert "truncated_sentence_ending" in review_publication_chapter(_entry(truncated), truncated, PublicationLengthPolicy()).blocking_codes


def test_review_rejects_hook_span_that_does_not_resolve_against_body():
    text = "文" * 3000 + "。"
    entry = _entry(text)
    old = entry.ending_hook_evidence[0]
    shifted = replace(old, start_offset=old.start_offset - 1, end_offset=old.end_offset - 1)
    outcome = replace(entry.dramatic_outcomes[0], hook_evidence=shifted)
    tampered = replace(entry, ending_hook_evidence=(shifted,), dramatic_outcomes=(outcome,))
    assert "ending_hook_evidence_invalid" in review_publication_chapter(
        tampered, text, PublicationLengthPolicy(),
    ).blocking_codes


def test_review_rejects_forged_mapping_and_outcome_spans():
    text = "文" * 3000 + "。"
    entry = _entry(text)
    mapping_span = replace(entry.source_mappings[0].target_span, start_offset=1, end_offset=len(text) + 1)
    forged_mapping = replace(entry.source_mappings[0], target_span=mapping_span)
    mapped = replace(entry, source_mappings=(forged_mapping,))
    assert "source_mapping_evidence_invalid" in review_publication_chapter(mapped, text, PublicationLengthPolicy()).blocking_codes
    evidence = entry.dramatic_outcomes[0].outcome_evidence
    forged_evidence = replace(evidence, start_offset=len(text) - 1, end_offset=len(text))
    outcome = replace(entry.dramatic_outcomes[0], outcome_evidence=forged_evidence)
    assert "dramatic_outcome_evidence_invalid" in review_publication_chapter(
        replace(entry, dramatic_outcomes=(outcome,)), text, PublicationLengthPolicy(),
    ).blocking_codes


def test_review_allows_result_itself_to_be_the_exact_hook():
    text = "文" * 3000 + "。"
    entry = _entry(text)
    outcome = replace(entry.dramatic_outcomes[0], outcome_evidence=entry.ending_hook_evidence[0])
    assert not review_publication_chapter(
        replace(entry, dramatic_outcomes=(outcome,)), text, PublicationLengthPolicy(),
    ).blocking_codes


def _source(tmp_path):
    chapters = tmp_path / "production/final_chapters"
    chapters.mkdir(parents=True)
    for number in range(1, 33):
        (chapters / f"chapter_{number:03}.md").write_text(f"第{number}章甲。\n\n第{number}章乙。", encoding="utf-8")
    snapshot = build_source_snapshot(tmp_path, 4, range(5, 33))
    receipt = copy_verified_source_archive(snapshot, tmp_path)
    return load_verified_archive(receipt, tmp_path)


def _coverage_entries(view):
    entries = []
    target = 5
    for paragraph in view.iter_paragraphs():
        text = paragraph.text if paragraph.text.endswith("。") else paragraph.text + "。"
        fragment = SourceFragment(paragraph.chapter_number, paragraph.paragraph_ordinal,
                                  paragraph.paragraph_ordinal, paragraph.paragraph_hash)
        outcome_id = f"outcome-{target}"
        unit = _unit(fragment, outcome_id)
        entries.append(_entry(text, chapter=target, source=fragment, outcome_id=outcome_id,
                              candidate_hash="d" * 64, unit_hash=dramatic_unit_hash(unit)))
        target += 1
    return tuple(entries)


class _Decision:
    approved = True
    decision_hash = "e" * 64
    actor = "editor"
    decided_at = "2026-08-28T10:00:00+08:00"


class _ApprovalStore:
    def require_current_approval(self, candidate, receipt, review):
        return _Decision()


def _unit(fragment, outcome_id):
    resolved = SimpleNamespace(value="resolved")
    return SimpleNamespace(
        function="推进", scene_scope=("场景",), conflict="冲突", choice_or_discovery="选择",
        outcome=outcome_id, information_reveal="揭示", technology_state="状态", state_shift="变化",
        ending_hook="钩子", source_fragments=(fragment,), estimated_chinese_chars=3000,
        boundary_basis="dramatic_turn", dialogue_closed=True, conflict_status=resolved,
        choice_status=resolved, closure_evidence=(),
    )


def _candidate_for(entries, omissions=()):
    return SimpleNamespace(
        migration_id="migration-1", candidate_hash="d" * 64, omissions=omissions,
        units=tuple(_unit(entry.source_fragments[0], entry.dramatic_outcomes[0].outcome_id) for entry in entries),
    )


def _verify(view, entries, omissions=(), candidate=None):
    return verify_source_coverage(
        view, entries, omissions, target_texts={item.target_chapter: item.source_mappings[0].target_span.excerpt for item in entries},
        split_plan_store=_ApprovalStore(), split_plan_candidate=candidate or _candidate_for(entries),
        archive_receipt=object(), split_plan_review=object(),
    )


def test_source_coverage_accepts_exact_mapping_and_blocks_missing_duplicate_order(tmp_path):
    view = _source(tmp_path)
    entries = _coverage_entries(view)
    _verify(view, entries)
    with pytest.raises(SourceCoverageError, match="unmapped_source_fragment"):
        _verify(view, entries[:-1])
    duplicate_mapping = replace(entries[-1].source_mappings[0], source_fragment=entries[0].source_fragments[0])
    duplicate_entry = replace(entries[-1], source_fragments=(entries[0].source_fragments[0],),
                              source_mappings=(duplicate_mapping,))
    with pytest.raises(SourceCoverageError, match="duplicate_source_fragment"):
        _verify(view, (*entries[:-1], duplicate_entry))
    first_mapping = replace(entries[0].source_mappings[0], source_fragment=entries[1].source_fragments[0])
    second_mapping = replace(entries[1].source_mappings[0], source_fragment=entries[0].source_fragments[0])
    first = replace(entries[0], source_fragments=(entries[1].source_fragments[0],), source_mappings=(first_mapping,))
    second = replace(entries[1], source_fragments=(entries[0].source_fragments[0],), source_mappings=(second_mapping,))
    with pytest.raises(SourceCoverageError, match="source_fragment_out_of_order"):
        _verify(view, (first, second, *entries[2:]))


def test_repeated_structured_outcome_is_blocked_but_distinct_recap_is_allowed(tmp_path):
    view = _source(tmp_path)
    entries = list(_coverage_entries(view))
    repeated_id = "outcome-5"
    repeated_unit = _unit(entries[1].source_fragments[0], repeated_id)
    entries[1] = replace(entries[1], dramatic_outcomes=(replace(
        entries[1].dramatic_outcomes[0], outcome_id=repeated_id,
        dramatic_unit_hash=dramatic_unit_hash(repeated_unit),
    ),))
    with pytest.raises(SourceCoverageError, match="repeated_dramatic_outcome"):
        _verify(view, tuple(entries))
    _verify(view, _coverage_entries(view))


def test_source_coverage_rejects_empty_entries_and_missing_target_text(tmp_path):
    view = _source(tmp_path)
    with pytest.raises(SourceCoverageError, match="publication_entries_empty"):
        _verify(view, ())
    with pytest.raises(SourceCoverageError, match="target_text_missing"):
        verify_source_coverage(view, _coverage_entries(view), (), target_texts={},
            split_plan_store=_ApprovalStore(), split_plan_candidate=_candidate_for(_coverage_entries(view)),
            archive_receipt=object(), split_plan_review=object())


def test_same_dramatic_unit_is_rejected_even_when_candidate_hash_changes(tmp_path):
    view = _source(tmp_path)
    entries = list(_coverage_entries(view))
    prior = entries[0].dramatic_outcomes[0]
    current = entries[1].dramatic_outcomes[0]
    entries[1] = replace(entries[1], dramatic_outcomes=(replace(
        current, dramatic_unit_hash=prior.dramatic_unit_hash, candidate_hash="f" * 64,
    ),))
    with pytest.raises(SourceCoverageError, match="candidate_hash_mismatch"):
        _verify(view, tuple(entries))


@pytest.mark.parametrize("mutation", ["unknown_unit", "missing_unit", "wrong_group"])
def test_entries_must_exactly_cover_current_candidate_units_and_source_groups(tmp_path, mutation):
    view = _source(tmp_path)
    entries = list(_coverage_entries(view))
    candidate = _candidate_for(tuple(entries))
    if mutation == "unknown_unit":
        entries[0] = replace(entries[0], dramatic_outcomes=(replace(
            entries[0].dramatic_outcomes[0], dramatic_unit_hash="f" * 64,
        ),))
    elif mutation == "missing_unit":
        candidate = replace(candidate, units=(*candidate.units, candidate.units[-1])) if hasattr(candidate, "__dataclass_fields__") else SimpleNamespace(
            migration_id=candidate.migration_id, candidate_hash=candidate.candidate_hash,
            omissions=candidate.omissions, units=(*candidate.units, candidate.units[-1]),
        )
    else:
        first, second = entries[:2]
        first_mapping = replace(first.source_mappings[0], source_fragment=second.source_fragments[0])
        entries[0] = replace(first, source_fragments=(second.source_fragments[0],), source_mappings=(first_mapping,))
    with pytest.raises(SourceCoverageError):
        _verify(view, tuple(entries), candidate=candidate)


def test_final_omission_set_must_exactly_match_current_approved_candidate(tmp_path):
    view = _source(tmp_path)
    entries = _coverage_entries(view)[1:]
    paragraph = view.iter_paragraphs()[0]
    fragment = SourceFragment(paragraph.chapter_number, paragraph.paragraph_ordinal,
                              paragraph.paragraph_ordinal, paragraph.paragraph_hash)
    planned = SimpleNamespace(source_fragments=(fragment,), reason="删除重复说明", evidence="重复证明", impact="无Canon影响")
    candidate = _candidate_for(entries, (planned,))
    omission = MigrationOmission(fragment.source_chapter, fragment.paragraph_start, fragment.paragraph_end,
        fragment.text_hash, planned.reason, view.snapshot_hash, "migration-1", "d" * 64, "e" * 64,
        "editor", "2026-08-28T10:00:00+08:00")
    _verify(view, entries, (omission,), candidate)
    with pytest.raises(SourceCoverageError, match="omission_set_mismatch"):
        _verify(view, entries, (), candidate)
