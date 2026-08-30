from __future__ import annotations

import hashlib
import re
import json
from pathlib import Path

from creative_os.domains.pov_strategy_model import EvidenceRef, POVOption, POVSelectionRecord, POVStrategyCandidateSet


class POVEvidenceError(ValueError):
    pass


def verify_candidate_evidence(project_root, candidates: POVStrategyCandidateSet, option: POVOption, selection: POVSelectionRecord) -> None:
    """逐条验证实际选择及候选所依赖的权威文件。"""
    refs = [*option.evidence_refs, *option.mainline_change.evidence_refs, *option.transition.evidence_refs]
    refs.extend(option.agency.goal_ref.evidence_refs)
    refs.extend(option.agency.resistance_ref.evidence_refs)
    if option.agency.plausible_cost_ref is not None:
        refs.extend(option.agency.plausible_cost_ref.evidence_refs)
    refs.extend(candidates.recommended.evidence_refs)
    if selection.override is not None:
        refs.extend(selection.override.evidence_refs)
    for ref in refs:
        verify_evidence_ref(project_root, ref)


def verify_evidence_ref(project_root, ref: EvidenceRef) -> None:
    root = Path(project_root)
    if ref.source_id == "narrative-project-profile":
        path = root / ".creative_os" / "memory" / "items" / "narrative-project-profile.json"
    else:
        path = root / ref.source_id
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve())
        text = resolved.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise POVEvidenceError("unverifiable_pov_evidence") from exc
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != ref.source_content_hash:
        raise POVEvidenceError("unverifiable_pov_evidence")
    locator = ref.locator.value if ref.locator is not None else ""
    if not locator.strip() or not ref.source_version.strip():
        raise POVEvidenceError("unverifiable_pov_evidence")
    if locator.startswith("chapter:"):
        chapter = int(locator.partition(":")[2])
        if not re.search(rf"chapter_{chapter:03d}\.md$", ref.source_id):
            raise POVEvidenceError("unverifiable_pov_evidence")
        if not re.search(rf"第\s*{chapter}\s*章", text):
            raise POVEvidenceError("unverifiable_pov_evidence")
    elif locator.startswith("arc:"):
        if ref.source_id != "narrative-project-profile":
            raise POVEvidenceError("unverifiable_pov_evidence")
        if locator.partition(":")[2] not in text:
            raise POVEvidenceError("unverifiable_pov_evidence")
    elif locator.startswith("snapshot:"):
        if "/state/snapshots/" not in f"/{ref.source_id}":
            raise POVEvidenceError("unverifiable_pov_evidence")
        parts = locator.split(":", 2)
        payload = json.loads(text)
        if len(parts) != 3 or payload.get("kind") != parts[1] or payload.get("subject") != parts[2]:
            raise POVEvidenceError("unverifiable_pov_evidence")
    else:
        raise POVEvidenceError("unverifiable_pov_evidence")
