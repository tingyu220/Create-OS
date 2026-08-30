from __future__ import annotations

from dataclasses import dataclass

from creative_os.domains.narrative_decision import ChapterContract
from creative_os.domains.novel_review_model import CharacterStateProposal, NovelReviewResult
from creative_os.domains.novel_state_model import StateChange, StateEvidence


@dataclass(frozen=True, slots=True)
class CanonPatch:
    kind: str
    subject: str
    fields: dict[str, object]
    evidence: tuple[StateEvidence, ...]


@dataclass(frozen=True, slots=True)
class NovelNextTaskInput:
    previous_chapter_id: str
    previous_chapter_hash: str
    resulting_states: tuple[str, ...]
    required_open_hooks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NovelCompileRequest:
    chapter_id: str
    source_chapter: str
    draft: str
    content_hash: str
    chapter_contract: ChapterContract
    review: NovelReviewResult
    character_changes: tuple[CharacterStateProposal, ...] = ()


@dataclass(frozen=True, slots=True)
class NovelCompileResult:
    canon_patches: tuple[CanonPatch, ...]
    state_changes: tuple[StateChange, ...]
    next_task_input: NovelNextTaskInput
    fingerprint: str

