from __future__ import annotations

from pathlib import Path

from creative_os.task_status import load_chapter_statuses


def render_console_dashboard(project_root: str | Path) -> str:
    statuses = load_chapter_statuses(project_root)
    lines = ["章节状态"]
    if not statuses:
        lines.extend(["", "暂无章节任务状态"])
        return "\n".join(lines)

    pass_count = sum(1 for status in statuses if status.status == "pass")
    fail_count = sum(1 for status in statuses if status.status == "fail")
    lines.extend([f"通过: {pass_count}", f"失败: {fail_count}", ""])
    for status in statuses:
        issue_text = f" issues={';'.join(status.issues)}" if status.issues else ""
        lines.append(
            f"chapter_{status.chapter:03d} {status.status} "
            f"attempts={status.attempts} elapsed={status.elapsed_seconds:.1f}s{issue_text}"
        )
    return "\n".join(lines)
