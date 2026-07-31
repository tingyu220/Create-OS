import pytest

from scripts.run_llm_writer_pilot import parse_chapters


def test_parse_chapters_accepts_commas_and_ranges():
    assert parse_chapters("4,7-9,12") == [4, 7, 8, 9, 12]


def test_parse_chapters_rejects_descending_range():
    with pytest.raises(ValueError, match="Invalid chapter range"):
        parse_chapters("9-7")
