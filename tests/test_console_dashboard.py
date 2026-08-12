from creative_os.console_dashboard import render_console_dashboard
from creative_os.task_status import ChapterTaskStatus, write_chapter_status


def test_render_console_dashboard_shows_status_summary(tmp_path):
    write_chapter_status(tmp_path, ChapterTaskStatus(1, "pass", 1, 3.2, []))
    write_chapter_status(tmp_path, ChapterTaskStatus(2, "fail", 2, 8.5, ["missing_fact:测试"]))

    output = render_console_dashboard(tmp_path)

    assert "章节状态" in output
    assert "通过: 1" in output
    assert "失败: 1" in output
    assert "chapter_002" in output
    assert "missing_fact:测试" in output


def test_render_console_dashboard_handles_empty_statuses(tmp_path):
    output = render_console_dashboard(tmp_path)

    assert "章节状态" in output
    assert "暂无章节任务状态" in output
