from dataclasses import replace

import pytest

from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.novel_writer import (
    NovelDraft,
    NovelWritingError,
    NovelWritingRequest,
    chapter_contract_content_hash,
)
from tests.test_narrative_director import _v2_decision


def _request_inputs(decision):
    canonical_json = NarrativeDecisionCodec.encode(decision)
    return {
        "chapter_id": decision.chapter_contract.chapter_id,
        "chapter_contract": decision.chapter_contract,
        "context_fingerprint": "a" * 64,
        "instruction": "按批准合同写作",
        "contract_id": decision.contract_id,
        "contract_content_hash": NarrativeDecisionCodec.content_hash(canonical_json),
        "chapter_contract_hash": chapter_contract_content_hash(decision.chapter_contract),
        "contract_canonical_json": canonical_json,
    }


def test_request_recomputes_authoritative_contract_binding():
    decision = _v2_decision()

    request = NovelWritingRequest(**_request_inputs(decision))

    assert request.contract_id == decision.contract_id
    assert request.contract_content_hash == NarrativeDecisionCodec.content_hash(decision)
    assert request.chapter_contract_hash == chapter_contract_content_hash(decision.chapter_contract)
    assert request.chapter_contract == decision.chapter_contract


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"contract_id": "unrelated-contract"}, "novel_writer_request_contract_id_mismatch"),
        ({"contract_content_hash": "0" * 64}, "novel_writer_request_contract_hash_mismatch"),
    ],
)
def test_request_rejects_unrelated_contract_identity(changes, code):
    inputs = _request_inputs(_v2_decision())
    inputs.update(changes)

    with pytest.raises(NovelWritingError, match=code):
        NovelWritingRequest(**inputs)


def test_request_rejects_tampered_chapter_contract():
    decision = _v2_decision()
    inputs = _request_inputs(decision)
    inputs["chapter_contract"] = replace(
        decision.chapter_contract,
        ending_shift="调用方篡改后的结尾",
    )

    with pytest.raises(NovelWritingError, match="novel_writer_request_contract_projection_mismatch"):
        NovelWritingRequest(**inputs)


def test_request_rejects_chapter_contract_hash_that_does_not_match_current_contract():
    inputs = _request_inputs(_v2_decision())
    inputs["chapter_contract_hash"] = "0" * 64

    with pytest.raises(NovelWritingError, match="novel_writer_request_chapter_contract_hash_mismatch"):
        NovelWritingRequest(**inputs)


def test_request_rejects_chapter_id_mismatched_with_chapter_contract():
    decision = _v2_decision(chapter=7)
    inputs = _request_inputs(decision)
    inputs["chapter_id"] = "chapter_001"

    with pytest.raises(NovelWritingError, match="novel_writer_request_chapter_mismatch"):
        NovelWritingRequest(**inputs)


def test_draft_strips_final_content_before_hashing():
    draft = NovelDraft.from_content(" \n正文\n ")

    assert draft.content == "正文"
    assert draft.content_hash == "d661c3d96d53ebc0ca8a55aae24b5df4a4d1bf28d37337b982fe8ebf54846eeb"
