from creative_os.domains.novel_importer import classify_novel_documents, default_novel_mapping, role_of
from creative_os.importing.scanner import scan_source


def test_classifier_keeps_official_chapters_and_excludes_fix_tree(tmp_path):
    source = tmp_path / "文明升阶"
    for relative in (
        "04_Chapters/第1章 数据里的幽灵.md",
        "00_Worldview/Main_Worldview.md",
        "01_Characters/林子轩.md",
        "02_Plot/第一卷.md",
        "03_Hooks/Hooks_Tracker.md",
        "05_Context/Author_Diary.md",
        "06_重构方案.md",
        "fix/第1章 数据里的幽灵.md",
    ):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content", encoding="utf-8")

    result = classify_novel_documents(scan_source(source), default_novel_mapping())

    assert role_of(result, "04_Chapters/第1章 数据里的幽灵.md") == "canon_chapter"
    assert role_of(result, "00_Worldview/Main_Worldview.md") == "world"
    assert role_of(result, "01_Characters/林子轩.md") == "character"
    assert role_of(result, "06_重构方案.md") == "outline"
    assert role_of(result, "fix/第1章 数据里的幽灵.md") == "archive"


def test_classifier_accepts_custom_prefix_mapping(tmp_path):
    source = tmp_path / "custom"
    (source / "正文" / "第1章.md").mkdir(parents=True)
    path = source / "正文" / "第1章.md" / "chapter.md"
    path.write_text("content", encoding="utf-8")

    result = classify_novel_documents(scan_source(source), {"正文": "canon_chapter"})

    assert role_of(result, "正文/第1章.md/chapter.md") == "canon_chapter"
