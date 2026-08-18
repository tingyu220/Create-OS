from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from creative_os.domains.narrative_decision import NarrativeDecision, NarrativeProjectProfile, NarrativeValidationError


class NarrativeDirectorBlockedError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DirectorInput:
    project_root: str | Path
    chapter_number: int
    profile: NarrativeProjectProfile
    fact_snapshots: tuple[dict[str, Any], ...]
    previous_ending: str
    active_decisions: tuple[NarrativeDecision, ...]
    target_chinese_chars: int


class NarrativeDirector:
    def propose(self, input: DirectorInput, proposal: NarrativeDecision) -> NarrativeDecision:
        self._validate_input(input)
        try:
            proposal.validate()
        except NarrativeValidationError as error:
            raise NarrativeDirectorBlockedError(f"invalid narrative proposal: {error}") from error
        if proposal.chapter != input.chapter_number:
            raise NarrativeDirectorBlockedError("proposal chapter does not match director chapter")
        if proposal.profile_id != input.profile.id:
            raise NarrativeDirectorBlockedError("proposal profile does not match active profile")
        volumes = {volume.id: volume for volume in input.profile.volumes}
        arcs = {arc.id: arc for arc in input.profile.arcs}
        volume = volumes.get(proposal.volume_id)
        arc = arcs.get(proposal.arc_id)
        if volume is None or arc is None or arc.volume_id != proposal.volume_id:
            raise NarrativeDirectorBlockedError("proposal narrative scale does not match active profile")
        if arc.phase != proposal.arc_phase or arc.goal != proposal.arc_goal:
            raise NarrativeDirectorBlockedError("proposal narrative phase does not match active profile")
        if proposal.chapter_contract.target_chinese_chars != input.target_chinese_chars:
            raise NarrativeDirectorBlockedError("proposal target length does not match director target")
        if any(decision.chapter == input.chapter_number for decision in input.active_decisions):
            raise NarrativeDirectorBlockedError("an active decision already exists for this chapter")
        return proposal

    def _validate_input(self, input: DirectorInput) -> None:
        if input.chapter_number < 1:
            raise NarrativeDirectorBlockedError("chapter number must be positive")
        if not str(input.project_root).strip():
            raise NarrativeDirectorBlockedError("project root is required")
        if not input.fact_snapshots:
            raise NarrativeDirectorBlockedError("fact snapshots are required")
        if any(not snapshot.get("kind") or not snapshot.get("subject") for snapshot in input.fact_snapshots):
            raise NarrativeDirectorBlockedError("fact snapshots require kind and subject")
        if not input.previous_ending.strip():
            raise NarrativeDirectorBlockedError("previous ending is required")
        if input.target_chinese_chars <= 0:
            raise NarrativeDirectorBlockedError("target chinese chars must be positive")
        try:
            input.profile.validate()
        except NarrativeValidationError as error:
            raise NarrativeDirectorBlockedError(f"invalid narrative profile: {error}") from error
