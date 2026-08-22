from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from creative_os.domains.narrative_decision import NarrativeDecision, NarrativeProjectProfile, NarrativeValidationError
from creative_os.domains.reader_engagement_model import ChapterEngagementProjection
import hashlib


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
    engagement_projection: ChapterEngagementProjection | None = None
    context_fingerprint: str | None = None


class NarrativeDirector:
    """Builds and validates candidates only; approval and persistence live elsewhere."""

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
        projection = input.engagement_projection
        if projection is not None:
            if projection.chapter_number != input.chapter_number:
                raise NarrativeDirectorBlockedError("engagement projection chapter mismatch")
            if len(set(projection.obligation_ids)) != len(projection.obligation_ids):
                raise NarrativeDirectorBlockedError("engagement projection contains duplicate obligations")
            obligations = proposal.chapter_contract.engagement_obligations
            if not obligations:
                raise NarrativeDirectorBlockedError("engagement projection is required")
            if any(item.projection_hash != projection.projection_hash for item in obligations):
                raise NarrativeDirectorBlockedError("engagement projection hash mismatch")
            if tuple(item.expectation_id for item in obligations) != projection.obligation_ids:
                raise NarrativeDirectorBlockedError("engagement obligations do not match frozen projection")
            if input.context_fingerprint is not None:
                expected = hashlib.sha256(projection.canonical_json.encode("utf-8")).hexdigest()
                if input.context_fingerprint != expected:
                    raise NarrativeDirectorBlockedError("context fingerprint is not bound to projection")
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
