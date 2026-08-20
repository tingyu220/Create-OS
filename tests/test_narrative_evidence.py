import json

import pytest

from creative_os.domains.narrative_evidence import load_chapter_evidence


def _seed_chapter_artifacts(root, chapter_number=1):
    chapter_id = f"chapter_{chapter_number:03d}"
    chapter_root = root / "production" / chapter_id
    final_path = root / "production" / "final_chapters" / f"{chapter_id}.md"
    final_path.parent.mkdir(parents=True)
    final_path.write_text("# 第一章\n\n主角回到了城里。\n", encoding="utf-8")

    for directory in ("contexts", "knowledge", "tasks"):
        path = chapter_root / directory
        path.mkdir(parents=True)
        (path / "b.json").write_text(json.dumps({"order": 2}), encoding="utf-8")
        (path / "a.json").write_text(json.dumps({"order": 1}), encoding="utf-8")
    reviews = chapter_root / "reviews"
    reviews.mkdir(parents=True)
    (reviews / "review.md").write_text("Pass", encoding="utf-8")
    return root


def test_load_chapter_evidence_reads_canonical_artifacts_in_stable_order(tmp_path):
    root = _seed_chapter_artifacts(tmp_path)

    evidence = load_chapter_evidence(root, 1)

    assert evidence.chapter_id == "chapter_001"
    assert "主角" in evidence.prose
    assert evidence.source_refs[0].endswith("chapter_001.md")
    assert [item.data["order"] for item in evidence.contexts] == [1, 2]
    assert len(evidence.tasks) == 2
    assert all(not path.is_absolute() for path in evidence.source_paths())


def test_load_chapter_evidence_fails_when_canonical_chapter_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="chapter_001"):
        load_chapter_evidence(tmp_path, 1)


def test_load_chapter_evidence_reports_invalid_json_path(tmp_path):
    root = _seed_chapter_artifacts(tmp_path)
    invalid = root / "production/chapter_001/contexts/a.json"
    invalid.write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match=r"contexts[\\/]a\.json"):
        load_chapter_evidence(root, 1)
