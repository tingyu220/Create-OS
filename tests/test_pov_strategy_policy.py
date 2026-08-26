import json

import pytest

from creative_os.domains.pov_strategy_policy import POVStrategyPolicyError, load_pov_strategy_policy


@pytest.mark.parametrize("illegal", [
    {"protagonist_ratio": 0.7},
    {"pov_rotation": ["a", "b"]},
    {"history_window": 11},
])
def test_policy_rejects_ratio_rotation_and_invalid_window(tmp_path, illegal):
    path = tmp_path / ".creative_os/pov_strategy_policy.json"
    path.parent.mkdir()
    path.write_text(json.dumps(illegal), encoding="utf-8")
    with pytest.raises(POVStrategyPolicyError):
        load_pov_strategy_policy(tmp_path)


def test_policy_defaults_are_review_thresholds_not_ratios(tmp_path):
    policy = load_pov_strategy_policy(tmp_path)
    assert policy.history_window == 8
    assert policy.absence_review_after == 3
    assert not hasattr(policy, "protagonist_ratio")
