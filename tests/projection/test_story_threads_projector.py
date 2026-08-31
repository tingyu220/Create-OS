from __future__ import annotations

import json

from creative_os.projection.projectors.narrative import project_story_threads
from creative_os.projection.provenance import SourceRef
from creative_os.projection.source import ActiveStateFact, EngagementExpectationFact, ProjectFacts


def _ref(kind: str, source_id: str) -> SourceRef:
    return SourceRef(kind, source_id, f"{kind}/{source_id}.json", "a" * 64)


def _facts(*, states: tuple[ActiveStateFact, ...] = (), expectations: tuple[EngagementExpectationFact, ...] = ()) -> ProjectFacts:
    refs = tuple(item.source_ref for item in states) + tuple(item.source_ref for item in expectations)
    return ProjectFacts("book-a", (), (), (), (), (), (), refs, states, expectations)


def test_story_threads_aggregate_authoritative_hook_and_approved_expectation() -> None:
    hook_ref = _ref("active_state", "hook-1")
    transition_ref = _ref("engagement_authority", "transition-1")
    decision_ref = _ref("engagement_authority", "decision-1")
    result = project_story_threads(_facts(
        states=(ActiveStateFact("hook", "钥匙线", json.dumps({"status": "open", "open_loop": "钥匙仍未解释"}), hook_ref),),
        expectations=(EngagementExpectationFact("expectation-1", "absent", "open", "a" * 64, transition_ref, decision_ref),),
    ))

    assert [(item.subject, item.thread_type, item.status) for item in result] == [
        ("expectation-1", "expectation", "open"),
        ("钥匙线", "foreshadow", "open"),
    ]
    expectation = result[0]
    assert {ref.source_id for ref in expectation.source_refs} == {"transition-1", "decision-1"}
    assert {ref.source_id for ref in expectation.derivation.inputs} == {"transition-1", "decision-1"}


def test_story_thread_keeps_open_loop_missing_when_authority_does_not_prove_it() -> None:
    ref = _ref("active_state", "hook-1")
    result = project_story_threads(_facts(states=(ActiveStateFact("hook", "未知线", json.dumps({"status": "open"}), ref),)))

    assert result[0].open_loop is None
    assert result[0].fields_json == '{"status": "open"}'


def test_story_thread_ignores_non_hook_active_states_and_unapproved_expectations() -> None:
    character_ref = _ref("active_state", "character-1")
    result = project_story_threads(_facts(
        states=(ActiveStateFact("character", "人物", "{}", character_ref),),
    ))

    assert result == ()
