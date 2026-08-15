from creative_os.local_repair import build_local_repair_messages, detect_repair_scope


def test_detect_repair_scope_uses_local_for_reader_surface_issues():
    assert detect_repair_scope(["time_word_opener"]) == "local"
    assert detect_repair_scope(["reader_term:Context"]) == "local"


def test_detect_repair_scope_uses_full_for_missing_fact():
    assert detect_repair_scope(["missing_fact:林遥未离城"]) == "full"


def test_detect_repair_scope_uses_full_for_shrinkage():
    assert detect_repair_scope(["below_minimum_chinese_chars"]) == "full"


def test_build_local_repair_messages_preserves_full_chapter_context():
    messages = build_local_repair_messages("# 第 1 章\n\n凌晨，林澈回城。", ["time_word_opener"])

    assert messages[0].role == "system"
    assert "只输出修复后的完整章节正文" in messages[0].content
    assert "不改变剧情事实" in messages[1].content
    assert "time_word_opener" in messages[1].content
    assert "凌晨，林澈回城。" in messages[1].content
