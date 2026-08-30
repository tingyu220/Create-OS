import json
import hashlib
from dataclasses import replace

import pytest

from creative_os.domains.publication_migration_model import (
    CheckpointPhase,
    FileHashRecord,
    ManifestStatus,
    MigrationCheckpoint,
    MigrationOmission,
    PublicationChapterEntry,
    PublicationChapterMigrationManifest,
    PublicationLengthPolicy,
    SourceFragment,
    RewriteRecord,
    DramaticOutcomeBinding,
    LengthIntervalKind,
    LengthDisposition,
    RewriteKind,
    ShortChapterApproval,
    SourceToTargetMapping,
    TargetEvidenceSpan,
    migration_checkpoint_hash,
    length_policy_hash,
)
from creative_os.domains.publication_migration_codec import (
    decode_manifest,
    encode_candidate_manifest,
    encode_manifest,
    manifest_hash,
)


HASH = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def fragment(chapter=1, start=1, end=2):
    return SourceFragment(chapter, start, end, HASH)


def omission(chapter=1, start=3, end=3):
    return MigrationOmission(chapter, start, end, HASH, "重复段落")


def manifest(**changes):
    values = dict(
        migration_id="migration-1", project_id="project-1", source_edition_id="source-1", target_edition_id="target-1",
        source_start=1,
        source_end=2,
        frozen_through_chapter=0,
        entries=(PublicationChapterEntry(1, (fragment(),), ()),
                 PublicationChapterEntry(2, (fragment(2),), ())),
        omissions=(),
        length_policy=PublicationLengthPolicy(),
        checkpoints=(),
        status=ManifestStatus.CANDIDATE,
        manifest_hash="",
    )
    values.update(changes)
    value = PublicationChapterMigrationManifest(**values)
    if not value.manifest_hash:
        value = replace(value, manifest_hash=manifest_hash(value))
    return value


def test_rejects_duplicate_fragment_consumption_across_entries_and_omissions():
    with pytest.raises(ValueError):
        manifest(entries=(PublicationChapterEntry(1, (fragment(),), ()),
                          PublicationChapterEntry(2, (fragment(),), ())))
    with pytest.raises(ValueError):
        manifest(omissions=(omission(1, 1, 2),))


def test_manifest_status_has_exact_publication_lifecycle_states():
    assert {item.name for item in ManifestStatus} == {
        "CANDIDATE", "APPROVED", "REBUILT", "VERIFIED", "ACTIVATED",
    }


def test_identity_file_hash_and_rewrite_records_are_strict():
    assert FileHashRecord("chapters/a.md", HASH).relative_path == "chapters/a.md"
    with pytest.raises(ValueError):
        FileHashRecord("../a.md", HASH)
    with pytest.raises(ValueError):
        FileHashRecord("/a.md", HASH)
    with pytest.raises(ValueError):
        RewriteRecord(HASH, "B" * 64, "理由")
    with pytest.raises(ValueError):
        RewriteRecord(HASH, HASH, "")


def test_checkpoint_phase_values_and_checkpoint_contract():
    assert {item.value for item in CheckpointPhase} == {
        "snapshot_verified", "plan_approved", "content_rebuilt",
        "authority_rebuilt", "batch_verified", "activated", "failed",
    }
    checkpoint = MigrationCheckpoint("migration-1", CheckpointPhase.FAILED, "batch-1", HASH, "", "失败原因")
    assert checkpoint.error == "失败原因"
    with pytest.raises(ValueError):
        MigrationCheckpoint("migration-1", CheckpointPhase.ACTIVATED, "batch-1", HASH, "", "错误")


def bound_checkpoint(*, previous="", phase=CheckpointPhase.SNAPSHOT_VERIFIED, error=""):
    partial = MigrationCheckpoint(
        migration_id="migration-1", phase=phase, batch_id="source-1-2",
        input_fingerprint=HASH, output_fingerprint=HASH_B, error=error,
        project_id="project-1", source_edition_id="source-1", target_edition_id="target-1",
        source_start=1, source_end=2, previous_checkpoint_hash=previous,
    )
    return replace(partial, checkpoint_hash=migration_checkpoint_hash(partial))


def test_checkpoint_authority_identity_range_and_hash_are_strict():
    checkpoint = bound_checkpoint()
    assert checkpoint.checkpoint_hash == migration_checkpoint_hash(checkpoint)
    with pytest.raises(ValueError, match="checkpoint_hash"):
        replace(checkpoint, project_id="other")
    with pytest.raises(ValueError, match="source range"):
        replace(checkpoint, source_start=True)
    with pytest.raises(ValueError, match="authority identity"):
        replace(checkpoint, project_id="", checkpoint_hash="")


