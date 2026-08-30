from pathlib import Path
import hashlib
import json

import pytest

from creative_os.domains.publication_reflow_materializer import (
    PublicationReflowError,
    materialize_publication_reflow,
)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _source(tmp_path: Path) -> tuple[Path, str]:
    project = tmp_path / "book"
    edition = project / ".creative_os/publication_migration/target_editions/source"
    edition.mkdir(parents=True)
    chapters = []
    for number in (1, 2, 3):
        content = f"# 第 {number} 章：标题{number}\n\n正文{number}\n"
        filename = f"chapter_{number:03d}.md"
        (edition / filename).write_text(content, encoding="utf-8")
        chapters.append({"target_chapter_id": number, "file": filename,
                         "content_hash": hashlib.sha256(content.encode()).hexdigest()})
    manifest = {"schema_version": 1, "chapters": chapters}
    manifest["manifest_hash"] = hashlib.sha256(_canonical(manifest).encode()).hexdigest()
    (edition / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return project, manifest["manifest_hash"]


def test_reflow_preserves_exact_source_coverage(tmp_path):
    project, source_hash = _source(tmp_path)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "schema_version": 1, "source_edition_id": "source",
        "source_manifest_hash": source_hash, "target_edition_id": "target",
        "chapters": [
            {"target_chapter_id": 1, "source_chapter_ids": [1]},
            {"target_chapter_id": 2, "source_chapter_ids": [2, 3], "title": "合章"},
        ],
    }), encoding="utf-8")
    manifest = materialize_publication_reflow(project, spec_path=spec)
    assert len(manifest["chapters"]) == 2
    assert (project / ".creative_os/publication_migration/target_editions/target/chapter_002.md").read_text(
        encoding="utf-8"
    ).count("正文") == 2


def test_reflow_rejects_missing_source_chapter(tmp_path):
    project, source_hash = _source(tmp_path)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "schema_version": 1, "source_edition_id": "source",
        "source_manifest_hash": source_hash, "target_edition_id": "target",
        "chapters": [{"target_chapter_id": 1, "source_chapter_ids": [1, 2]}],
    }), encoding="utf-8")
    with pytest.raises(PublicationReflowError, match="coverage"):
        materialize_publication_reflow(project, spec_path=spec)


def test_reflow_expands_compact_merge_plan(tmp_path):
    project, source_hash = _source(tmp_path)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "schema_version": 1, "source_edition_id": "source",
        "source_manifest_hash": source_hash, "target_edition_id": "target",
        "merges": [{"source_chapter_ids": [2, 3], "title": "合章"}],
    }), encoding="utf-8")
    manifest = materialize_publication_reflow(project, spec_path=spec)
    assert [item["source_chapter_ids"] for item in manifest["chapters"]] == [[1], [2, 3]]


def test_reflow_applies_expansion_at_exact_paragraph_ordinal(tmp_path):
    project, source_hash = _source(tmp_path)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "schema_version": 1, "source_edition_id": "source",
        "source_manifest_hash": source_hash, "target_edition_id": "target",
        "merges": [],
        "expansions": [{"source_chapter_id": 2, "after_paragraph": 1,
                        "paragraphs": ["补写段落"]}],
    }), encoding="utf-8")
    materialize_publication_reflow(project, spec_path=spec)
    content = (project / ".creative_os/publication_migration/target_editions/target/chapter_002.md").read_text(
        encoding="utf-8"
    )
    assert "正文2\n\n补写段落" in content


def test_reflow_can_trim_a_confirmed_duplicate_tail(tmp_path):
    project, source_hash = _source(tmp_path)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "schema_version": 1, "source_edition_id": "source",
        "source_manifest_hash": source_hash, "target_edition_id": "target",
        "merges": [], "trims": [{"source_chapter_id": 2, "keep_through_paragraph": 1}],
    }), encoding="utf-8")
    materialize_publication_reflow(project, spec_path=spec)
    content = (project / ".creative_os/publication_migration/target_editions/target/chapter_002.md").read_text(
        encoding="utf-8"
    )
    assert content.count("正文2") == 1
