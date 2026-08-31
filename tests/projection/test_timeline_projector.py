from __future__ import annotations

import json

from creative_os.projection.projectors.narrative import project_timeline
from creative_os.projection.provenance import SourceRef
from creative_os.projection.source import ActiveStateFact, ProjectFacts


def _facts(*states: ActiveStateFact) -> ProjectFacts:
    return ProjectFacts("book-a", (), (), (), (), (), (), tuple(item.source_ref for item in states), tuple(states))


def _state(subject: str, payload: dict[str, object], source_id: str) -> ActiveStateFact:
    ref = SourceRef("active_state", source_id, f"state/{source_id}.json", source_id * 64)
    return ActiveStateFact("timeline", subject, json.dumps(payload), ref)


def test_timeline_projection_keeps_unknown_for_missing_structured_fields() -> None:
    result = project_timeline(_facts(_state("事件A", {"precision": "chapter_only"}, "a")))

    assert result[0].precision == "chapter_only"
    assert result[0].relative_order == "unknown"
    assert result[0].conflict_status == "unknown"


def test_timeline_projection_fails_closed_on_conflicting_active_sources() -> None:
    result = project_timeline(_facts(
        _state("事件A", {"precision": "chapter_only", "relative_order": "先"}, "a"),
        _state("事件A", {"precision": "scene_only", "relative_order": "后"}, "b"),
    ))

    entry = result[0]
    assert entry.precision == "unknown"
    assert entry.relative_order == "unknown"
    assert entry.conflict_status == "conflicted"
    assert {ref.source_id for ref in entry.source_refs} == {"a", "b"}
    assert {ref.source_id for ref in entry.derivation.inputs} == {"a", "b"}


def test_timeline_projection_does_not_leak_conflicting_source_fields() -> None:
    result = project_timeline(_facts(
        _state("事件A", {"precision": "chapter_only", "relative_order": "先", "detail": "来源A"}, "a"),
        _state("事件A", {"precision": "scene_only", "relative_order": "后", "detail": "来源B"}, "b"),
    ))

    assert json.loads(result[0].fields_json) == {
        "conflict_status": "conflicted",
        "precision": "unknown",
        "relative_order": "unknown",
    }


def test_timeline_projection_preserves_structured_fields_and_provenance() -> None:
    result = project_timeline(_facts(_state(
        "事件A", {"precision": "chapter_only", "relative_order": "第1章内", "conflict_status": "clear"}, "a"
    )))

    entry = result[0]
    assert (entry.precision, entry.relative_order, entry.conflict_status) == ("chapter_only", "第1章内", "clear")
    assert entry.derivation.rule_id == "active-timeline-state"
