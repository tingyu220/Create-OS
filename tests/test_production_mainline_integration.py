import ast
import json
from pathlib import Path

from creative_os.domains.narrative_memory import load_active_narrative_decision


ROOT = Path(__file__).parents[1]
PROJECT = ROOT / "projects" / "文明升阶"


def test_civilization_ascension_has_one_continuous_canon_through_chapter_032():
    final_dir = PROJECT / "production" / "final_chapters"
    assert [path.name for path in sorted(final_dir.glob("chapter_*.md"))] == [
        f"chapter_{chapter:03d}.md" for chapter in range(1, 33)
    ]

    chapter_002 = (final_dir / "chapter_002.md").read_text(encoding="utf-8")
    assert "不要相信那个声音" in chapter_002
    assert not any(term in chapter_002 for term in ("银色球体", "你是收割者", "林峰", "刘阳"))

    chapter_020 = (final_dir / "chapter_020.md").read_text(encoding="utf-8")
    chapter_022 = (final_dir / "chapter_022.md").read_text(encoding="utf-8")
    chapter_023 = (final_dir / "chapter_023.md").read_text(encoding="utf-8")
    assert "遗产仓库" not in chapter_020
    assert "倒计时两年" not in chapter_022 and "七年" in chapter_022
    assert "成功点火" not in chapter_023


def test_chapter_007_032_contracts_use_integrated_scene_technology_and_pov_schema():
    items = PROJECT / ".creative_os" / "memory" / "items"
    for chapter in range(7, 27):
        payload = json.loads((items / f"narrative-chapter-{chapter:03d}.json").read_text(encoding="utf-8"))
        decision = json.loads(payload["content"])
        contract = decision["chapter_contract"]
        assert decision["schema_version"] == 2
        assert contract["scene_plan"]["scenes"]
        assert "technology_plan" in contract
        if chapter >= 24:
            assert contract["pov_plan"]["primary_owner"]
        else:
            assert "pov_plan" not in contract

    chapter_027 = load_active_narrative_decision(PROJECT, 27)
    assert chapter_027 is not None
    assert chapter_027.chapter_contract.scene_plan.scenes
    assert chapter_027.chapter_contract.technology_plan.technologies
    assert chapter_027.chapter_contract.pov_plan.primary_owner == "林子轩"

    for chapter in range(28, 33):
        decision = load_active_narrative_decision(PROJECT, chapter)
        assert decision is not None
        assert decision.schema_version == 2
        assert decision.chapter_contract.scene_plan.scenes
        assert decision.chapter_contract.technology_plan.technologies
        assert decision.chapter_contract.pov_plan.primary_owner


def test_historical_scene_v2_contracts_load_through_the_integrated_codec():
    for chapter in range(7, 33):
        decision = load_active_narrative_decision(PROJECT, chapter)
        assert decision is not None
        assert decision.chapter == chapter
        assert decision.chapter_contract.scene_plan.scenes


def test_phase_e_and_pov_share_one_evidence_ref_type():
    definitions = []
    for path in (ROOT / "creative_os").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        definitions.extend(path for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == "EvidenceRef")
    assert definitions == [ROOT / "creative_os" / "domains" / "narrative_evidence.py"]


def test_readiness_points_to_chapter_033_after_chapter_032_completion():
    readiness = (PROJECT / "production" / "reports" / "continuation_readiness.md").read_text(encoding="utf-8")
    assert "下一章：33" in readiness
    assert "第32章最终状态已物化" in readiness
    assert (PROJECT / "production" / "final_chapters" / "chapter_032.md").exists()
    assert not (PROJECT / "production" / "final_chapters" / "chapter_033.md").exists()
