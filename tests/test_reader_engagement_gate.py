from pathlib import Path
from creative_os.domains.reader_engagement_gate import evaluate_reader_engagement_exit_gate


def test_gate_is_non_persistent_and_fail_closed_without_authority(tmp_path: Path):
    result = evaluate_reader_engagement_exit_gate(tmp_path)
    assert result.passed is False
    assert "active_plan_missing" in result.issues
