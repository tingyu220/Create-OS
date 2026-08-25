from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from creative_os.domains.narrative_decision import NarrativeDecision, NarrativeProjectProfile, NarrativeValidationError

if TYPE_CHECKING:
    from creative_os.domains.pov_strategy_model import POVOption


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
    def propose(
        self,
        input: DirectorInput,
        proposal: NarrativeDecision,
        pov_candidate: "POVOption | None" = None,
    ) -> NarrativeDecision:
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
        if proposal.schema_version != 2:
            raise NarrativeDirectorBlockedError("new narrative production requires schema v2")
        if proposal.schema_version >= 2:
            scene_plan = proposal.chapter_contract.scene_plan
            try:
                proposal.chapter_contract.pov_plan.validate(required=True)
            except NarrativeValidationError as error:
                raise NarrativeDirectorBlockedError(f"invalid POV or supporting agency: {error}") from error
            if scene_plan.required_world_slice and not any(
                scene.ordinary_people_present for scene in scene_plan.scenes
            ):
                raise NarrativeDirectorBlockedError(
                    "scene plan requires an ordinary-people scene for its external world slice"
                )
            self._validate_same_place_run(scene_plan, input.active_decisions)
            enabled = (Path(input.project_root) / ".creative_os" / "pov_strategy_policy.json").exists()
            if enabled:
                pov_candidate = self._load_selected_pov(input, proposal)
            if pov_candidate is not None:
                self._validate_pov_candidate(proposal, pov_candidate)
        return proposal

    @staticmethod
    def _load_selected_pov(input: DirectorInput, proposal: NarrativeDecision):
        from creative_os.runtime.pov_strategy_store import POVStrategyAuditStore, POVStrategyStoreError
        from creative_os.domains.pov_strategy_model import ChapterNeeds
        from creative_os.domains.pov_strategy_recompute import on_chapter_materialized, pending_recompute
        pending = pending_recompute(input.project_root)
        if pending and pending.get("target_chapter") == proposal.chapter:
            chapter = proposal.chapter_contract
            needs = ChapterNeeds(
                chapter.functions, chapter.dramatic_question,
                tuple(dict.fromkeys(scene.action for scene in chapter.scene_plan.scenes)),
                chapter.scene_plan.required_world_slice,
                tuple(technology.role for technology in chapter.technology_plan.technologies),
            )
            result = on_chapter_materialized(input.project_root, proposal.chapter - 1, needs)
            if result.next_candidate_id is None:
                raise NarrativeDirectorBlockedError("POV strategy recompute is pending")
        store = POVStrategyAuditStore(input.project_root)
        candidate_id = f"pov-strategy-{proposal.chapter:03d}"
        try:
            record = store.read(candidate_id)
            selection = store.load_selection(candidate_id)
        except POVStrategyStoreError as exc:
            raise NarrativeDirectorBlockedError("selected POV strategy is required") from exc
        if record.status != "selected" or selection.candidate_id != candidate_id:
            raise NarrativeDirectorBlockedError("selected POV strategy is required")
        from creative_os.domains.pov_strategy_input import assemble_pov_strategy_input
        from creative_os.domains.pov_strategy_policy import load_pov_strategy_policy
        from creative_os.domains.pov_strategy_selection import POVSelectionError, validate_selection
        chapter = proposal.chapter_contract
        current_needs = ChapterNeeds(
            chapter.functions, chapter.dramatic_question,
            tuple(dict.fromkeys(scene.action for scene in chapter.scene_plan.scenes)),
            chapter.scene_plan.required_world_slice,
            tuple(technology.role for technology in chapter.technology_plan.technologies),
        )
        try:
            current_input = assemble_pov_strategy_input(input.project_root, proposal.chapter, current_needs, load_pov_strategy_policy(input.project_root))
            validate_selection(selection, record.candidate, current_input)
        except (OSError, ValueError, POVSelectionError) as exc:
            raise NarrativeDirectorBlockedError("selected POV strategy is stale or invalid") from exc
        if selection.override is not None:
            return selection.override.option
        options = {record.candidate.recommended.id: record.candidate.recommended, **{item.id: item for item in record.candidate.alternatives}}
        option = options.get(selection.option_id)
        if option is None:
            raise NarrativeDirectorBlockedError("selected POV strategy is invalid")
        return option

    @staticmethod
    def _validate_pov_candidate(proposal: NarrativeDecision, candidate: "POVOption") -> None:
        plan = proposal.chapter_contract.pov_plan
        if plan.primary_owner != candidate.primary_owner or plan.protagonist_present != candidate.protagonist_present:
            raise NarrativeDirectorBlockedError("POV candidate does not match chapter contract")
        scenes = proposal.chapter_contract.scene_plan.scenes
        owner_scenes = [scene for scene in scenes if candidate.primary_owner == scene.viewpoint]
        if not owner_scenes:
            raise NarrativeDirectorBlockedError("POV candidate is not used by any scene viewpoint")
        if any(candidate.primary_owner not in scene.participants for scene in owner_scenes):
            raise NarrativeDirectorBlockedError("POV candidate owner must participate in viewpoint scenes")
        if candidate.mainline_change.change_type == "report":
            raise NarrativeDirectorBlockedError("POV candidate cannot change mainline only by report")
        if not set(proposal.chapter_contract.functions).issubset(set(candidate.function_fits)):
            raise NarrativeDirectorBlockedError("POV candidate cannot serve chapter functions")
        agency = next((item for item in plan.supporting_agency if item.actor == candidate.primary_owner), None)
        if agency is None:
            raise NarrativeDirectorBlockedError("POV candidate lacks matching supporting agency")
        if agency.choice != candidate.agency.choice_boundary or agency.mainline_change != candidate.mainline_change.target_state_ref:
            raise NarrativeDirectorBlockedError("POV candidate conflicts with supporting agency contract")
        technologies = proposal.chapter_contract.technology_plan.technologies
        if technologies and candidate.mainline_change.capability not in {
            value for technology in technologies for value in (technology.id, technology.name, technology.role, technology.first_application)
        }:
            raise NarrativeDirectorBlockedError("POV candidate capability cannot serve technology plan")

    @staticmethod
    def _validate_same_place_run(scene_plan: object, active_decisions: tuple[NarrativeDecision, ...]) -> None:
        scenes = getattr(scene_plan, "scenes")
        if not scenes:
            return
        current_places = {scene.place_id for scene in scenes}
        if len(current_places) != 1 or getattr(scene_plan, "exception_reason"):
            return
        place_id = next(iter(current_places))
        repeated = 1
        for decision in sorted(active_decisions, key=lambda value: value.chapter, reverse=True):
            previous = decision.chapter_contract.scene_plan.scenes
            if not previous or {scene.place_id for scene in previous} != {place_id}:
                break
            repeated += 1
        if repeated > getattr(scene_plan, "allowed_same_place_run"):
            raise NarrativeDirectorBlockedError(
                f"same place run exceeds limit for {place_id}; provide an exception reason or change scene structure"
            )

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
