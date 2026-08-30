from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from creative_os.domains.narrative_decision import NarrativeDecision
from creative_os.domains.narrative_memory import (
    load_active_narrative_approval_actor,
    load_active_narrative_decision,
)
from creative_os.domains.pov_strategy_input import assemble_pov_strategy_input
from creative_os.domains.pov_strategy_model import ChapterNeeds
from creative_os.domains.pov_strategy_model import POVSelectionRecord, POVStrategyInput, POVRisk
from creative_os.domains.pov_strategy_contract import chapter_needs_from_contract
from creative_os.domains.pov_strategy_policy import POVStrategyPolicy, load_pov_strategy_policy
from creative_os.domains.pov_strategy_review import review_selected_pov
from creative_os.domains.pov_strategy_selection import POVSelectionError, validate_selection
from creative_os.runtime.pov_strategy_store import POVStrategyAuditStore, POVStrategyStoreError
from creative_os.domains.pov_strategy_evidence import POVEvidenceError, verify_candidate_evidence


class POVStrategyAdmissionBlockedError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class POVStrategyAdmissionResult:
    admitted: bool
    candidate_id: str
    input_fingerprint: str
    contract_hash: str
    risks: tuple[POVRisk, ...]


def admit_pov_strategy(
    project_root: str | Path,
    selection: POVSelectionRecord,
    current_input: POVStrategyInput,
    contract: NarrativeDecision,
    *,
    approved_by: str,
    policy: POVStrategyPolicy | None = None,
    verify_evidence: bool = False,
) -> POVStrategyAdmissionResult:
    if not approved_by.strip() or approved_by.strip().lower() == "system":
        raise POVStrategyAdmissionBlockedError("missing_approved_narrative_decision")
    try:
        store = POVStrategyAuditStore(project_root)
        record = store.read(selection.candidate_id)
        persisted = store.load_selection(selection.candidate_id)
        if persisted != selection or record.status != "selected":
            raise POVStrategyStoreError("selection audit mismatch")
        validate_selection(selection, record.candidate, current_input)
    except (POVStrategyStoreError, POVSelectionError) as exc:
        code = "unverifiable_pov_evidence" if isinstance(exc, POVStrategyStoreError) else str(exc)
        raise POVStrategyAdmissionBlockedError(code) from exc
    candidates = record.candidate
    if candidates.input_fingerprint != current_input.baseline_fingerprint:
        raise POVStrategyAdmissionBlockedError("stale_pov_strategy_candidate")
    options = {candidates.recommended.id: candidates.recommended, **{item.id: item for item in candidates.alternatives}}
    if selection.override is not None:
        option = selection.override.option
    else:
        option = options.get(selection.option_id)
    if option is None:
        raise POVStrategyAdmissionBlockedError("pov_override_insufficient_evidence")
    if verify_evidence:
        try:
            verify_candidate_evidence(project_root, candidates, option, selection)
        except POVEvidenceError as exc:
            raise POVStrategyAdmissionBlockedError("unverifiable_pov_evidence") from exc
    plan = contract.chapter_contract.pov_plan
    if plan.primary_owner != option.primary_owner or plan.protagonist_present != option.protagonist_present:
        raise POVStrategyAdmissionBlockedError("pov_selection_contract_mismatch")
    active_policy = policy or load_pov_strategy_policy(project_root)
    risks = review_selected_pov(current_input, candidates, option, active_policy)
    if any(risk.severity == "blocking" or risk.code in active_policy.blocking_risks for risk in risks):
        raise POVStrategyAdmissionBlockedError("pov_strategy_review_blocked")
    contract_hash = hashlib.sha256(contract.to_json().encode("utf-8")).hexdigest()
    return POVStrategyAdmissionResult(True, candidates.id, current_input.baseline_fingerprint, contract_hash, risks)


def admit_active_pov_strategy(project_root: str | Path, contract: NarrativeDecision) -> POVStrategyAdmissionResult:
    root = Path(project_root)
    policy = load_pov_strategy_policy(root)
    active = load_active_narrative_decision(root, contract.chapter)
    if active is None or active.to_json() != contract.to_json():
        raise POVStrategyAdmissionBlockedError("missing_approved_narrative_decision")
    approved_by = load_active_narrative_approval_actor(root, contract.chapter)
    if not approved_by:
        raise POVStrategyAdmissionBlockedError("missing_approved_narrative_decision")
    needs = chapter_needs_from_contract(contract.chapter_contract)
    current_input = assemble_pov_strategy_input(root, contract.chapter, needs, policy)
    store = POVStrategyAuditStore(root)
    current = store.current_for_chapter(contract.chapter)
    selection = store.load_selection(current.candidate.id)
    return admit_pov_strategy(root, selection, current_input, contract, approved_by=approved_by, policy=policy, verify_evidence=True)
