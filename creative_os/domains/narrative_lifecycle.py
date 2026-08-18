from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from creative_os.domains.narrative_decision import NarrativeDecision
from creative_os.domains.novel_state_model import StateChange


class HookStatus(StrEnum):
    OPEN = "open"
    ADVANCING = "advancing"
    DORMANT = "dormant"
    PAID_OFF = "paid_off"
    CONTRADICTED = "contradicted"


class LifecycleConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HookTransition:
    hook_id: str
    chapter: int
    status: HookStatus
    action: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HookLifecycle:
    hook_id: str
    status: HookStatus
    last_chapter: int
    history: tuple[HookTransition, ...]


@dataclass(frozen=True, slots=True)
class EmotionalTransition:
    subject: str
    chapter: int
    states: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReaderExpectationTransition:
    chapter: int
    before: str
    after: str


def build_hook_lifecycles(changes: Iterable[StateChange]) -> tuple[HookLifecycle, ...]:
    grouped: dict[str, list[HookTransition]] = {}
    for change in changes:
        if change.kind != "hook":
            continue
        status = _hook_status(change.fields.get("status", "open"))
        action = str(change.fields.get("action") or change.fields.get("question") or "").strip()
        if not action:
            raise LifecycleConflictError(f"hook {change.subject} has no lifecycle action")
        transition = HookTransition(
            hook_id=change.subject,
            chapter=_chapter(change),
            status=status,
            action=action,
            evidence=tuple(item.excerpt for item in change.evidence),
        )
        grouped.setdefault(change.subject, []).append(transition)

    lifecycles: list[HookLifecycle] = []
    for hook_id, history in grouped.items():
        history.sort(key=lambda item: (item.chapter, item.status.value, item.action))
        for previous, current in zip(history, history[1:]):
            if previous.status in {HookStatus.PAID_OFF, HookStatus.CONTRADICTED} and current.status != previous.status:
                raise LifecycleConflictError(
                    f"hook {hook_id} cannot move from {previous.status.value} to {current.status.value}"
                )
        latest = history[-1]
        lifecycles.append(HookLifecycle(hook_id, latest.status, latest.chapter, tuple(history)))
    return tuple(sorted(lifecycles, key=lambda item: item.hook_id))


def build_emotional_history(changes: Iterable[StateChange]) -> tuple[EmotionalTransition, ...]:
    history: list[EmotionalTransition] = []
    for change in changes:
        if change.kind != "character" or "emotional_state" not in change.fields:
            continue
        states = change.fields["emotional_state"]
        if not isinstance(states, list) or not states or any(not str(state).strip() for state in states):
            raise LifecycleConflictError(f"character {change.subject} has invalid emotional_state")
        history.append(EmotionalTransition(change.subject, _chapter(change), tuple(str(state) for state in states)))
    return tuple(sorted(history, key=lambda item: (item.chapter, item.subject)))


def build_reader_expectation_history(decisions: Iterable[NarrativeDecision]) -> tuple[ReaderExpectationTransition, ...]:
    ordered = sorted(decisions, key=lambda item: item.chapter)
    history: list[ReaderExpectationTransition] = []
    for previous, current in zip(ordered, ordered[1:]):
        if previous.volume_id != current.volume_id or previous.arc_id != current.arc_id:
            continue
        if previous.chapter_contract.reader_change.after != current.chapter_contract.reader_change.before:
            raise LifecycleConflictError(
                f"reader expectation discontinuity between chapters {previous.chapter} and {current.chapter}"
            )
    for decision in ordered:
        change = decision.chapter_contract.reader_change
        history.append(ReaderExpectationTransition(decision.chapter, change.before, change.after))
    return tuple(history)


def _hook_status(value: object) -> HookStatus:
    try:
        return HookStatus(str(value))
    except ValueError as error:
        raise LifecycleConflictError(f"invalid hook status: {value}") from error


def _chapter(change: StateChange) -> int:
    marker = "chapter-"
    if not change.id.startswith(marker):
        raise LifecycleConflictError(f"state change has no chapter: {change.id}")
    number = change.id[len(marker):].split("-", 1)[0]
    if not number.isdigit():
        raise LifecycleConflictError(f"state change has invalid chapter: {change.id}")
    return int(number)
