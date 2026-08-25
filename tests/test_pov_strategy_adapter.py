import pytest

from creative_os.domains.narrative_decision import NarrativeValidationError, SupportingAgencyContract
from creative_os.domains.pov_strategy_adapter import pov_plan_from_option
from tests.pov_strategy_helpers import option


def test_adapter_requires_agency_and_preserves_owner():
    with pytest.raises(NarrativeValidationError):
        pov_plan_from_option(option(), ())
    agency = SupportingAgencyContract("lin-zixuan", "目标", "阻力", "选择", "代价", "结果", "改变主线")
    plan = pov_plan_from_option(option(), (agency,))
    assert plan.primary_owner == "lin-zixuan"
    assert plan.protagonist_present is True
