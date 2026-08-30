from __future__ import annotations

import hashlib
import json
from typing import Any

from creative_os.domains.publication_migration_model import (
    CheckpointPhase,
    DramaticOutcomeBinding,
    FileHashRecord,
    LengthIntervalKind,
    LengthDisposition,
    ManifestStatus,
    MigrationCheckpoint,
    MigrationOmission,
    PublicationChapterEntry,
    PublicationChapterMigrationManifest,
    PublicationLengthPolicy,
    RewriteKind,
    RewriteRecord,
    ShortChapterApproval,
    SourceFragment,
    SourceToTargetMapping,
    TargetEvidenceSpan,
)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def encode_manifest(manifest: PublicationChapterMigrationManifest) -> str:
    if not isinstance(manifest, PublicationChapterMigrationManifest):
        raise TypeError("manifest is required")
    if manifest.schema_version == 2 and not manifest.manifest_hash:
        raise ValueError("persisted schema v2 manifest requires manifest_hash")
    if manifest.schema_version == 2 and manifest.manifest_hash != manifest_hash(manifest):
        raise ValueError("manifest hash mismatch")
    return _canonical(_manifest_body(manifest, with_hash=True))


def encode_candidate_manifest(manifest: PublicationChapterMigrationManifest) -> str:
    """仅编码尚未持久化的候选；不赋予审批或持久化语义。"""
    if not isinstance(manifest, PublicationChapterMigrationManifest):
        raise TypeError("manifest is required")
    if manifest.schema_version != 2 or manifest.status is not ManifestStatus.CANDIDATE or manifest.manifest_hash:
        raise ValueError("candidate encoder requires an unhashed schema v2 candidate")
    payload = _manifest_body(manifest, with_hash=True)
    payload["document_kind"] = "publication_migration_candidate"
    return _canonical(payload)


def manifest_hash(manifest: PublicationChapterMigrationManifest) -> str:
    return hashlib.sha256(_canonical(_manifest_body(manifest, with_hash=False)).encode("utf-8")).hexdigest()


def _fragment(value: SourceFragment) -> dict[str, object]:
    return {"paragraph_end": value.paragraph_end, "paragraph_start": value.paragraph_start,
            "source_chapter": value.source_chapter, "text_hash": value.text_hash}


def _span(value: TargetEvidenceSpan) -> dict[str, object]:
    return {"body_hash": value.body_hash, "end_offset": value.end_offset,
            "excerpt": value.excerpt, "excerpt_hash": value.excerpt_hash,
            "start_offset": value.start_offset, "target_chapter": value.target_chapter}


def _omission(value: MigrationOmission, schema_version: int) -> dict[str, object]:
    payload = {"original_text_hash": value.original_text_hash, "paragraph_end": value.paragraph_end,
               "paragraph_start": value.paragraph_start, "reason": value.reason,
               "source_chapter": value.source_chapter}
    if schema_version == 2:
        payload.update({"actor": value.actor,
                        "decided_at": value.decided_at, "migration_id": value.migration_id,
                        "snapshot_hash": value.snapshot_hash,
                        "split_plan_candidate_hash": value.split_plan_candidate_hash,
                        "split_plan_decision_hash": value.split_plan_decision_hash})
    return payload


def _entry(value: PublicationChapterEntry, schema_version: int) -> dict[str, object]:
    payload: dict[str, object] = {
        "body_hash": value.body_hash,
        "canon_assertions": list(value.canon_assertions),
        "chapter_function": value.chapter_function,
        "contract_id": value.contract_id,
        "ending_hook": value.ending_hook,
        "omissions": [_omission(item, schema_version) for item in value.omissions],
        "rewrites": [{"reason": item.reason, "rewritten_text_hash": item.rewritten_text_hash,
                      "source_text_hash": item.source_text_hash} for item in value.rewrites],
        "source_fragments": [_fragment(item) for item in value.source_fragments],
        "state_receipt_id": value.state_receipt_id,
        "target_chapter": value.target_chapter,
        "title": value.title,
        "turning_point": value.turning_point,
    }
    if schema_version == 2:
        payload.update({
            "dramatic_outcomes": [{"candidate_hash": item.candidate_hash,
                                   "dramatic_unit_hash": item.dramatic_unit_hash,
                                   "hook_evidence": _span(item.hook_evidence),
                                   "outcome_evidence": _span(item.outcome_evidence),
                                   "outcome_id": item.outcome_id,
                                   "target_chapter": item.target_chapter}
                                  for item in value.dramatic_outcomes],
            "ending_hook_evidence": [_span(item) for item in value.ending_hook_evidence],
            "length_dispositions": [_length_projection(item) for item in value.length_dispositions],
            "short_chapter_approvals": [_length_projection(item) for item in value.short_chapter_approvals],
            "schema_version": 2,
            "source_mappings": [{"reason": item.reason,
                                 "rewrite_kind": item.rewrite_kind.value,
                                 "source_fragment": _fragment(item.source_fragment),
                                 "target_chapter": item.target_chapter,
                                 "target_span": _span(item.target_span)}
                                for item in value.source_mappings],
        })
    return payload


