from __future__ import annotations

from dataclasses import dataclass, replace

from creative_os.domains.narrative_replay_model import NarrativeReplayState, ReplayedChapterContract


KNOWN_REPLAY_EVENT_KINDS = frozenset({"chapter_replayed"})


@dataclass(frozen=True, slots=True)
class NarrativeReplayEvent:
    version: int
    kind: str
    chapter_id: str
    payload: ReplayedChapterContract


class NarrativeReplayStore:
    """Append-only in-memory projection used by a single replay run."""

    def __init__(self, project_id: str) -> None:
        if not project_id.strip():
            raise ValueError("narrative replay store requires project_id")
        self._events: tuple[NarrativeReplayEvent, ...] = ()
        self._state = NarrativeReplayState(project_id=project_id)

    def append(self, event: NarrativeReplayEvent) -> NarrativeReplayState:
        expected = self._state.version + 1
        if event.version != expected:
            raise ValueError(f"event version must be {expected}")
        if event.kind not in KNOWN_REPLAY_EVENT_KINDS:
            raise ValueError(f"unknown narrative replay event: {event.kind}")
        if event.chapter_id != event.payload.chapter_id:
            raise ValueError("event chapter_id must match replayed contract chapter_id")
        event.payload.validate()

        self._events = (*self._events, event)
        self._state = replace(
            self._state,
            version=event.version,
            chapter_contracts=(*self._state.chapter_contracts, event.payload),
        )
        return self.snapshot()

    def snapshot(self) -> NarrativeReplayState:
        return self._state

    def events(self) -> tuple[NarrativeReplayEvent, ...]:
        return self._events
