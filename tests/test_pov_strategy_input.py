from pathlib import Path

from creative_os.domains.narrative_decision import NarrativeDecision
from creative_os.domains.pov_strategy_input import assemble_pov_strategy_input
from creative_os.domains.pov_strategy_model import ChapterNeeds
from creative_os.domains.pov_strategy_policy import POVStrategyPolicy
from tests.pov_strategy_helpers import HASH


def test_assembler_reads_only_formal_chapters_and_active_contracts(monkeypatch, tmp_path):
    final = tmp_path / "production/final_chapters"
    final.mkdir(parents=True)
    for chapter in range(1, 4):
        owner = "林子轩" if chapter == 1 else "配角"
        (final / f"chapter_{chapter:03d}.md").write_text(f"# 第{chapter}章\n{owner}推进正式正文。", encoding="utf-8")
    decisions = {chapter: _decision(chapter, "林子轩" if chapter == 1 else "配角") for chapter in range(1, 4)}
    monkeypatch.setattr("creative_os.domains.pov_strategy_input.load_active_narrative_decision", lambda _r, n: decisions.get(n))
    monkeypatch.setattr("creative_os.domains.pov_strategy_input.load_active_narrative_profile", lambda _r: _profile(decisions[1]))
    monkeypatch.setattr("creative_os.domains.pov_strategy_input.compact_active_snapshots", lambda *_a, **_k: [])

    value = assemble_pov_strategy_input(tmp_path, 4, _needs(), POVStrategyPolicy())

    assert [item.chapter for item in value.recent_pov_history] == [1, 2, 3]
    assert value.protagonist_load.cold_start is True
    assert value.protagonist_load.consecutive_absence == 2
    assert len(value.baseline_fingerprint) == 64
    assert value.unclaimed_consequences == ()
    assert value.character_pressures == ()


def _needs():
    return ChapterNeeds(("整合后果",), "谁来承接", ("integrate",), "", ())


def _decision(chapter, owner):
    from tests.test_narrative_director import _v2_decision
    value = _v2_decision(chapter)
    import json
    payload = json.loads(value.to_json())
    payload["chapter_contract"]["pov_plan"]["primary_owner"] = owner
    payload["chapter_contract"]["pov_plan"]["protagonist_present"] = owner == "林子轩"
    payload["chapter_contract"]["pov_plan"]["supporting_agency"][0]["actor"] = owner
    return NarrativeDecision.from_json(json.dumps(payload, ensure_ascii=False))


def _profile(decision):
    from tests.test_narrative_director import _profile
    return _profile()
