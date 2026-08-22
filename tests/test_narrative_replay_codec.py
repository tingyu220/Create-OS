import pytest

from creative_os.domains.narrative_replay_codec import ReplayContractCodec
from creative_os.domains.narrative_replay_model import (
    ReplayChoiceStatus, ReplayedChapterContract, ReplayedProtagonistChoice,
)


def _v2_payload(choice):
    return {
        "schema_version": 2,
        "chapter_id": "chapter_005",
        "functions": ["保留关键证据"],
        "dramatic_question": "是否立即上报？",
        "protagonist_choice": choice,
        "reader_change": {"before": "怀疑", "after": "确认"},
        "pressure_curve": {"start": "受阻", "end": "被监控"},
        "ending_shift": "暂缓上报",
        "evidence": [{
            "source_type": "chapter", "source_ref": "chapter_005.md",
            "excerpt": "保存缺页证据。",
        }],
    }


def test_v2_round_trip_returns_replay_contract_not_formal_contract():
    payload = _v2_payload({
        "status": "complete", "actor": "许砚", "action": "保存证据",
        "alternatives": ["立即上报"], "cost": "承担隐瞒风险",
        "consequence": "进入监控", "missing_fields": [],
    })
    contract = ReplayContractCodec.decode(payload)
    assert type(contract) is ReplayedChapterContract
    assert contract.protagonist_choice.status is ReplayChoiceStatus.COMPLETE
    assert ReplayContractCodec.decode(ReplayContractCodec.encode_v2(contract)) == contract


def test_v1_legacy_evidence_is_audit_only_and_round_trips():
    payload = _v2_payload(None)
    payload["schema_version"] = 1
    payload["reader_before"] = payload.pop("reader_change")["before"]
    payload["reader_after"] = "确认"
    payload["pressure_start"] = payload.pop("pressure_curve")["start"]
    payload["pressure_end"] = "被监控"
    contract = ReplayContractCodec.decode(payload)
    assert contract.evidence[0].role is None
    assert contract.evidence[0].evidence_id is None
    assert ReplayContractCodec.decode_v1(payload) == contract


@pytest.mark.parametrize(
    ("choice", "status", "missing"),
    [
        ({"actor": "许砚", "action": "不上报"}, ReplayChoiceStatus.PARTIAL,
         ("alternatives", "cost", "consequence")),
        (None, ReplayChoiceStatus.UNKNOWN,
         ("actor", "action", "alternatives", "cost", "consequence")),
    ],
)
def test_choice_status_and_missing_fields_are_exact(choice, status, missing):
    contract = ReplayContractCodec.decode(_v2_payload(choice))
    assert contract.protagonist_choice.status is status
    assert contract.protagonist_choice.missing_fields == missing


def test_codec_rejects_claim_without_evidence_and_unknown_schema():
    payload = _v2_payload(None)
    payload["evidence"] = []
    with pytest.raises(ValueError, match="evidence"):
        ReplayContractCodec.decode(payload)
    payload["schema_version"] = 3
    with pytest.raises(ValueError, match="schema"):
        ReplayContractCodec.decode(payload)
