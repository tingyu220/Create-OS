from __future__ import annotations

import pytest

from creative_os.projection.provenance import Derivation, SourceHead, SourceRef


def test_source_ref_rejects_windows_absolute_locator() -> None:
    """捕获把机器绝对路径泄漏进可移植快照的实现。"""
    with pytest.raises(ValueError, match="source_locator_must_be_project_relative"):
        SourceRef(
            source_kind="chapter_status",
            source_id="chapter-029",
            locator=r"D:\book\status.json",
            content_hash="a" * 64,
        )


def test_source_ref_rejects_parent_traversal() -> None:
    """捕获允许来源引用逃出项目根的实现。"""
    with pytest.raises(ValueError, match="source_locator_must_be_project_relative"):
        SourceRef("review", "review-029", "../review.json", "b" * 64)


def test_source_ref_normalizes_locator_to_posix() -> None:
    reference = SourceRef("review", "review-029", r"production\reviews\029.json", "b" * 64)

    assert reference.locator == "production/reviews/029.json"


def test_derivation_requires_at_least_one_source() -> None:
    """捕获没有证据却声称是派生状态的实现。"""
    with pytest.raises(ValueError, match="derivation_inputs_required"):
        Derivation(rule_id="chapter.blocked_by_gate", inputs=())


def test_source_head_requires_cursor_or_content_hash() -> None:
    with pytest.raises(ValueError, match="source_head_position_required"):
        SourceHead(source_kind="event_log", source_id="runtime", cursor=None, content_hash=None)
