from creative_os.domains.novel_importer import classify_novel_documents
from creative_os.domains.novel_baseline import build_novel_baseline
from creative_os.importing.scanner import scan_source


def test_baseline_preserves_provenance_and_never_activates_unconfirmed_facts(tmp_path):
    source = tmp_path / "文明升阶"
    files = {
        "04_Chapters/第1章 数据里的幽灵.md": "# 第1章：数据里的幽灵\n正文一",
        "04_Chapters/第2章 龙渊.md": "# 第2章：龙渊\n正文二",
        "核心框架.md": "# 世界观\n## 核心规则\n物理现实不可违背。",
        "01_Characters/林子轩.md": "# 林子轩\n身份：天文系学生。",
        "02_Plot/第一卷.md": "# 第一卷\n## 关键事件\n林子轩进入龙渊。",
        "03_Hooks/Hooks_Tracker.md": "# H-001\nCMB信号来源未揭示。",
        "05_Context/Author_Diary.md": "# 写作规则\n保持生活感。",
    }
    for relative, content in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    classified = classify_novel_documents(scan_source(source))
    draft = build_novel_baseline(classified)

    assert [chapter.number for chapter in draft.canon_chapters] == [1, 2]
    assert draft.world_rules[0].source_path == "核心框架.md"
    assert draft.characters[0].source_path == "01_Characters/林子轩.md"
    assert draft.hooks[0].source_path == "03_Hooks/Hooks_Tracker.md"
    assert all(item.status == "candidate" for item in draft.knowledge_candidates)