def test_schema_v2_checkpoint_roundtrip_chain_and_tamper():
    first = bound_checkpoint()
    second_partial = replace(
        first, phase=CheckpointPhase.PLAN_APPROVED, batch_id="source-1-2-plan",
        previous_checkpoint_hash=first.checkpoint_hash, checkpoint_hash="",
    )
    second = replace(second_partial, checkpoint_hash=migration_checkpoint_hash(second_partial))
    value = manifest(schema_version=2, entries=(mapped_entry(1), mapped_entry(2)),
                     omissions=(approved_omission(),), checkpoints=(first, second))
    assert decode_manifest(encode_manifest(value)).checkpoints == (first, second)
    wrong_partial = replace(second, previous_checkpoint_hash=HASH_C, checkpoint_hash="")
    wrong = replace(wrong_partial, checkpoint_hash=migration_checkpoint_hash(wrong_partial))
    with pytest.raises(ValueError, match="checkpoint binding or chain"):
        manifest(schema_version=2, entries=(mapped_entry(1), mapped_entry(2)),
                 omissions=(approved_omission(),), checkpoints=(first, wrong))
    payload = json.loads(encode_manifest(value))
    payload["checkpoints"][0]["source_end"] = 1
    with pytest.raises(ValueError):
        decode_manifest(json.dumps(payload, ensure_ascii=False))


def test_schema_v1_checkpoint_compatibility_is_explicit():
    legacy = MigrationCheckpoint("migration-1", CheckpointPhase.SNAPSHOT_VERIFIED, "batch-1", HASH)
    assert manifest(checkpoints=(legacy,)).schema_version == 1
    with pytest.raises(ValueError, match="v2 checkpoints"):
        manifest(checkpoints=(bound_checkpoint(),))


def test_rejects_invalid_ranges_and_hashes():
    with pytest.raises(ValueError):
        SourceFragment(0, 1, 1, HASH)
    with pytest.raises(ValueError):
        SourceFragment(1, 2, 1, HASH)
    with pytest.raises(ValueError):
        SourceFragment(1, 1, 1, "A" * 64)
    with pytest.raises(ValueError):
        manifest(source_start=2, source_end=1)


def test_rejects_target_number_gaps():
    with pytest.raises(ValueError):
        manifest(entries=(PublicationChapterEntry(1, (fragment(),), ()),
                          PublicationChapterEntry(3, (fragment(2),), ())))


def test_codec_is_canonical_and_round_trips_tuples():
    value = manifest()
    encoded = encode_manifest(value)
    assert encoded == encode_manifest(decode_manifest(encoded))
    assert isinstance(decode_manifest(encoded).entries, tuple)
    assert json.loads(encoded)["entries"][0]["source_fragments"][0]["text_hash"] == HASH


def test_codec_rejects_unknown_fields_noncanonical_values_and_tampering():
    payload = json.loads(encode_manifest(manifest()))
    payload["unexpected"] = True
    with pytest.raises(ValueError):
        decode_manifest(json.dumps(payload))


@pytest.mark.parametrize("bad_hash", [None, 0, False, {}])
def test_manifest_rejects_falsy_non_string_hashes(bad_hash):
    with pytest.raises(ValueError):
        manifest(manifest_hash=bad_hash)


def test_default_empty_hash_round_trips_without_verification():
    values = dict(
        migration_id="migration-1", project_id="project-1", source_edition_id="source-1", target_edition_id="target-1",
        source_start=1, source_end=2, frozen_through_chapter=0,
        entries=(PublicationChapterEntry(1, (fragment(),), ()),
                 PublicationChapterEntry(2, (fragment(2),), ())),
        omissions=(), length_policy=PublicationLengthPolicy(),
        checkpoints=(), status=ManifestStatus.VERIFIED, approved_by="审核人", approved_at="2026-08-28T00:00:00Z", manifest_hash="",
    )
    value = PublicationChapterMigrationManifest(**values)
    assert decode_manifest(encode_manifest(value)) == value
    payload = json.loads(encode_manifest(manifest()))
    payload["status"] = "draft "
    with pytest.raises(ValueError):
        decode_manifest(json.dumps(payload))
    payload = json.loads(encode_manifest(manifest()))
    payload["manifest_hash"] = "b" * 64
    with pytest.raises(ValueError):
        decode_manifest(json.dumps(payload))


