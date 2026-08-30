import hashlib
import json

import pytest

from creative_os.domains.legacy_narrative_adapter import LegacyNarrativeAdapter
from tests.test_narrative_codec import _legacy_v1_payload


def _legacy():
    raw = json.dumps(_legacy_v1_payload(), ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def test_adapter_is_pure_idempotent_and_reports_all_legacy_losses():
    raw, digest = _legacy()
    first = LegacyNarrativeAdapter.adapt("legacy-7", 3, digest, raw)
    second = LegacyNarrativeAdapter.adapt("legacy-7", 3, digest, raw)
    assert first == second
    assert first.candidate.contract_id == "narrative-chapter-007"
    assert first.candidate.chapter_contract.chapter_id == "chapter_007"
    assert {loss.code for loss in first.losses} >= {
        "derived_chapter_id", "legacy_unclassified_evidence",
        "empty_nullable_plan_requires_review",
    }
    assert first.requires_manual_review is True
    assert first.candidate.chapter_contract.intent_evidence_bindings == ()


def test_adapter_rejects_hash_drift_and_can_mark_completed_chapter_replay_only():
    raw, digest = _legacy()
    with pytest.raises(ValueError, match="hash"):
        LegacyNarrativeAdapter.adapt("legacy-7", 3, "0" * 64, raw)
    report = LegacyNarrativeAdapter.adapt("legacy-7", 3, digest, raw, completed=True)
    assert report.replay_only is True
    assert report.candidate is None
