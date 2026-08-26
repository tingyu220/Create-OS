import dataclasses

import pytest

from creative_os.domains.pov_strategy_model import EvidenceRef, POVStrategyCandidateSet, POVStrategyValidationError
from creative_os.domains.narrative_evidence import EvidenceLocator


def test_candidate_model_has_no_prose_or_activation_fields():
    fields = {field.name for field in dataclasses.fields(POVStrategyCandidateSet)}
    assert fields.isdisjoint({"draft", "body", "memory_status"})


def test_evidence_requires_sha256():
    with pytest.raises(ValueError):
        EvidenceRef(
            source_id="source",
            source_version="1",
            source_content_hash="bad",
            locator=EvidenceLocator("text_anchor", "line:1"),
            assertion="证明",
        ).validate()
