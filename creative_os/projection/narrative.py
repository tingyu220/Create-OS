from __future__ import annotations

from dataclasses import dataclass

from creative_os.projection.provenance import Derivation, SourceRef


@dataclass(frozen=True, slots=True)
class CharacterSnapshot:
    subject: str
    fields_json: str
    source_refs: tuple[SourceRef, ...]
    derivation: Derivation


@dataclass(frozen=True, slots=True)
class StoryThreadSnapshot:
    subject: str
    thread_type: str
    status: str
    fields_json: str
    source_refs: tuple[SourceRef, ...]
    derivation: Derivation
    open_loop: str | None = None


@dataclass(frozen=True, slots=True)
class TimelineEntrySnapshot:
    subject: str
    precision: str
    relative_order: str
    conflict_status: str
    fields_json: str
    source_refs: tuple[SourceRef, ...]
    derivation: Derivation