def _length_projection(item: LengthDisposition | ShortChapterApproval) -> dict[str, object]:
    return {"actor": item.actor, "body_hash": item.body_hash, "decided_at": item.decided_at,
            "decision_hash": item.decision_hash, "disposition_id": item.disposition_id,
            "interval_kind": item.interval_kind.value, "migration_id": item.migration_id,
            "policy_hash": item.policy_hash, "reason": item.reason,
            "record_sequence": item.record_sequence,
            "target_chapter": item.target_chapter}


def _manifest_body(manifest: PublicationChapterMigrationManifest, with_hash: bool) -> dict[str, object]:
    version = manifest.schema_version
    payload: dict[str, object] = {
        "approved_at": manifest.approved_at,
        "approved_by": manifest.approved_by,
        "checkpoints": [_checkpoint_payload(item, version) for item in manifest.checkpoints],
        "entries": [_entry(item, version) for item in manifest.entries],
        "frozen_file_hashes": [{"content_hash": item.content_hash,
                                "relative_path": item.relative_path}
                               for item in manifest.frozen_file_hashes],
        "frozen_through_chapter": manifest.frozen_through_chapter,
        "length_policy": {"hard_max": manifest.length_policy.hard_max,
                          "hook_tail_window_codepoints": manifest.length_policy.hook_tail_window_codepoints,
                          "short_min": manifest.length_policy.short_min,
                          "soft_max": manifest.length_policy.soft_max,
                          "target_max": manifest.length_policy.target_max,
                          "target_min": manifest.length_policy.target_min},
        "migration_id": manifest.migration_id,
        "omissions": [_omission(item, version) for item in manifest.omissions],
        "project_id": manifest.project_id,
        "source_edition_id": manifest.source_edition_id,
        "source_end": manifest.source_end,
        "source_file_hashes": [{"content_hash": item.content_hash,
                                "relative_path": item.relative_path}
                               for item in manifest.source_file_hashes],
        "source_start": manifest.source_start,
        "status": manifest.status.value,
        "target_edition_id": manifest.target_edition_id,
    }
    if version == 2:
        payload["schema_version"] = 2
    if with_hash:
        payload["manifest_hash"] = manifest.manifest_hash
    return payload


def decode_manifest(payload: str) -> PublicationChapterMigrationManifest:
    if type(payload) is not str:
        raise ValueError("invalid manifest")
    try:
        raw = json.loads(payload, object_pairs_hook=_strict_object)
        if not isinstance(raw, dict):
            raise ValueError("invalid manifest")
        version = 2 if raw.get("schema_version") == 2 else 1
        if "schema_version" in raw and version != 2:
            raise ValueError("invalid schema version")
        if version == 2 and (not isinstance(raw.get("manifest_hash"), str) or not raw["manifest_hash"]):
            raise ValueError("persisted schema v2 manifest requires manifest_hash")
        value = _decode_manifest(raw, version)
    except (KeyError, TypeError, ValueError) as cause:
        raise ValueError("invalid manifest") from cause
    if value.manifest_hash and value.manifest_hash != manifest_hash(value):
        raise ValueError("manifest hash mismatch")
    return value


