from __future__ import annotations

from creative_os.domains.narrative_decision import (
    NarrativeValidationError, PointOfViewPlan, SupportingAgencyContract,
)
from creative_os.domains.pov_strategy_model import POVOption


def pov_plan_from_option(
    option: POVOption,
    agencies: tuple[SupportingAgencyContract, ...],
) -> PointOfViewPlan:
    if not agencies:
        raise NarrativeValidationError("POV option requires approved supporting agency details")
    if option.primary_owner not in {agency.actor for agency in agencies}:
        raise NarrativeValidationError("POV owner must own a supporting agency contract")
    plan = PointOfViewPlan(
        primary_owner=option.primary_owner,
        mode="limited",
        protagonist_present=option.protagonist_present,
        supporting_agency=agencies,
        rationale=option.rationale,
    )
    plan.validate(required=True)
    return plan
