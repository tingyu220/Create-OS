import json

import pytest

from creative_os.domains.reader_engagement_codec import ReaderEngagementCodec


def test_codec_rejects_duplicate_keys_and_non_v1_schema():
    with pytest.raises(ValueError, match="duplicate"):
        ReaderEngagementCodec.decode('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="schema"):
        ReaderEngagementCodec.decode(json.dumps({"schema_version": 2}))


def test_codec_rejects_extra_fields_and_noncanonical_payload():
    with pytest.raises(ValueError, match="fields"):
        ReaderEngagementCodec.decode(json.dumps({"schema_version": 1, "extra": True}))


def test_codec_round_trips_known_record_with_canonical_bytes():
    payload = {"schema_version": 1, "record_type": "plan", "record": {"id": "plan-1"}}
    encoded = ReaderEngagementCodec.encode(payload)
    assert encoded == '{"record":{"id":"plan-1"},"record_type":"plan","schema_version":1}'
    assert ReaderEngagementCodec.decode(encoded) == payload
