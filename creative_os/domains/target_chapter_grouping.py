from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib, json

@dataclass(frozen=True, slots=True)
class TargetChapterGroupingCandidate:
    migration_id: str
    target_chapter_id: int
    unit_indices: tuple[int, ...]
    source_mappings: tuple[tuple[int, int], ...]
    estimated_chinese_chars: int
    hook_evidence: tuple[str, ...]
    short_chapter_disposition: str | None = None

    def __post_init__(self):
        if self.target_chapter_id <= 0 or not self.unit_indices:
            raise ValueError("group identity invalid")
        if self.estimated_chinese_chars < 0 or not self.hook_evidence:
            raise ValueError("group evidence invalid")
        if self.short_chapter_disposition is not None and not self.short_chapter_disposition.strip():
            raise ValueError("short disposition invalid")

    @property
    def candidate_hash(self) -> str:
        payload = {"migration_id": self.migration_id, "target_chapter_id": self.target_chapter_id,
                   "unit_indices": self.unit_indices, "source_mappings": self.source_mappings,
                   "estimated_chinese_chars": self.estimated_chinese_chars,
                   "hook_evidence": self.hook_evidence,
                   "short_chapter_disposition": self.short_chapter_disposition}
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def encode_grouping(value: TargetChapterGroupingCandidate) -> str:
    return json.dumps({"schema_version": 1, "candidate_hash": value.candidate_hash, **asdict(value)}, ensure_ascii=False, sort_keys=True)
