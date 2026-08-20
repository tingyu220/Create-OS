from creative_os.domains.narrative_memory import load_active_narrative_decision, load_active_narrative_profile
from creative_os.memory.store import JsonMemoryStore
from scripts.prepare_narrative_validation import build_decisions, build_profile, prepare


def test_validation_contracts_are_complete_and_approved(tmp_path):
    project = tmp_path / "文明升阶"
    prepare(project, actor="tingyu")

    assert load_active_narrative_profile(project) == build_profile()
    assert [load_active_narrative_decision(project, chapter).chapter for chapter in range(3, 13)] == list(range(3, 13))
    assert all(item.approved_by == "tingyu" for item in JsonMemoryStore(project / ".creative_os/memory").list())
    assert [decision.chapter for decision in build_decisions()] == list(range(3, 31))


def test_construction_chapters_start_a_new_arc_with_monotonic_phases():
    profile = build_profile()
    decisions = {decision.chapter: decision for decision in build_decisions()}

    assert {arc.id for arc in profile.arcs} >= {"arc-key-and-cost", "arc-fusion-construction"}
    assert decisions[22].arc_id == "arc-key-and-cost"
    assert decisions[23].arc_id == "arc-fusion-construction"
    assert [decisions[chapter].arc_phase.value for chapter in range(23, 31)] == [
        "setup", "escalation", "escalation", "escalation",
        "escalation", "escalation", "turn", "aftermath",
    ]
