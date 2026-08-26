import dataclasses

import pytest

from creative_os.domains.pov_strategy_model import MainlineChangeProposal
from creative_os.domains.pov_strategy_review import review_pov_strategy
from creative_os.domains.pov_strategy_policy import POVStrategyPolicy
from tests.pov_strategy_helpers import candidate_set, evidence, option, strategy_input


@pytest.mark.parametrize("code", [
    "protagonist_absence_unresolved", "protagonist_pov_monopoly",
    "supporting_pov_without_agency", "pov_cannot_serve_chapter_function",
    "supporting_outcome_only_reported_to_protagonist", "pov_transition_without_arc_reason",
])
def test_reviewer_supports_all_required_risk_codes(code):
    assert code in review_pov_strategy.supported_codes


def test_reviewer_detects_report_only_supporting_outcome():
    candidates = candidate_set()
    changed = dataclasses.replace(
        candidates.recommended,
        primary_owner="supporting",
        protagonist_present=False,
        mainline_change=MainlineChangeProposal("mainline", "report", "integrate", (evidence(),)),
    )
    candidates = dataclasses.replace(candidates, recommended=changed)
    risks = review_pov_strategy(strategy_input(), candidates, POVStrategyPolicy())
    assert "supporting_outcome_only_reported_to_protagonist" in {risk.code for risk in risks}