def _decode_manifest(raw: dict[str, object], version: int) -> PublicationChapterMigrationManifest:
    keys = {"approved_at", "approved_by", "checkpoints", "entries", "frozen_file_hashes",
            "frozen_through_chapter", "length_policy", "manifest_hash", "migration_id",
            "omissions", "project_id", "source_edition_id", "source_end",
            "source_file_hashes", "source_start", "status", "target_edition_id"}
    if version == 2:
        keys.add("schema_version")
    _fields(raw, keys)
    policy_raw = _fields(raw["length_policy"], {"hard_max", "hook_tail_window_codepoints", "short_min", "soft_max", "target_max", "target_min"})
    policy = PublicationLengthPolicy(**policy_raw)
    checkpoints = tuple(_checkpoint(item, version) for item in _list(raw["checkpoints"]))
    return PublicationChapterMigrationManifest(
        migration_id=raw["migration_id"], project_id=raw["project_id"],
        source_edition_id=raw["source_edition_id"], target_edition_id=raw["target_edition_id"],
        source_start=raw["source_start"], source_end=raw["source_end"],
        frozen_through_chapter=raw["frozen_through_chapter"],
        entries=tuple(_decode_entry(item, version) for item in _list(raw["entries"])),
        omissions=tuple(_decode_omission(item, version) for item in _list(raw["omissions"])),
        length_policy=policy, checkpoints=checkpoints, status=ManifestStatus(raw["status"]),
        source_file_hashes=tuple(_file(item) for item in _list(raw["source_file_hashes"])),
        frozen_file_hashes=tuple(_file(item) for item in _list(raw["frozen_file_hashes"])),
        approved_by=raw["approved_by"], approved_at=raw["approved_at"],
        manifest_hash=raw["manifest_hash"], schema_version=version,
    )


def _decode_entry(raw: object, version: int) -> PublicationChapterEntry:
    base = {"body_hash", "canon_assertions", "chapter_function", "contract_id", "ending_hook",
            "omissions", "rewrites", "source_fragments", "state_receipt_id",
            "target_chapter", "title", "turning_point"}
    if version == 2:
        base |= {"dramatic_outcomes", "ending_hook_evidence", "length_dispositions",
                 "short_chapter_approvals",
                 "schema_version", "source_mappings"}
    value = _fields(raw, base)
    if version == 2 and value["schema_version"] != 2:
        raise ValueError("invalid entry schema version")
    return PublicationChapterEntry(
        target_chapter=value["target_chapter"],
        source_fragments=tuple(_decode_fragment(item) for item in _list(value["source_fragments"])),
        omissions=tuple(_decode_omission(item, version) for item in _list(value["omissions"])),
        title=value["title"], body_hash=value["body_hash"],
        rewrites=tuple(_rewrite(item) for item in _list(value["rewrites"])),
        chapter_function=value["chapter_function"], turning_point=value["turning_point"],
        ending_hook=value["ending_hook"], canon_assertions=tuple(_strings(value["canon_assertions"])),
        contract_id=value["contract_id"], state_receipt_id=value["state_receipt_id"],
        source_mappings=tuple(_mapping(item) for item in _list(value["source_mappings"])) if version == 2 else (),
        ending_hook_evidence=tuple(_decode_span(item) for item in _list(value["ending_hook_evidence"])) if version == 2 else (),
        length_dispositions=tuple(_approval(item) for item in _list(value["length_dispositions"])) if version == 2 else (),
        short_chapter_approvals=tuple(_short_approval(item) for item in _list(value["short_chapter_approvals"])) if version == 2 else (),
        dramatic_outcomes=tuple(_outcome(item) for item in _list(value["dramatic_outcomes"])) if version == 2 else (),
        schema_version=version,
    )


def _decode_fragment(raw: object) -> SourceFragment:
    value = _fields(raw, {"paragraph_end", "paragraph_start", "source_chapter", "text_hash"})
    return SourceFragment(value["source_chapter"], value["paragraph_start"], value["paragraph_end"], value["text_hash"])


def _decode_span(raw: object) -> TargetEvidenceSpan:
    value = _fields(raw, {"body_hash", "end_offset", "excerpt", "excerpt_hash", "start_offset", "target_chapter"})
    return TargetEvidenceSpan(value["target_chapter"], value["start_offset"], value["end_offset"], value["excerpt"], value["excerpt_hash"], value["body_hash"])


def _decode_omission(raw: object, version: int) -> MigrationOmission:
    keys = {"original_text_hash", "paragraph_end", "paragraph_start", "reason", "source_chapter"}
    if version == 2:
        keys |= {"actor", "decided_at", "migration_id", "snapshot_hash",
                 "split_plan_candidate_hash", "split_plan_decision_hash"}
    value = _fields(raw, keys)
    return MigrationOmission(value["source_chapter"], value["paragraph_start"], value["paragraph_end"],
                             value["original_text_hash"], value["reason"],
                             value.get("snapshot_hash", ""), value.get("migration_id", ""),
                             value.get("split_plan_candidate_hash", ""), value.get("split_plan_decision_hash", ""),
                             value.get("actor", ""), value.get("decided_at", ""))


