import dataclasses

import pytest

from creative_os.domains.pov_strategy_model import EvidenceRef, POVStrategyCandidateSet, POVStrategyValidationError


def test_candidate_model_has_no_prose_or_activation_fields():
    fields = {field.name for field in dataclasses.fields(POVStrategyCandidateSet)}
    assert fields.isdisjoint({"draft", "body", "memory_status"})


def test_evidence_requires_sha256():
    with pytest.raises(POVStrategyValidationError):
        EvidenceRef("source", "1", "bad", "line:1", "证明").validate()