def test_manifest_hash_excludes_own_hash_field():
    value = manifest()
    raw = json.loads(encode_manifest(value))
    raw.pop("manifest_hash")
    expected = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert manifest_hash(value) == expected


@pytest.mark.parametrize(
    "field",
    ["entries", "omissions", "checkpoints", "source_file_hashes", "frozen_file_hashes"],
)
@pytest.mark.parametrize("bad_shape", ["", {}])
def test_codec_rejects_non_list_manifest_collection_shapes(field, bad_shape):
    payload = json.loads(encode_manifest(manifest()))
    payload["manifest_hash"] = ""
    payload[field] = bad_shape

    with pytest.raises(ValueError):
        decode_manifest(json.dumps(payload))


@pytest.mark.parametrize(
    "field",
    ["source_fragments", "omissions", "rewrites", "canon_assertions"],
)
@pytest.mark.parametrize("bad_shape", ["", {}])
def test_codec_rejects_non_list_entry_collection_shapes(field, bad_shape):
    payload = json.loads(encode_manifest(manifest()))
    payload["manifest_hash"] = ""
    payload["entries"][0][field] = bad_shape

    with pytest.raises(ValueError):
        decode_manifest(json.dumps(payload))


@pytest.mark.parametrize(
    ("status", "approved_by", "approved_at"),
    [
        ("candidate", None, ""),
        ("candidate", "", None),
        ("approved", None, "2026-08-28T00:00:00Z"),
        ("approved", "审核人", None),
    ],
)
def test_codec_rejects_non_string_approval_metadata(status, approved_by, approved_at):
    payload = json.loads(encode_manifest(manifest()))
    payload["manifest_hash"] = ""
    payload["status"] = status
    payload["approved_by"] = approved_by
    payload["approved_at"] = approved_at

    with pytest.raises(ValueError):
        decode_manifest(json.dumps(payload))


def test_codec_rejects_bytes_payload():
    payload = encode_manifest(manifest()).encode("utf-8")

    with pytest.raises(ValueError):
        decode_manifest(payload)


def target_span(chapter=1, start=0, excerpt="钩子"):
    return TargetEvidenceSpan(
        target_chapter=chapter,
        start_offset=start,
        end_offset=start + len(excerpt),
        excerpt=excerpt,
        excerpt_hash=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        body_hash=HASH_B,
    )


def short_approval(chapter=1):
    return ShortChapterApproval(
        disposition_id=f"short-{chapter}", decision_hash=HASH_C, record_sequence=3,
        migration_id="migration-1",
        target_chapter=chapter,
        body_hash=HASH_B,
        policy_hash=length_policy_hash(PublicationLengthPolicy()),
        interval_kind=LengthIntervalKind.SHORT_CHAPTER,
        actor="总控",
        reason="独立强钩子短章",
        decided_at="2026-08-28T12:00:00+00:00",
    )


def soft_disposition(chapter=1):
    return LengthDisposition(
        disposition_id=f"soft-{chapter}", decision_hash=HASH_C, record_sequence=3,
        migration_id="migration-1", target_chapter=chapter, body_hash=HASH_B,
        policy_hash=length_policy_hash(PublicationLengthPolicy()),
        interval_kind=LengthIntervalKind.SOFT_LIMIT,
        actor="总控", reason="高潮收束需要", decided_at="2026-08-28T12:00:00+00:00",
    )


def mapped_entry(chapter=1):
    source = fragment(chapter, 1, 1)
    span = target_span(chapter)
    mapping = SourceToTargetMapping(
        source_fragment=source,
        target_chapter=chapter,
        target_span=span,
        rewrite_kind=RewriteKind.LIGHT_REWRITE,
        reason="压缩重复说明",
    )
    outcome = DramaticOutcomeBinding(
        outcome_id=f"outcome-{chapter}",
        dramatic_unit_hash=HASH,
        candidate_hash=HASH_C,
        target_chapter=chapter,
        outcome_evidence=target_span(chapter, 2, "结果"),
        hook_evidence=target_span(chapter, 4, "悬念"),
    )
    return PublicationChapterEntry(
        chapter,
        (source,),
        (),
        body_hash=HASH_B,
        source_mappings=(mapping,),
        ending_hook_evidence=(outcome.hook_evidence,),
        short_chapter_approvals=(short_approval(chapter),),
        dramatic_outcomes=(outcome,),
        schema_version=2,
    )


