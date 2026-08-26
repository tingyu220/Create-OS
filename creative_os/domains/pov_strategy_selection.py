from __future__ import annotations

from datetime import datetime, timezone

from creative_os.domains.pov_strategy_model import (
    HumanPOVOverride, POVSelectionRecord, POVStrategyCandidateSet, POVStrategyInput,
)


class POVSelectionError(ValueError):
    pass


def select_recommendation(candidates, current_input, *, actor):
    return _selection(candidates, candidates.recommended.id, "recommended", current_input, actor)


def select_alternative(candidate_id, candidates, current_input, *, actor):
    if candidate_id not in {item.id for item in candidates.alternatives}:
        raise POVSelectionError("unknown alternative")
    return _selection(candidates, candidate_id, "alternative", current_input, actor)


def select_override(override, candidates, current_input, *, actor):
    if not override.reason.strip() or not override.evidence_refs:
        raise POVSelectionError("pov_override_insufficient_evidence")
    option = override.option
    if not option.function_fits or not option.mainline_change.target_state_ref or not option.transition.arc_reason:
        raise POVSelectionError("pov_override_insufficient_evidence")
    record = _selection(candidates, option.id, "override", current_input, actor)
    return POVSelectionRecord(**{**record.__dict__}, override=override) if hasattr(record, "__dict__") else POVSelectionRecord(
        record.candidate_id, record.option_id, record.selection_kind, record.actor,
        record.input_fingerprint, record.selected_at, override,
    )


def validate_selection_fresh(selection: POVSelectionRecord, current_input: POVStrategyInput) -> None:
    current_input.validate_fingerprint()
    if selection.input_fingerprint != current_input.baseline_fingerprint:
        raise POVSelectionError("stale_pov_strategy_candidate")


def validate_selection(selection, candidates, current_input) -> None:
    """重放领域选择规则，防止持久层注入伪造的人工覆盖。"""
    validate_selection_fresh(selection, current_input)
    if selection.candidate_id != candidates.id:
        raise POVSelectionError("selection candidate mismatch")
    if selection.selection_kind == "recommended":
        expected = candidates.recommended.id
    elif selection.selection_kind == "alternative":
        expected = selection.option_id
        if expected not in {item.id for item in candidates.alternatives}:
            raise POVSelectionError("unknown alternative")
    elif selection.selection_kind == "override":
        override = selection.override
        if override is None or not override.reason.strip() or not override.evidence_refs:
            raise POVSelectionError("pov_override_insufficient_evidence")
        option = override.option
        if selection.option_id != option.id or not option.function_fits or not option.mainline_change.target_state_ref or not option.transition.arc_reason:
            raise POVSelectionError("pov_override_insufficient_evidence")
        _validate_option_fit(option, current_input)
        return
    else:
        raise POVSelectionError("invalid selection kind")
    if selection.override is not None or selection.option_id != expected:
        raise POVSelectionError("selection option mismatch")
    option = candidates.recommended if selection.selection_kind == "recommended" else next(item for item in candidates.alternatives if item.id == selection.option_id)
    _validate_option_fit(option, current_input)


def _validate_option_fit(option, current_input):
    required = set(current_input.chapter_needs.functions)
    required.update(current_input.chapter_needs.required_scene_capabilities)
    required.update(current_input.chapter_needs.technology_roles)
    supported = set(option.function_fits) | {option.mainline_change.capability}
    if not required.issubset(supported):
        raise POVSelectionError("pov_cannot_serve_chapter_function")


def _selection(candidates, option_id, kind, current_input, actor):
    if not actor.strip():
        raise POVSelectionError("human actor is required")
    current_input.validate_fingerprint()
    if candidates.input_fingerprint != current_input.baseline_fingerprint:
        raise POVSelectionError("stale_pov_strategy_candidate")
    return POVSelectionRecord(
        candidates.id, option_id, kind, actor.strip(), current_input.baseline_fingerprint,
        datetime.now(timezone.utc).isoformat(), None,
    )
