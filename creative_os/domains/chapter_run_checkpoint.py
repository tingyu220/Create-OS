from __future__ import annotations
from dataclasses import dataclass, replace
from enum import StrEnum
import hashlib, json

class CheckpointError(ValueError): pass

class ChapterRunState(StrEnum):
    AWAITING_READINESS_APPROVAL = "awaiting_readiness_approval"
    READINESS_APPROVED = "readiness_approved"
    DIRECTOR_PROPOSED = "director_proposed"
    CONTRACT_APPROVED = "contract_approved"
    ADMITTED = "admitted"
    WRITER_PREPARED = "writer_prepared"
    WRITER_COMPLETED = "writer_completed"
    QUALITY_REVIEWED = "quality_reviewed"
    CHAPTER_COMMITTED = "chapter_committed"
    ENGAGEMENT_REVIEWED = "engagement_reviewed"
    ENGAGEMENT_REVIEW_BLOCKED = "engagement_review_blocked"
    FULFILLMENT_INCOMPLETE = "fulfillment_incomplete"
    FULFILLMENT_RECORDED = "fulfillment_recorded"
    BLOCKED = "blocked"
    PAUSED = "paused"

_NEXT = {
    ChapterRunState.AWAITING_READINESS_APPROVAL: {ChapterRunState.READINESS_APPROVED, ChapterRunState.BLOCKED, ChapterRunState.PAUSED},
    ChapterRunState.READINESS_APPROVED: {ChapterRunState.DIRECTOR_PROPOSED, ChapterRunState.BLOCKED, ChapterRunState.PAUSED},
    ChapterRunState.DIRECTOR_PROPOSED: {ChapterRunState.CONTRACT_APPROVED, ChapterRunState.BLOCKED, ChapterRunState.PAUSED},
    ChapterRunState.CONTRACT_APPROVED: {ChapterRunState.ADMITTED, ChapterRunState.BLOCKED, ChapterRunState.PAUSED},
    ChapterRunState.ADMITTED: {ChapterRunState.WRITER_PREPARED, ChapterRunState.BLOCKED, ChapterRunState.PAUSED},
    ChapterRunState.WRITER_PREPARED: {ChapterRunState.WRITER_COMPLETED, ChapterRunState.BLOCKED, ChapterRunState.PAUSED},
    ChapterRunState.WRITER_COMPLETED: {ChapterRunState.QUALITY_REVIEWED, ChapterRunState.BLOCKED, ChapterRunState.PAUSED},
    ChapterRunState.QUALITY_REVIEWED: {ChapterRunState.CHAPTER_COMMITTED, ChapterRunState.BLOCKED, ChapterRunState.PAUSED},
    ChapterRunState.DIRECTOR_PROPOSED: {ChapterRunState.CONTRACT_APPROVED, ChapterRunState.ENGAGEMENT_REVIEWED, ChapterRunState.ENGAGEMENT_REVIEW_BLOCKED, ChapterRunState.BLOCKED, ChapterRunState.PAUSED},
    ChapterRunState.ENGAGEMENT_REVIEWED: {ChapterRunState.FULFILLMENT_INCOMPLETE, ChapterRunState.FULFILLMENT_RECORDED, ChapterRunState.BLOCKED, ChapterRunState.PAUSED},
    ChapterRunState.BLOCKED: {ChapterRunState.PAUSED},
    ChapterRunState.PAUSED: set(),
    ChapterRunState.CHAPTER_COMMITTED: set(),
}

@dataclass(frozen=True, slots=True)
class ChapterRunCheckpoint:
    project_id: str
    chapter_number: int
    state: ChapterRunState
    sequence: int
    previous_hash: str
    checkpoint_hash: str
    idempotency_key: str
    refs: tuple[str, ...] = ()

    @classmethod
    def initial(cls, project_id: str, chapter_number: int) -> "ChapterRunCheckpoint":
        if not project_id or type(chapter_number) is not int or chapter_number <= 0: raise CheckpointError("invalid_identity")
        return cls(project_id, chapter_number, ChapterRunState.AWAITING_READINESS_APPROVAL, 1, "0"*64, "0"*64, f"{project_id}:{chapter_number}:1")

    def advance(self, state: ChapterRunState, refs: tuple[str, ...] = ()) -> "ChapterRunCheckpoint":
        if state not in _NEXT[self.state]: raise CheckpointError("invalid_transition")
        if not isinstance(refs, tuple): raise CheckpointError("invalid_refs")
        payload = {"project_id":self.project_id,"chapter_number":self.chapter_number,"state":state.value,"sequence":self.sequence+1,"previous_hash":self.checkpoint_hash,"idempotency_key":f"{self.project_id}:{self.chapter_number}:{self.sequence+1}","refs":list(refs)}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return replace(self, state=state, sequence=self.sequence+1, previous_hash=self.checkpoint_hash, checkpoint_hash=digest, idempotency_key=payload["idempotency_key"], refs=refs)
