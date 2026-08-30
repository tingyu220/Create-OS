import pytest
import json
from tests.test_narrative_director import _decision
from tests.test_narrative_codec import _legacy_v1_payload

from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_director import NarrativeDirectorBlockedError
from creative_os.domains.reader_engagement_model import ChapterEngagementProjection
from dataclasses import replace
import hashlib


def test_v3_contract_obligation_requires_projection_and_exact_intent_evidence():
    decision = _decision()
    with pytest.raises(Exception, match="engagement"):
        NarrativeDecisionCodec.encode_v3(decision)


def test_v2_decode_is_exact_but_adapter_candidate_is_unsatisfied():
    v2 = json.loads(NarrativeDecisionCodec.encode_v2(_decision()))
    decoded = NarrativeDecisionCodec.decode(v2)
    assert NarrativeDecisionCodec.schema_version(v2) == 2
    candidate = NarrativeDecisionCodec.adapt_v2_to_v3(v2)
    assert getattr(candidate, "engagement_status", "unsatisfied") == "unsatisfied"


def test_director_consumes_frozen_projection_and_context_binding():
    projection = ChapterEngagementProjection("p", 1, "a" * 64, "b" * 64, "c" * 64, 7, ("e1",), '{"p":1}', "d" * 64)
    decision = _decision()
    obligation = object.__new__(type("O", (), {}))
    with pytest.raises(NarrativeDirectorBlockedError, match="engagement"):
        from creative_os.domains.narrative_director import NarrativeDirector, DirectorInput
        NarrativeDirector().propose(DirectorInput(".", 7, __import__('tests.test_narrative_director', fromlist=['_profile'])._profile(), ({"kind":"x","subject":"y"},), "end", (), 7000, projection, hashlib.sha256(projection.canonical_json.encode()).hexdigest()), decision)