def _mapping(raw: object) -> SourceToTargetMapping:
    value = _fields(raw, {"reason", "rewrite_kind", "source_fragment", "target_chapter", "target_span"})
    return SourceToTargetMapping(_decode_fragment(value["source_fragment"]), value["target_chapter"],
                                 _decode_span(value["target_span"]), RewriteKind(value["rewrite_kind"]), value["reason"])


def _length_fields(raw: object) -> dict[str, Any]:
    return _fields(raw, {"actor", "body_hash", "decided_at", "decision_hash", "disposition_id",
                         "interval_kind", "migration_id", "policy_hash", "reason",
                         "record_sequence", "target_chapter"})


def _approval(raw: object) -> LengthDisposition:
    value = _length_fields(raw)
    return LengthDisposition(value["disposition_id"], value["decision_hash"], value["record_sequence"],
                             value["migration_id"], value["target_chapter"], value["body_hash"],
                             value["policy_hash"], LengthIntervalKind(value["interval_kind"]),
                             value["actor"], value["reason"], value["decided_at"])


def _short_approval(raw: object) -> ShortChapterApproval:
    value = _length_fields(raw)
    return ShortChapterApproval(value["disposition_id"], value["decision_hash"], value["record_sequence"],
                                value["migration_id"], value["target_chapter"], value["body_hash"],
                                value["policy_hash"], LengthIntervalKind(value["interval_kind"]),
                                value["actor"], value["reason"], value["decided_at"])


def _outcome(raw: object) -> DramaticOutcomeBinding:
    value = _fields(raw, {"candidate_hash", "dramatic_unit_hash", "hook_evidence",
                          "outcome_evidence", "outcome_id", "target_chapter"})
    return DramaticOutcomeBinding(value["outcome_id"], value["dramatic_unit_hash"], value["candidate_hash"],
                                  value["target_chapter"], _decode_span(value["outcome_evidence"]),
                                  _decode_span(value["hook_evidence"]))


def _checkpoint_payload(value: MigrationCheckpoint, version: int) -> dict[str, object]:
    payload: dict[str, object] = {
        "batch_id": value.batch_id, "error": value.error,
        "input_fingerprint": value.input_fingerprint, "migration_id": value.migration_id,
        "output_fingerprint": value.output_fingerprint, "phase": value.phase.value,
    }
    if version == 2:
        payload.update({
            "checkpoint_hash": value.checkpoint_hash,
            "previous_checkpoint_hash": value.previous_checkpoint_hash,
            "project_id": value.project_id, "source_edition_id": value.source_edition_id,
            "source_end": value.source_end, "source_start": value.source_start,
            "target_edition_id": value.target_edition_id,
        })
    return payload


def _checkpoint(raw: object, version: int) -> MigrationCheckpoint:
    fields = {"batch_id", "error", "input_fingerprint", "migration_id", "output_fingerprint", "phase"}
    if version == 2:
        fields |= {"checkpoint_hash", "previous_checkpoint_hash", "project_id",
                   "source_edition_id", "source_end", "source_start", "target_edition_id"}
    value = _fields(raw, fields)
    return MigrationCheckpoint(value["migration_id"], CheckpointPhase(value["phase"]), value["batch_id"],
                               value["input_fingerprint"], value["output_fingerprint"], value["error"],
                               value.get("project_id", ""), value.get("source_edition_id", ""),
                               value.get("target_edition_id", ""), value.get("source_start", 0),
                               value.get("source_end", 0), value.get("previous_checkpoint_hash", ""),
                               value.get("checkpoint_hash", ""))


def _file(raw: object) -> FileHashRecord:
    value = _fields(raw, {"content_hash", "relative_path"})
    return FileHashRecord(value["relative_path"], value["content_hash"])


def _rewrite(raw: object) -> RewriteRecord:
    value = _fields(raw, {"reason", "rewritten_text_hash", "source_text_hash"})
    return RewriteRecord(value["source_text_hash"], value["rewritten_text_hash"], value["reason"])


def _fields(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("invalid fields")
    return value


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("invalid list")
    return value


def _strings(value: object) -> list[str]:
    items = _list(value)
    if not all(type(item) is str for item in items):
        raise ValueError("invalid string list")
    return items


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
