import json

import pytest

from creative_os.domains.pov_strategy_codec import POVStrategyCodecError, decode_candidate_set, encode_candidate_set
from tests.pov_strategy_helpers import candidate_set


def test_candidate_codec_round_trip():
    value = candidate_set()
    assert decode_candidate_set(encode_candidate_set(value)) == value


def test_candidate_codec_rejects_modified_fingerprint():
    payload = json.loads(encode_candidate_set(candidate_set()))
    payload["input_fingerprint"] = "0" * 64
    with pytest.raises(POVStrategyCodecError, match="fingerprint"):
        decode_candidate_set(json.dumps(payload, ensure_ascii=False))
