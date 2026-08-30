import pytest
from dataclasses import replace

from creative_os.domains.pov_strategy_policy import POVStrategyPolicy
from creative_os.domains.pov_strategy_selection import select_recommendation
from creative_os.domains.pov_strategy_model import POVSelectionRecord, HumanPOVOverride
from creative_os.pov_strategy_admission import POVStrategyAdmissionBlockedError, admit_pov_strategy
from creative_os.runtime.pov_strategy_store import POVStrategyAuditStore
from tests.pov_strategy_helpers import candidate_set, strategy_input
from tests.test_pov_strategy_input import _decision


def test_admission_blocks_stale_and_unapproved_contract(tmp_path):
    value = strategy_input()
    candidates = candidate_set()
    store = POVStrategyAuditStore(tmp_path)
    store.append_candidate(candidates)
    selection = select_recommendation(candidates, value, actor="tingyu")
    store.append_selection(selection)
    with pytest.raises(POVStrategyAdmissionBlockedError, match="missing_approved_narrative_decision"):
        admit_pov_strategy(tmp_path, selection, value, _decision(27, "lin-zixuan"), approved_by="")


def test_admission_accepts_matching_approved_selection(tmp_path):
    value = strategy_input()
    candidates = candidate_set()
    store = POVStrategyAuditStore(tmp_path)
    store.append_candidate(candidates)
    selection = select_recommendation(candidates, value, actor="tingyu")
    store.append_selection(selection)
    contract = _decision(27, "lin-zixuan")
    contract = replace(contract, chapter_contract=replace(
        contract.chapter_contract,
        pov_plan=replace(contract.chapter_contract.pov_plan, protagonist_present=True),
    ))
    result = admit_pov_strategy(tmp_path, selection, value, contract, approved_by="tingyu", policy=POVStrategyPolicy(protagonist_id="lin-zixuan"))
    assert result.admitted is True


def test_enabled_project_cannot_reach_writer_boundary_without_authoritative_admission(tmp_path):
    from tests.test_novel_continuation import _project
    from tests.test_narrative_continuation import _approved_contract
    from creative_os.domains.novel_continuation import build_next_chapter

    project = _project(tmp_path)
    _approved_contract(project, chapter=3)
    policy_path = project / ".creative_os/pov_strategy_policy.json"
    policy_path.write_text('{"version":"v1"}', encoding="utf-8")
    with pytest.raises(ValueError):
        build_next_chapter(project, require_narrative_contract=True)


def test_admission_rejects_forged_empty_override(tmp_path):
    value = strategy_input()
    candidates = candidate_set()
    store = POVStrategyAuditStore(tmp_path)
    store.append_candidate(candidates)
    forged = POVSelectionRecord(candidates.id, "evil", "override", "attacker", value.baseline_fingerprint, "now", HumanPOVOverride(candidates.recommended, "", ()))
    store.append_selection(forged)
    with pytest.raises(POVStrategyAdmissionBlockedError, match="pov_override_insufficient_evidence"):
        admit_pov_strategy(tmp_path, forged, value, _decision(27, "lin-zixuan"), approved_by="tingyu")


def test_admission_rejects_override_with_unrelated_function(tmp_path):
    value = strategy_input()
    candidates = candidate_set()
    store = POVStrategyAuditStore(tmp_path)
    store.append_candidate(candidates)
    bad_option = replace(candidates.recommended, id="bad", function_fits=("无关功能",))
    override = HumanPOVOverride(bad_option, "人工改选", bad_option.evidence_refs)
    forged = POVSelectionRecord(candidates.id, "bad", "override", "tingyu", value.baseline_fingerprint, "now", override)
    store.append_selection(forged)
    with pytest.raises(POVStrategyAdmissionBlockedError, match="pov_cannot_serve"):
        admit_pov_strategy(tmp_path, forged, value, _decision(27, "lin-zixuan"), approved_by="tingyu")
