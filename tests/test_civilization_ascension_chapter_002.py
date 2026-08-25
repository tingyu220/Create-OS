from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1] / "projects" / "文明升阶"


def test_chapter_002_preserves_the_dragon_abyss_storyline_and_hands_off_to_chapter_003():
    chapter_002 = (PROJECT_ROOT / "production/final_chapters/chapter_002.md").read_text(encoding="utf-8")
    chapter_003 = (PROJECT_ROOT / "production/final_chapters/chapter_003.md").read_text(encoding="utf-8")

    assert "不要相信那个声音" in chapter_002
    assert "显示屏" in chapter_002[-500:]
    assert "显示屏上的男人" in chapter_003[:200]

    premature_story_terms = (
        "银色球体",
        "你不是建造者",
        "你是收割者",
        "主核为什么会自毁",
        "人造卫星发送数据",
    )
    assert not any(term in chapter_002 for term in premature_story_terms)

    assert "刘阳" not in chapter_002
    assert "林峰" not in chapter_002
    assert "林正弘" not in chapter_002
