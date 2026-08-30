import dataclasses

import pytest

from creative_os.domains.pov_strategy_model import HumanPOVOverride
from creative_os.domains.pov_strategy_selection import (
    POVSelectionError, select_override, select_recommendation, validate_selection_fresh,
)
from tests.pov_strategy_helpers import candidate_set, option, strategy_input


def test_selection_becomes_stale_when_input_changes():
    value = strategy_input()
    selection = select_recommendation(candidate_set(), value, actor="tingyu")
    changed = dataclasses.replace(value, target_chapter=28).with_fingerprint()
    with pytest.raises(POVSelectionError, match="stale_pov_strategy_candidate"):
        validate_selection_fresh(selection, changed)


def test_override_requires_reason_and_evidence():
    override = HumanPOVOverride(option("other", False), "", ())
    with pytest.raises(POVSelectionError, match="pov_override_insufficient_evidence"):
        select_override(override, candidate_set(), strategy_input(), actor="tingyu")