def test_target_evidence_span_binds_unicode_offsets_excerpt_and_body():
    span = target_span(start=2, excerpt="临界点")
    assert span.end_offset - span.start_offset == len("临界点")
    with pytest.raises(ValueError, match="evidence span"):
        replace(span, end_offset=span.end_offset + 1)
    with pytest.raises(ValueError, match="excerpt_hash"):
        replace(span, excerpt_hash=HASH)
    with pytest.raises(ValueError, match="evidence span"):
        replace(span, start_offset=True)
    assert replace(span, target_chapter=2).target_chapter == 2


def test_length_disposition_only_references_future_task5_authority():
    approval = short_approval()
    assert approval.decision_hash == HASH_C
    assert approval.disposition_id == "short-1"
    assert not hasattr(ShortChapterApproval, "approve")
    assert not hasattr(approval, "split_plan_candidate_hash")
    with pytest.raises(ValueError, match="decision_hash"):
        replace(approval, decision_hash="")
    with pytest.raises((TypeError, ValueError)):
        replace(approval, record_sequence=True)
    with pytest.raises(ValueError, match="decided_at"):
        replace(approval, decided_at="2026-08-28T12:00:00")


def test_source_mapping_requires_single_paragraph_ordered_non_overlapping_target_spans():
    entry = mapped_entry()
    with pytest.raises(ValueError, match="single source paragraph"):
        replace(entry.source_mappings[0], source_fragment=fragment(1, 1, 2))
    second_source = fragment(1, 2, 2)
    overlap = replace(entry.source_mappings[0], source_fragment=second_source,
                      target_span=target_span(1, 0, "另一段"))
    with pytest.raises(ValueError, match="mapping order"):
        replace(entry, source_fragments=(entry.source_fragments[0], second_source),
                source_mappings=(entry.source_mappings[0], overlap))
    with pytest.raises(ValueError, match="source mapping coverage"):
        replace(entry, source_mappings=())


def test_verbatim_mapping_requires_exact_utf8_source_and_target_hash():
    excerpt = "逐字保留"
    exact = SourceFragment(1, 1, 1, hashlib.sha256(excerpt.encode("utf-8")).hexdigest())
    SourceToTargetMapping(exact, 1, target_span(1, 0, excerpt), RewriteKind.VERBATIM)
    with pytest.raises(ValueError, match="verbatim source"):
        SourceToTargetMapping(fragment(1, 1, 1), 1, target_span(1, 0, excerpt), RewriteKind.VERBATIM)


def test_dramatic_outcome_binds_candidate_unit_outcome_and_hook_evidence():
    binding = mapped_entry().dramatic_outcomes[0]
    assert binding.hook_evidence.target_chapter == binding.target_chapter
    with pytest.raises(ValueError, match="target chapter"):
        replace(binding, hook_evidence=target_span(2))
    with pytest.raises(ValueError, match="outcome_id"):
        replace(binding, outcome_id="")
    with pytest.raises(ValueError, match="hook evidence mismatch"):
        replace(mapped_entry(), ending_hook_evidence=(target_span(1, 10, "另一个钩子"),))
    with pytest.raises(ValueError, match="duplicate ending hook evidence"):
        replace(mapped_entry(), ending_hook_evidence=(binding.hook_evidence, binding.hook_evidence))
    duplicate = replace(binding, outcome_id="另一个结果")
    with pytest.raises(ValueError, match="duplicate dramatic outcome binding"):
        replace(mapped_entry(), dramatic_outcomes=(binding, duplicate))


def test_length_disposition_is_unique_and_short_long_are_mutually_exclusive():
    entry = mapped_entry()
    with pytest.raises(ValueError, match="conflicting length disposition"):
        replace(entry, length_dispositions=(soft_disposition(),))
    with pytest.raises(ValueError, match="conflicting length disposition"):
        replace(entry, short_chapter_approvals=(short_approval(), short_approval()))


def approved_omission():
    return MigrationOmission(
        source_chapter=1,
        paragraph_start=2,
        paragraph_end=2,
        original_text_hash=HASH,
        reason="重复段落",
        snapshot_hash=HASH_B,
        migration_id="migration-1",
        split_plan_candidate_hash=HASH,
        split_plan_decision_hash=HASH_C,
        actor="总控",
        decided_at="2026-08-28T12:00:00+00:00",
    )


