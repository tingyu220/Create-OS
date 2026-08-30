import pytest
from pathlib import Path
import subprocess
import sys

from creative_os.domains.publication_source_snapshot import VerifiedSourceParagraph
from creative_os.domains.publication_target_materializer import (
    MaterializationError,
    apply_published_expansion,
    render_target_chapter,
    validate_exact_coverage,
)
from creative_os.domains.target_chapter_grouping import TargetChapterGroupingCandidate


def _paragraph(chapter: int, ordinal: int, text: str) -> VerifiedSourceParagraph:
    return VerifiedSourceParagraph(chapter, ordinal, text, "a" * 64, "b" * 64, "c" * 64, "d" * 64)


def test_render_target_chapter_replaces_source_heading_and_preserves_body():
    paragraphs = (
        _paragraph(5, 1, "# 第 5 章：旧标题"),
        _paragraph(5, 2, "第一段。"),
        _paragraph(5, 3, "第二段。\n"),
    )

    rendered = render_target_chapter(5, "余震", paragraphs)

    assert rendered == "# 第 5 章：余震\n\n第一段。\n\n第二段。\n"


def test_render_target_chapter_removes_internal_source_heading():
    paragraphs = (
        _paragraph(7, 78, "上一章结尾。"),
        _paragraph(8, 1, "# 第 8 章：联邦会议"),
        _paragraph(8, 2, "下一章正文。"),
    )

    rendered = render_target_chapter(11, "协议最后一行", paragraphs)

    assert rendered == "# 第 11 章：协议最后一行\n\n上一章结尾。\n\n下一章正文。\n"


def test_exact_coverage_rejects_duplicate_or_missing_source_paragraphs():
    available = ((5, 1), (5, 2), (5, 3))
    groups = (
        TargetChapterGroupingCandidate("m", 5, (1,), ((5, 1), (5, 2)), 100, ("hook",)),
        TargetChapterGroupingCandidate("m", 6, (2,), ((5, 2),), 100, ("hook-2",)),
    )

    with pytest.raises(MaterializationError, match="source_mapping_not_exact"):
        validate_exact_coverage(groups, available)


def test_materialization_cli_supports_direct_file_entry():
    script = Path("scripts/materialize_publication_split.py")
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
    )

    assert result.returncode == 0
    assert b"approve" in result.stdout
    assert b"materialize" in result.stdout


def test_published_expansion_is_bound_to_exact_base_and_anchor():
    base = "# 第 10 章：标题\n\n第一段。\n\n第二段。\n"
    spec = {
        "base_content_hash": __import__("hashlib").sha256(base.encode()).hexdigest(),
        "insertions": [{
            "after_paragraph_hash": __import__("hashlib").sha256("第一段。".encode()).hexdigest(),
            "paragraphs": ["补充一。", "补充二。"],
        }],
    }

    assert apply_published_expansion(base, spec) == (
        "# 第 10 章：标题\n\n第一段。\n\n补充一。\n\n补充二。\n\n第二段。\n"
    )
    with pytest.raises(MaterializationError, match="published_revision_base_mismatch"):
        apply_published_expansion(base + "漂移", spec)
