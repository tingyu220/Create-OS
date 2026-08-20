import json

import pytest

from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import ChoiceStatus, NarrativeValidationError


def _legacy_v1_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "narrative_decision",
        "chapter": 7,
        "profile_id": "civilization-profile",
        "volume_id": "volume-1",
        "arc_id": "arc-identity",
        "arc_phase": "escalation",
        "arc_goal": "推进主动调查",
        "inherited_pressure": "权限即将收紧",
        "future_pressures": ["进入权限审查"],
        "evidence": [
            {
                "source_type": "outline",
                "source_ref": "outline/chapter-007.json",
                "excerpt": "第七章调查日志",
            }
        ],
        "chapter_contract": {
            "functions": ["推进主线"],
            "dramatic_question": "林子轩是否主动调查？",
            "protagonist_choice": {
                "actor": "林子轩",
                "action": "调查日志",
                "alternatives": ["等待"],
                "cost": "关系受损",
                "consequence": "进入审查",
            },
            "reader_change": {"before": "读者怀疑", "after": "读者确认风险"},
            "information": {"reveal": ["日志被覆盖"], "withhold": ["覆盖者身份"], "misdirect": []},
            "pressure_curve": {"start": "封控", "turn": "违令", "end": "审查"},
            "foreshadow_actions": [],
            "ending_shift": "主角成为审查对象",
            "target_chinese_chars": 7000,
            "forbidden": ["不得确认发送者"],
        },
    }


def test_decode_v1_normalizes_identity_and_marks_legacy_evidence_without_binding_it():
    decision = NarrativeDecisionCodec.decode(json.dumps(_legacy_v1_payload(), ensure_ascii=False))

    assert decision.schema_version == 2
    assert decision.contract_id == "narrative-chapter-007"
    assert decision.contract_version == 1
    assert decision.chapter_contract.chapter_id == "chapter_007"
    assert decision.chapter_contract.protagonist_choice.status == ChoiceStatus.COMPLETE
    assert decision.chapter_contract.intent_evidence_bindings == ()
    assert decision.legacy_unclassified_evidence[0].classification == "legacy_unclassified"
    assert decision.chapter_contract.foreshadow_actions.values == ()
    assert decision.chapter_contract.foreshadow_actions.not_applicable_reason is None


def test_v2_codec_round_trip_preserves_normalized_legacy_loss_marker():
    normalized = NarrativeDecisionCodec.decode_v1(_legacy_v1_payload())
    encoded = NarrativeDecisionCodec.encode_v2(normalized)

    assert NarrativeDecisionCodec.decode_v2(json.loads(encoded)) == normalized
    assert encoded == normalized.to_json()


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda payload: payload.update(schema_version=3), "schema"),
        (
            lambda payload: payload["chapter_contract"]["protagonist_choice"].update(status="assumed"),
            "choice status",
        ),
        (
            lambda payload: payload["chapter_contract"]["optional_candidates"][0].update(value_state="assumed"),
            "candidate value_state",
        ),
    ],
)
def test_codec_rejects_unknown_schema_or_required_state(mutation, match):
    normalized = NarrativeDecisionCodec.decode_v1(_legacy_v1_payload())
    payload = json.loads(NarrativeDecisionCodec.encode_v2(normalized))
    if not payload["chapter_contract"]["optional_candidates"]:
        payload["chapter_contract"]["optional_candidates"].append(
            {
                "candidate_id": "candidate-1",
                "kind": "scene_transition",
                "value_state": "known",
                "proposed_value": "转场",
                "dependency_inputs": ["chapter_contract.pressure_curve.end"],
                "affects_current_chapter": "yes",
                "rationale": "本章结尾依赖转场",
                "decided_by": "rule",
                "decision_ref": "rule-v1",
            }
        )
    mutation(payload)

    with pytest.raises(NarrativeValidationError, match=match):
        NarrativeDecisionCodec.decode(json.dumps(payload, ensure_ascii=False))


@pytest.mark.parametrize("alias", ["reader_before", "reader_after", "pressure_start", "pressure_end"])
def test_v2_codec_rejects_legacy_alias_field_names(alias):
    payload = json.loads(NarrativeDecisionCodec.encode_v2(NarrativeDecisionCodec.decode_v1(_legacy_v1_payload())))
    payload["chapter_contract"][alias] = "旧别名"

    with pytest.raises(NarrativeValidationError, match="unexpected field"):
        NarrativeDecisionCodec.decode_v2(payload)


def test_canonical_json_is_compact_sorted_utf8_and_content_hash_is_sha256():
    assert NarrativeDecisionCodec.canonical_json({"b": 2, "a": "汉"}) == '{"a":"汉","b":2}'
    assert NarrativeDecisionCodec.content_hash({"b": 2, "a": "汉"}) == (
        "e13590e4dfe9555eb0cd1d55f5bffab42d51ecf60d66afc55689a806f79c0f16"
    )