def test_migration_omission_has_exact_identity_and_approval_binding():
    value = approved_omission()
    assert value.split_plan_candidate_hash == HASH
    assert value.split_plan_decision_hash == HASH_C
    assert not hasattr(value, "split_plan_decision_record_id")
    with pytest.raises(ValueError, match="split_plan_decision_hash"):
        replace(value, split_plan_decision_hash="C" * 64)
    with pytest.raises(ValueError, match="approval metadata"):
        replace(value, actor="")


def test_schema_v2_codec_roundtrip_hash_and_tamper_cover_new_fields():
    value = manifest(
        schema_version=2,
        entries=(mapped_entry(1), mapped_entry(2)),
        omissions=(approved_omission(),),
    )
    encoded = encode_manifest(value)
    decoded = decode_manifest(encoded)
    assert decoded == value
    assert isinstance(decoded.entries[0].source_mappings, tuple)
    assert isinstance(decoded.entries[0].ending_hook_evidence, tuple)
    assert json.loads(encoded)["schema_version"] == 2
    payload = json.loads(encoded)
    payload["entries"][0]["ending_hook_evidence"][0]["excerpt"] = "篡改"
    with pytest.raises(ValueError):
        decode_manifest(json.dumps(payload, ensure_ascii=False))


def test_schema_v2_persisted_codec_requires_hash_but_candidate_encoding_is_explicit():
    value = PublicationChapterMigrationManifest(
        migration_id="migration-1", project_id="project-1", source_edition_id="source-1",
        target_edition_id="target-1", source_start=1, source_end=2,
        frozen_through_chapter=0, entries=(mapped_entry(1), mapped_entry(2)),
        omissions=(approved_omission(),), length_policy=PublicationLengthPolicy(),
        checkpoints=(), status=ManifestStatus.CANDIDATE, schema_version=2,
    )
    with pytest.raises(ValueError, match="requires manifest_hash"):
        encode_manifest(value)
    candidate_payload = encode_candidate_manifest(value)
    assert json.loads(candidate_payload)["document_kind"] == "publication_migration_candidate"
    with pytest.raises(ValueError, match="invalid manifest"):
        decode_manifest(candidate_payload)
    wrong = replace(value, manifest_hash=HASH)
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        encode_manifest(wrong)


def test_length_authority_reference_must_bind_entry_body_chapter_and_policy():
    entry = mapped_entry()
    with pytest.raises(ValueError, match="target binding"):
        replace(entry, short_chapter_approvals=(replace(short_approval(), body_hash=HASH_C),))
    with pytest.raises(ValueError, match="policy_hash"):
        replace(short_approval(), policy_hash="")


@pytest.mark.parametrize("schema_version", [True, False, 2.0, "2"])
def test_schema_versions_reject_bool_and_non_integer_types(schema_version):
    with pytest.raises(ValueError, match="schema"):
        replace(mapped_entry(), schema_version=schema_version)


@pytest.mark.parametrize(
    "field",
    ["source_mappings", "ending_hook_evidence", "length_dispositions",
     "short_chapter_approvals", "dramatic_outcomes"],
)
def test_schema_v2_codec_rejects_non_list_tuple_field_shapes(field):
    value = manifest(schema_version=2, entries=(mapped_entry(1), mapped_entry(2)),
                     omissions=(approved_omission(),))
    payload = json.loads(encode_manifest(value))
    payload["manifest_hash"] = ""
    payload["entries"][0][field] = {}
    with pytest.raises(ValueError):
        decode_manifest(json.dumps(payload, ensure_ascii=False))


def test_legacy_v1_is_explicit_and_cannot_smuggle_v2_fields():
    legacy = manifest()
    payload = json.loads(encode_manifest(legacy))
    assert "schema_version" not in payload
    assert decode_manifest(encode_manifest(legacy)).schema_version == 1
    with pytest.raises(ValueError, match="schema v1"):
        replace(legacy.entries[0], ending_hook_evidence=(target_span(),))
    payload["schema_version"] = 1
    with pytest.raises(ValueError):
        decode_manifest(json.dumps(payload))
def test_length_policy_binds_explicit_hook_tail_window_and_rejects_bool():
    base = PublicationLengthPolicy()
    changed = PublicationLengthPolicy(hook_tail_window_codepoints=900)
    assert base.hook_tail_window_codepoints == 800
    assert length_policy_hash(base) != length_policy_hash(changed)
    with pytest.raises(ValueError, match="invalid length policy"):
        PublicationLengthPolicy(hook_tail_window_codepoints=True)
