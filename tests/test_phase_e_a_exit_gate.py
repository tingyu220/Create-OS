from pathlib import Path

import pytest

from creative_os.domains.reader_engagement_gate import (
    ReaderEngagementExitGateResult,
    evaluate_reader_engagement_exit_gate,
)


class PhaseEAPrerequisiteError(RuntimeError):
    pass


def require_phase_e_a_gate(project_root: Path) -> ReaderEngagementExitGateResult:
    """B-test fixture: reevaluate A every time and never persist a receipt."""
    result = evaluate_reader_engagement_exit_gate(project_root)
    if not result.passed:
        raise PhaseEAPrerequisiteError(",".join(result.issues))
    return result


def test_b_cannot_create_readiness_or_run_when_a_gate_fails(tmp_path: Path):
    with pytest.raises(PhaseEAPrerequisiteError):
        require_phase_e_a_gate(tmp_path)
    assert not (tmp_path / ".creative_os" / "production-runs").exists()


def test_a_gate_fixture_has_no_persistent_receipt_or_b_owner_dependencies(tmp_path: Path):
    with pytest.raises(PhaseEAPrerequisiteError):
        require_phase_e_a_gate(tmp_path)
    assert not (tmp_path / ".creative_os" / "production-runs").exists()


def test_architecture_has_one_evidence_ref_definition_and_no_a_ledger_writer_escape():
    root = Path(__file__).parents[1]
    definitions = [path for path in root.joinpath("creative_os").rglob("*.py") if "class EvidenceRef" in path.read_text(encoding="utf-8")]
    assert definitions == [root / "creative_os" / "domains" / "narrative_evidence.py"]
    for name in ("narrative_director.py", "reader_engagement_planning.py"):
        source = root / "creative_os" / "domains" / name
        assert "materialize_transition(" not in source.read_text(encoding="utf-8")
